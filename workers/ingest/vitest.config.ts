import path from "node:path";
import { defineConfig } from "vitest/config";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { Response as MiniflareResponse, type Request as MiniflareRequest } from "miniflare";

// Fake Telegram Bot API for integration tests. All other outbound traffic is blocked
// so tests can never hit the real network.
function fakeTelegramApi(request: MiniflareRequest): MiniflareResponse {
  const url = new URL(request.url);
  if (url.hostname !== "api.telegram.org") {
    return new MiniflareResponse("net connect disabled in tests", { status: 502 });
  }
  if (url.pathname.endsWith("/getFile")) {
    return MiniflareResponse.json({ ok: true, result: { file_path: "voice/file_1.oga" } });
  }
  if (url.pathname.startsWith("/file/")) {
    return new MiniflareResponse("fake-ogg-bytes");
  }
  // sendMessage, setMessageReaction, ...
  return MiniflareResponse.json({ ok: true, result: {} });
}

export default defineConfig(async () => {
  const migrations = await readD1Migrations(path.join(import.meta.dirname, "migrations"));
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          outboundService: fakeTelegramApi,
          bindings: {
            TEST_MIGRATIONS: migrations,
            TELEGRAM_BOT_TOKEN: "test-token",
            TELEGRAM_WEBHOOK_SECRET: "test-secret",
            OWNER_CHAT_ID: "12345",
          },
        },
      }),
    ],
    test: {
      setupFiles: ["./test/apply-migrations.ts"],
    },
  };
});
