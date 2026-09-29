import { AuthorizationError, CimdFetchError, authorizationErrorRedirect } from "@cloudflare/workers-oauth-provider";
import type { ConsentDescription } from "@cloudflare/workers-oauth-provider";
import type { Env, Props } from "./types";

// Sign-in for MCP clients (docs/design/v3.md#sign-in-google-decided-2026-09-29):
// consent page → Google → owner check → token. The library's consent and
// upstream helpers carry the confused-deputy protections MCP requires: a
// per-client consent page that can't be framed or forged, and a `state` bound
// to this browser, stored server-side, single use.

const GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN = "https://oauth2.googleapis.com/token";
const GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo";

interface UpstreamData {
  verifier: string; // PKCE for the Google leg
  clientName: string;
}

export const authHandler: ExportedHandler<Env> = {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    try {
      if (pathname === "/authorize" && request.method === "GET") return await showConsent(request, env);
      if (pathname === "/authorize" && request.method === "POST") return await decide(request, env);
      if (pathname === "/callback" && request.method === "GET") return await googleCallback(request, env);
    } catch (err) {
      // consent-page.md "Errors: redirect or render?"
      if (err instanceof AuthorizationError && err.redirectTo) return Response.redirect(err.redirectTo, 302);
      if (err instanceof AuthorizationError) return page(400, "Sign-in failed", escape(err.description));
      if (err instanceof CimdFetchError) return page(400, "Sign-in failed", "This app could not be verified.");
      throw err;
    }
    return new Response("not found", { status: 404 });
  },
};

async function showConsent(request: Request, env: Env): Promise<Response> {
  const oauth = env.OAUTH_PROVIDER;
  const authRequest = await oauth.parseAuthRequest(request);
  const details = await oauth.describeConsent(authRequest); // first: a failed lookup leaves nothing in KV
  const consent = await oauth.beginConsent(authRequest);
  consent.headers.set("Content-Type", "text/html; charset=utf-8");
  return new Response(consentPage(details, consent.handle), { headers: consent.headers });
}

async function decide(request: Request, env: Env): Promise<Response> {
  const oauth = env.OAUTH_PROVIDER;
  const form = await request.formData();
  const handle = String(form.get("handle"));
  if (form.get("decision") !== "approve") {
    const denied = await oauth.denyConsent(request, handle);
    return new Response(null, { status: 302, headers: denied.headers });
  }
  const approved = await oauth.approveConsent(request, handle);
  const details = await oauth.describeConsent(approved.request);

  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const { state, headers } = await oauth.beginUpstream(approved.request, {
    data: { verifier, clientName: details.clientName } satisfies UpstreamData,
    headers: approved.headers,
  });
  const google = new URL(GOOGLE_AUTHORIZE);
  google.search = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID,
    redirect_uri: callbackUrl(request),
    response_type: "code",
    scope: "openid email",
    state,
    code_challenge: await s256(verifier),
    code_challenge_method: "S256",
    prompt: "select_account",
  }).toString();
  headers.set("Location", google.href);
  return new Response(null, { status: 302, headers });
}

async function googleCallback(request: Request, env: Env): Promise<Response> {
  const oauth = env.OAUTH_PROVIDER;
  const { request: original, data, headers } = await oauth.finishUpstream<UpstreamData>(request);
  const params = new URL(request.url).searchParams;
  const code = params.get("code");
  if (params.get("error") || !code) {
    headers.set("Location", authorizationErrorRedirect(original, "access_denied"));
    return new Response(null, { status: 302, headers });
  }

  const tokenRes = await fetch(GOOGLE_TOKEN, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: callbackUrl(request),
      grant_type: "authorization_code",
      code_verifier: data.verifier,
    }),
  });
  if (!tokenRes.ok) {
    console.error("google token exchange failed", tokenRes.status, await tokenRes.text());
    return page(502, "Sign-in failed", "Google didn't accept the sign-in. Start again from your MCP client.");
  }
  const { access_token } = (await tokenRes.json()) as { access_token: string };
  const userRes = await fetch(GOOGLE_USERINFO, { headers: { Authorization: `Bearer ${access_token}` } });
  if (!userRes.ok) {
    console.error("google userinfo failed", userRes.status);
    return page(502, "Sign-in failed", "Couldn't read your Google account. Start again from your MCP client.");
  }
  const user = (await userRes.json()) as { sub: string; email?: string };

  if (!env.OWNER_GOOGLE_SUB) {
    // First-time setup: show the id to pin, and issue nothing.
    return page(
      403,
      "Almost set up",
      `<p>Signed in with Google as <strong>${escape(user.email ?? "unknown")}</strong>. To make this account the owner, run in <code>workers/mcp</code>:</p>` +
        `<pre>printf '%s' '${escape(user.sub)}' | npx wrangler secret put OWNER_GOOGLE_SUB</pre>` +
        "<p>Then connect again from your MCP client.</p>",
    );
  }
  if (user.sub !== env.OWNER_GOOGLE_SUB) {
    headers.set("Location", authorizationErrorRedirect(original, "access_denied", "this memory belongs to someone else"));
    return new Response(null, { status: 302, headers });
  }

  const { redirectTo } = await oauth.completeAuthorization({
    request: original,
    userId: user.sub,
    metadata: { client: data.clientName },
    scope: original.scope,
    props: { clientName: data.clientName } satisfies Props,
  });
  headers.set("Location", redirectTo);
  return new Response(null, { status: 302, headers });
}

function callbackUrl(request: Request): string {
  return new URL("/callback", request.url).href;
}

function consentPage(d: ConsentDescription, handle: string): string {
  const name = escape(d.clientName);
  const origin = d.clientDomain
    ? `Published by <strong>${escape(d.clientDomain)}</strong>.`
    : "This app registered itself; its name is not verified.";
  const loopback = d.redirectIsLoopback
    ? "<p><strong>This sends access to an app on your computer.</strong> Continue only if you just started connecting from it.</p>"
    : "";
  return html(
    `Connect ${name}?`,
    `<h1>Allow ${name} to use your memory?</h1>
<p>It will be able to search your knowledge graph and save links and notes to it. It can't delete anything.</p>
<p>${origin} Access will be sent to <strong>${escape(d.redirectHost)}</strong>.</p>
${loopback}
<p>Next you'll sign in with Google, to prove you're the owner.</p>
<form method="post">
  <input type="hidden" name="handle" value="${escape(handle)}">
  <button name="decision" value="approve">Allow</button>
  <button name="decision" value="deny">Deny</button>
</form>`,
  );
}

function page(status: number, title: string, body: string): Response {
  return new Response(html(title, `<h1>${escape(title)}</h1>\n${body.startsWith("<") ? body : `<p>${body}</p>`}`), {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

function html(title: string, body: string): string {
  return `<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(title)}</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem}button{font:inherit;padding:.5rem 1.25rem;margin-right:.5rem}pre{white-space:pre-wrap;word-break:break-all;background:#f3f3f3;padding:.75rem}</style>
${body}
</html>`;
}

function escape(value: string): string {
  return value.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function s256(verifier: string): Promise<string> {
  return base64url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
}
