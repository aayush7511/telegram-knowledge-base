import path from "node:path";
import { defineConfig } from "vitest/config";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { Response as MiniflareResponse, type Request as MiniflareRequest } from "miniflare";

// Fake Cloud Run + fake Telegram for integration tests. All other outbound
// traffic is blocked so tests can never hit the real network.
//
// Cloud Run: job ids containing "boom" get a 500 to exercise the retry path.
// Telegram: every Bot API call is recorded and served back on
// GET https://api.telegram.org/__reactions (DELETE clears), so a test can see
// whether the worker actually sent the 👌. Chat id 666 gets a Telegram error to
// exercise the best-effort path.
const telegramCalls: unknown[] = [];

function fakeOutbound(request: MiniflareRequest): Promise<MiniflareResponse> | MiniflareResponse {
  const url = new URL(request.url);
  if (url.hostname === "api.telegram.org") {
    if (url.pathname === "/__reactions") {
      if (request.method === "DELETE") telegramCalls.length = 0;
      return MiniflareResponse.json(telegramCalls);
    }
    return (async () => {
      const body = (await request.json()) as { chat_id?: number };
      telegramCalls.push({ path: url.pathname, ...body });
      if (body.chat_id === 666) {
        return MiniflareResponse.json({ ok: false, description: "Bad Request: REACTION_INVALID" });
      }
      return MiniflareResponse.json({ ok: true, result: true });
    })();
  }
  if (url.hostname !== "fake-cloud-run.test") {
    return new MiniflareResponse("net connect disabled in tests", { status: 502 });
  }
  if (url.pathname !== "/jobs" || request.method !== "POST") {
    return new MiniflareResponse("not found", { status: 404 });
  }
  if (request.headers.get("X-KB-Secret") !== "test-cloud-run-secret") {
    return new MiniflareResponse("unauthorized", { status: 401 });
  }
  return (async () => {
    const job = (await request.json()) as { job_id?: string };
    if (job.job_id?.includes("boom")) {
      return new MiniflareResponse("stub exploded", { status: 500 });
    }
    return MiniflareResponse.json({ accepted: true, job_id: job.job_id });
  })();
}

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
            WORKER2_SHARED_SECRET: "test-worker2-secret",
            TELEGRAM_BOT_TOKEN: "test-token",
          },
        },
      }),
    ],
    test: {
      setupFiles: ["./test/apply-migrations.ts"],
    },
  };
});
