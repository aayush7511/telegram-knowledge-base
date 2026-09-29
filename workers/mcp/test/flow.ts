// The OAuth flow an MCP client runs, driven by hand against the Worker:
// register (DCR) → /authorize consent page → approve → Google (faked in
// vitest.config.ts) → /callback → code → /token. Cookies are carried
// explicitly, as a browser would.
import { exports } from "cloudflare:workers";

export const ORIGIN = "https://kb-mcp.aayush7511.workers.dev";
export const RESOURCE = `${ORIGIN}/mcp`;
export const CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback";

const worker = (exports as unknown as { default: Fetcher }).default;

export function call(path: string, init?: RequestInit): Promise<Response> {
  return worker.fetch(`${ORIGIN}${path}`, { redirect: "manual", ...init });
}

function cookiesFrom(res: Response): string {
  return res.headers
    .getSetCookie()
    .map((c) => c.split(";")[0])
    .join("; ");
}

function b64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function register(name = "Claude", redirect = CLAUDE_CALLBACK): Promise<string> {
  const res = await call("/register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ client_name: name, redirect_uris: [redirect], token_endpoint_auth_method: "none" }),
  });
  if (res.status !== 201) throw new Error(`register: ${res.status} ${await res.text()}`);
  return ((await res.json()) as { client_id: string }).client_id;
}

export interface Started {
  clientId: string;
  verifier: string;
  consentPage: string;
  handle: string;
  cookies: string;
}

export async function startAuthorize(clientId: string, redirect = CLAUDE_CALLBACK): Promise<Started> {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = b64url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
  const q = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirect,
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: "client-state",
    scope: "memory offline_access",
    resource: RESOURCE,
  });
  const res = await call(`/authorize?${q}`);
  const consentPage = await res.text();
  if (res.status !== 200) throw new Error(`authorize: ${res.status} ${consentPage}`);
  const handle = /name="handle" value="([^"]+)"/.exec(consentPage)![1];
  return { clientId, verifier, consentPage, handle, cookies: cookiesFrom(res) };
}

/** Approve (or deny) the consent page; returns the redirect response. */
export async function decide(s: Started, decision: "approve" | "deny"): Promise<Response> {
  return call("/authorize", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded", cookie: s.cookies },
    body: new URLSearchParams({ handle: s.handle, decision }),
  });
}

/** Google redirects back to /callback with `code`; returns our response. */
export async function googleReturns(toGoogle: Response, code: string): Promise<Response> {
  const state = new URL(toGoogle.headers.get("location")!).searchParams.get("state")!;
  return call(`/callback?${new URLSearchParams({ code, state })}`, { headers: { cookie: cookiesFrom(toGoogle) } });
}

export async function exchange(s: Started, toClient: Response, redirect = CLAUDE_CALLBACK) {
  const code = new URL(toClient.headers.get("location")!).searchParams.get("code")!;
  const res = await call("/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      client_id: s.clientId,
      redirect_uri: redirect,
      code_verifier: s.verifier,
      resource: RESOURCE,
    }),
  });
  if (res.status !== 200) throw new Error(`token: ${res.status} ${await res.text()}`);
  return (await res.json()) as { access_token: string; refresh_token?: string; scope: string };
}

/** The whole flow as the owner; returns an access token. */
export async function connectAsOwner(name = "Claude"): Promise<string> {
  const s = await startAuthorize(await register(name));
  const toClient = await googleReturns(await decide(s, "approve"), "code-owner");
  return (await exchange(s, toClient)).access_token;
}
