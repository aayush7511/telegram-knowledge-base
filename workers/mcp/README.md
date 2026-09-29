# kb-mcp (MCP connector)

Remote MCP server that lets Claude (claude.ai, Desktop, mobile, Claude Code)
and Codex search the knowledge graph and save to it. One Cloudflare Worker is
both the OAuth authorization server and the MCP endpoint, `/mcp`. Owner-only:
a token is issued only after Google sign-in as `OWNER_GOOGLE_SUB`. Design:
[docs/design/v3.md](../../docs/design/v3.md#mcp-connector).

- `src/index.ts` — `OAuthProvider` wiring (`@cloudflare/workers-oauth-provider`)
  and the stateless MCP handler (`@modelcontextprotocol/server` v2).
- `src/auth.ts` — `/authorize` consent page, the Google leg, `/callback` and
  the owner check.
- `src/tools.ts` — `search_memory` (→ `kb-orchestrator` `POST /search`) and
  `save_to_memory` (→ Worker 1's `IngestRpc.createJobs` over a service binding).
- `src/limits.ts` — tool-call caps, counted in D1's `usage` table.

## Develop

```bash
npm install
npm test           # runs inside workerd; Google, Cloud Run and Worker 1 are faked
npm run typecheck
```

## Deploy

Order matters: the D1 `usage` table and Worker 1's `IngestRpc` entrypoint must
exist before this Worker is deployed.

```bash
cd ../ingest && npx wrangler d1 migrations apply kb-jobs --remote && npx wrangler deploy && cd ../mcp
```

Create the Google OAuth client (once), in the Cloud project that runs
`kb-orchestrator`:

1. Google Auth Platform → Branding: app name, your email. Audience: External,
   **Testing**, and add your own Google account as the only test user.
2. Data Access: scopes `openid` and `.../auth/userinfo.email` only.
3. Clients → Create client → Web application. Authorized redirect URI:
   `https://kb-mcp.aayush7511.workers.dev/callback`.

Then set the secrets and deploy:

```bash
printf '%s' '<client id>'     | npx wrangler secret put GOOGLE_CLIENT_ID
printf '%s' '<client secret>' | npx wrangler secret put GOOGLE_CLIENT_SECRET
printf '%s' '<KB_SHARED_SECRET value>' | npx wrangler secret put CLOUD_RUN_SECRET
npx wrangler deploy
```

`OWNER_GOOGLE_SUB` is set last. Connect from any MCP client: with it unset, the
Google sign-in ends on a page showing your account id and the command that sets
it. Run that, then connect again.

## Connect

Server URL: `https://kb-mcp.aayush7511.workers.dev/mcp`

- **claude.ai / Desktop / mobile:** Settings → Connectors → Add custom connector,
  paste the URL.
- **Claude Code:** `claude mcp add --transport http kb-memory https://kb-mcp.aayush7511.workers.dev/mcp`,
  then `/mcp` to sign in.
- **Codex:** add the server under `[mcp_servers.kb-memory]` in `~/.codex/config.toml`
  with `url = "https://kb-mcp.aayush7511.workers.dev/mcp"`, then `codex mcp login kb-memory`.

Each client shows the consent page once, then signs in with Google; refresh
tokens keep it connected while it's used at least every 30 days.

## Skill

[skill/kb-memory/SKILL.md](skill/kb-memory/SKILL.md) teaches Claude when to
use the connector: search the knowledge base whenever the answer should fit the
owner (recommendations, learning, career, their projects), say which parts came
from it, and keep using its own knowledge and the web alongside it. A saved
item means *worth keeping*, not *read*. Install for Claude Code by linking it
into the user skills folder:

```bash
ln -s "$PWD/skill/kb-memory" ~/.claude/skills/kb-memory
```
