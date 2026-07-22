import type { Env, JobDescriptor, ReportableState, StatusUpdate } from "./types";
import { REPORTABLE_STATES } from "./types";
import { applyStatusUpdate, markForwarded } from "./db";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export default {
  // Queue consumer: push each job descriptor to Cloud Run. Per-message
  // ack/retry so one failing job doesn't recycle its batch-mates; retry
  // pacing comes from retry_delay in wrangler.jsonc. At-least-once delivery
  // is safe — Cloud Run keys work on job_id.
  async queue(batch, env, _ctx): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;
      try {
        const resp = await fetch(`${env.CLOUD_RUN_URL}/jobs`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "X-KB-Secret": env.CLOUD_RUN_SECRET,
          },
          body: JSON.stringify(job),
        });
        if (!resp.ok) {
          console.error(`forward failed job=${job.job_id} status=${resp.status} body=${await resp.text()}`);
          msg.retry();
          continue;
        }
        await markForwarded(env.DB, job.job_id, new Date().toISOString());
        msg.ack();
      } catch (err) {
        console.error(`forward errored job=${job.job_id}`, err instanceof Error ? (err.stack ?? err.message) : err);
        msg.retry();
      }
    }
  },

  // Status-update endpoint: Cloud Run's only path to D1. Shared-secret auth —
  // this is a public workers.dev URL otherwise.
  async fetch(request, env): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (request.method !== "POST" || pathname !== "/status") {
      return new Response("not found", { status: 404 });
    }
    if (request.headers.get("X-KB-Secret") !== env.WORKER2_SHARED_SECRET) {
      return new Response("unauthorized", { status: 401 });
    }

    let update: StatusUpdate;
    try {
      update = await request.json<StatusUpdate>();
    } catch {
      return json({ ok: false, error: "invalid JSON body" }, 400);
    }
    if (!update.job_id || typeof update.job_id !== "string") {
      return json({ ok: false, error: "job_id required" }, 400);
    }
    if (!REPORTABLE_STATES.includes(update.state as ReportableState)) {
      return json(
        { ok: false, error: `state must be one of: ${REPORTABLE_STATES.join(", ")}` },
        400,
      );
    }

    const found = await applyStatusUpdate(env.DB, update, new Date().toISOString());
    if (!found) return json({ ok: false, error: `unknown job_id ${update.job_id}` }, 404);
    return json({ ok: true });
  },
} satisfies ExportedHandler<Env, JobDescriptor>;
