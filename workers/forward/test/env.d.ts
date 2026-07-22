import type { D1Migration } from "@cloudflare/vitest-pool-workers";
import type { Env as WorkerEnv } from "../src/types";

// `env` from cloudflare:test is typed as Cloudflare.Env — extend it with our
// bindings plus the migrations injected by vitest.config.ts.
declare global {
  namespace Cloudflare {
    interface Env extends WorkerEnv {
      TEST_MIGRATIONS: D1Migration[];
    }
  }
}

export {};
