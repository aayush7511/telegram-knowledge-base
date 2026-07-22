import type { StatusUpdate } from "./types";

// Guarded transition: only advance queued → forwarded. Cloud Run can report a
// later state (via /status) before its /jobs response even reaches us, so an
// unconditional write here would regress the row.
export async function markForwarded(db: D1Database, jobId: string, at: string): Promise<void> {
  await db
    .prepare(
      "UPDATE jobs SET state = 'forwarded', updated_at = ?2 WHERE job_id = ?1 AND state = 'queued'",
    )
    .bind(jobId, at)
    .run();
}

// COALESCE keeps an existing r2_key when the update omits it (e.g. a state-only
// update after the Pi already filled it in); `error` is written as sent so a
// recovery update clears a stale error. Returns false when job_id is unknown.
export async function applyStatusUpdate(
  db: D1Database,
  u: StatusUpdate,
  at: string,
): Promise<boolean> {
  const { meta } = await db
    .prepare(
      "UPDATE jobs SET state = ?2, r2_key = COALESCE(?3, r2_key), error = ?4, updated_at = ?5 " +
        "WHERE job_id = ?1",
    )
    .bind(u.job_id, u.state, u.r2_key ?? null, u.error ?? null, at)
    .run();
  return meta.changes > 0;
}
