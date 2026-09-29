import path from "node:path";
import { defineConfig } from "vitest/config";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { Response as MiniflareResponse, type Request as MiniflareRequest } from "miniflare";

// Fakes for everything kb-mcp talks to, so tests never hit the real network:
//
// - Google (token + userinfo): the authorization code picks the account —
//   "code-owner" signs in as the owner, anything else as a stranger.
// - Cloud Run /search: checks X-KB-Secret; the query "boom" gets a 500.
// - Worker 1 (the INGEST service binding): an auxiliary Worker named kb-ingest
//   with the same IngestRpc.createJobs shape. It rejects instagram.com links,
//   throws on "boom", and answers "whoami" by rejecting it with the client name
//   it was given as the reason, so tests can see which name was passed. The real createJobs is tested in
//   workers/ingest/test/save.test.ts.
export const OWNER_SUB = "google-owner-sub";

async function fakeOutbound(request: MiniflareRequest): Promise<MiniflareResponse> {
  const url = new URL(request.url);
  if (url.href === "https://oauth2.googleapis.com/token") {
    const body = new URLSearchParams(await request.text());
    if (!body.get("code_verifier")) return MiniflareResponse.json({ error: "invalid_grant" }, { status: 400 });
    return MiniflareResponse.json({ access_token: `google-token-for-${body.get("code")}`, token_type: "Bearer" });
  }
  if (url.href === "https://openidconnect.googleapis.com/v1/userinfo") {
    const owner = request.headers.get("Authorization") === "Bearer google-token-for-code-owner";
    return MiniflareResponse.json(
      owner ? { sub: OWNER_SUB, email: "owner@example.com" } : { sub: "stranger", email: "stranger@example.com" },
    );
  }
  if (url.hostname === "fake-cloud-run.test" && url.pathname === "/search") {
    if (request.headers.get("X-KB-Secret") !== "test-cloud-run-secret") {
      return new MiniflareResponse("unauthorized", { status: 401 });
    }
    const { query, limit } = (await request.json()) as { query: string; limit: number };
    if (query === "boom") return new MiniflareResponse("stub exploded", { status: 500 });
    return MiniflareResponse.json({
      results: [
        {
          fact: `A fact about ${query} (limit ${limit})`,
          valid_at: "2026-09-19T02:39:47+00:00",
          invalid_at: null,
          sources: [
            { title: "An Article", kind: "blog", url: "https://example.com/a", saved_at: "2026-09-19T02:39:47+00:00" },
          ],
        },
      ],
    });
  }
  return new MiniflareResponse("net connect disabled in tests", { status: 502 });
}

const FAKE_INGEST = `
import { WorkerEntrypoint } from "cloudflare:workers";
export class IngestRpc extends WorkerEntrypoint {
  async createJobs(content, clientName) {
    if (content.includes("boom")) throw new Error("D1 is down");
    if (content === "whoami") return { jobs: [], rejected: [{ url: "whoami", reason: clientName }] };
    const links = content.split(/\\s+/).filter((w) => w.startsWith("https://"));
    const rejected = links.filter((u) => u.includes("instagram.com")).map((url) => ({ url, reason: "Instagram profile, not a post" }));
    const accepted = links.filter((u) => !u.includes("instagram.com"));
    const jobs = links.length === 0
      ? [{ job_id: "job-0", url: null }]
      : accepted.map((url, i) => ({ job_id: "job-" + i, url }));
    return { jobs, rejected };
  }
}
export default { fetch() { return new Response("fake kb-ingest"); } };
`;

export default defineConfig(async () => {
  // Schema truth lives with Worker 1 — reuse its migrations directly.
  const migrations = await readD1Migrations(path.join(import.meta.dirname, "../ingest/migrations"));
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          outboundService: fakeOutbound,
          bindings: {
            TEST_MIGRATIONS: migrations,
            CLOUD_RUN_URL: "https://fake-cloud-run.test",
            CLOUD_RUN_SECRET: "test-cloud-run-secret",
            GOOGLE_CLIENT_ID: "test-google-client",
            GOOGLE_CLIENT_SECRET: "test-google-secret",
            OWNER_GOOGLE_SUB: OWNER_SUB,
          },
          workers: [
            {
              name: "kb-ingest",
              modules: [{ type: "ESModule", path: "index.mjs", contents: FAKE_INGEST }],
              compatibilityDate: "2026-07-01",
            },
          ],
        },
      }),
    ],
    test: {
      setupFiles: ["./test/apply-migrations.ts"],
    },
  };
});
