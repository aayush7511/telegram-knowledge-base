import path from "node:path";
import { defineConfig } from "vitest/config";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { Response as MiniflareResponse, type Request as MiniflareRequest } from "miniflare";

// Fake Cloud Run for integration tests. All other outbound traffic is blocked
// so tests can never hit the real network. Job ids containing "boom" get a 500
// to exercise the retry path; requests are recorded via the /__seen endpoint
// pattern isn't possible here, so tests assert effects (D1 state + ack/retry).
function fakeCloudRun(request: MiniflareRequest): Promise<MiniflareResponse> | MiniflareResponse {
  const url = new URL(request.url);
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
          outboundService: fakeCloudRun,
          bindings: {
            TEST_MIGRATIONS: migrations,
            CLOUD_RUN_URL: "https://fake-cloud-run.test",
            CLOUD_RUN_SECRET: "test-cloud-run-secret",
            WORKER2_SHARED_SECRET: "test-worker2-secret",
          },
        },
      }),
    ],
    test: {
      setupFiles: ["./test/apply-migrations.ts"],
    },
  };
});
