import { OAuthProvider } from "@cloudflare/workers-oauth-provider";
import { createMcpHandler } from "@modelcontextprotocol/server";
import { authHandler } from "./auth";
import { buildServer } from "./tools";
import type { Env, Props } from "./types";

// kb-mcp: the MCP connector (docs/design/v3.md#mcp-connector). One Worker is
// both the OAuth authorization server and its only resource, /mcp. Owner-only:
// a token is issued only after Google sign-in as OWNER_GOOGLE_SUB.

const ORIGIN = "https://kb-mcp.aayush7511.workers.dev";
const DAY = 24 * 60 * 60;

export default new OAuthProvider<Env>({
  apiRoute: "/mcp",
  apiHandler: {
    fetch(request, env, ctx) {
      // Stateless (MCP 2026-07-28, and 2025-era clients via the SDK's default
      // stateless fallback): one server per request, nothing kept between them.
      const props = ctx.props as Props;
      return createMcpHandler(() => buildServer(env, props)).fetch(request);
    },
  },
  defaultHandler: authHandler,
  authorizeEndpoint: "/authorize",
  tokenEndpoint: "/token",
  clientRegistrationEndpoint: "/register", // DCR, for clients without CIMD support
  clientIdMetadataDocumentEnabled: true, // needs the global_fetch_strictly_public flag
  scopesSupported: ["memory", "offline_access"],
  requiredScopes: ["memory"],
  resourceMetadata: {
    resource: `${ORIGIN}/mcp`,
    authorization_servers: [ORIGIN],
    resource_name: "Knowledge base memory",
  },
  // A grant lives while its client keeps refreshing, and ends after 30 idle days.
  refreshTokenIdleTTL: 30 * DAY,
  refreshTokenTTL: 365 * DAY,
});
