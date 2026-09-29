// Sign-in: discovery, the consent page, Google, and who gets a token.
import { describe, expect, it } from "vitest";
import {
  CLAUDE_CALLBACK,
  ORIGIN,
  RESOURCE,
  call,
  connectAsOwner,
  decide,
  exchange,
  googleReturns,
  register,
  startAuthorize,
} from "./flow";

describe("discovery", () => {
  it("answers an unauthenticated /mcp with 401 pointing at its metadata", async () => {
    const res = await call("/mcp", { method: "POST", body: "{}" });
    expect(res.status).toBe(401);
    const challenge = res.headers.get("www-authenticate")!;
    expect(challenge).toContain(`resource_metadata="${ORIGIN}/.well-known/oauth-protected-resource/mcp"`);
    expect(challenge).toContain('scope="memory"');
  });

  it("publishes resource metadata naming this server as the authorization server", async () => {
    const meta = (await (await call("/.well-known/oauth-protected-resource/mcp")).json()) as Record<string, unknown>;
    expect(meta.resource).toBe(RESOURCE);
    expect(meta.authorization_servers).toEqual([ORIGIN]);
  });

  it("advertises what Claude needs: DCR, S256, and CIMD as a public client", async () => {
    const meta = (await (await call("/.well-known/oauth-authorization-server")).json()) as Record<string, unknown>;
    expect(meta.registration_endpoint).toBe(`${ORIGIN}/register`);
    expect(meta.code_challenge_methods_supported).toEqual(["S256"]);
    expect(meta.client_id_metadata_document_supported).toBe(true);
    expect(meta.token_endpoint_auth_methods_supported).toContain("none");
  });
});

describe("consent page", () => {
  it("names the client, marks it unverified, and shows where access goes", async () => {
    const s = await startAuthorize(await register("Claude"));
    expect(s.consentPage).toContain("Allow Claude to use your memory?");
    expect(s.consentPage).toContain("its name is not verified");
    expect(s.consentPage).toContain("<strong>claude.ai</strong>");
    expect(s.consentPage).not.toContain("an app on your computer");
  });

  it("escapes a hostile client name", async () => {
    const s = await startAuthorize(await register("<script>alert(1)</script>"));
    expect(s.consentPage).not.toContain("<script>alert(1)");
    expect(s.consentPage).toContain("&#60;script&#62;");
  });

  it("accepts a local client's loopback redirect on any port, with a warning", async () => {
    const clientId = await register("Claude Code", "http://localhost/callback");
    const s = await startAuthorize(clientId, "http://localhost:3118/callback");
    expect(s.consentPage).toContain("an app on your computer");
  });

  it("refuses an approval posted without the page's browser cookie", async () => {
    const s = await startAuthorize(await register());
    const forged = await decide({ ...s, cookies: "" }, "approve");
    expect(forged.status).toBe(400);
  });

  it("sends Deny back to the client as access_denied", async () => {
    const s = await startAuthorize(await register());
    const res = await decide(s, "deny");
    const to = new URL(res.headers.get("location")!);
    expect(`${to.origin}${to.pathname}`).toBe(CLAUDE_CALLBACK);
    expect(to.searchParams.get("error")).toBe("access_denied");
    expect(to.searchParams.get("state")).toBe("client-state");
  });
});

describe("Google sign-in", () => {
  it("sends the approved request to Google with PKCE and a state", async () => {
    const s = await startAuthorize(await register());
    const toGoogle = new URL((await decide(s, "approve")).headers.get("location")!);
    expect(toGoogle.origin + toGoogle.pathname).toBe("https://accounts.google.com/o/oauth2/v2/auth");
    expect(toGoogle.searchParams.get("scope")).toBe("openid email");
    expect(toGoogle.searchParams.get("redirect_uri")).toBe(`${ORIGIN}/callback`);
    expect(toGoogle.searchParams.get("code_challenge_method")).toBe("S256");
    expect(toGoogle.searchParams.get("state")).toBeTruthy();
  });

  it("issues the owner an access token and a refresh token", async () => {
    const s = await startAuthorize(await register());
    const toClient = await googleReturns(await decide(s, "approve"), "code-owner");
    expect(new URL(toClient.headers.get("location")!).searchParams.get("state")).toBe("client-state");
    const tokens = await exchange(s, toClient);
    expect(tokens.access_token).toBeTruthy();
    expect(tokens.refresh_token).toBeTruthy();
    expect(tokens.scope).toContain("memory");
  });

  it("turns away any other Google account", async () => {
    const s = await startAuthorize(await register());
    const res = await googleReturns(await decide(s, "approve"), "code-stranger");
    const to = new URL(res.headers.get("location")!);
    expect(to.searchParams.get("error")).toBe("access_denied");
    expect(to.searchParams.get("code")).toBeNull();
  });

  it("refuses a callback replayed without the browser's binding cookie", async () => {
    const s = await startAuthorize(await register());
    const toGoogle = await decide(s, "approve");
    const state = new URL(toGoogle.headers.get("location")!).searchParams.get("state")!;
    const res = await call(`/callback?${new URLSearchParams({ code: "code-owner", state })}`);
    expect(res.status).toBe(400);
  });

  it("gives a working token for /mcp", async () => {
    const token = await connectAsOwner();
    const res = await call("/mcp", { method: "POST", headers: { authorization: `Bearer ${token}` }, body: "{}" });
    expect(res.status).not.toBe(401);
  });
});
