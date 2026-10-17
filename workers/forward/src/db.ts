import type { JobDescriptor, StatusUpdate } from "./types";

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

// The pipeline's forward-only order. A job may skip states (text notes go
// forwarded → indexing) but never move backwards. `failed` isn't ranked: it can
// be entered from any non-terminal state, and left again when a job is re-driven
// from D1 and Cloud Run starts reporting progress on the retry. `retrying` isn't
// ranked either: a job waits there from `fetching` (YouTube home worker
// unreachable, specs/youtube-home-worker.md) or `summarizing` (Gemini
// overloaded, specs/summarize-retry.md), and leaves back to `fetching` or
// `summarizing` (the only allowed backward steps) or to `failed`.
const STATE_ORDER = [
  "received",
  "verified",
  "queued",
  "forwarded",
  "fetching",
  "transcribing",
  "summarizing",
  "indexing",
  "saved",
];

export function canTransition(from: string, to: string): boolean {
  if (from === "saved") return false; // terminal
  if (to === "failed" || from === "failed") return true;
  if (to === "retrying") return from === "fetching" || from === "summarizing";
  if (from === "retrying") return to === "fetching" || to === "summarizing";
  return STATE_ORDER.indexOf(to) > STATE_ORDER.indexOf(from);
}

export type ApplyResult =
  | { ok: true; chat_id: number; message_id: number }
  | { ok: false; reason: "not_found" }
  | { ok: false; reason: "invalid_transition"; from: string };

// COALESCE keeps an existing r2_key/summary when the update omits them (e.g. a
// state-only update after a fetch already filled r2_key in); `error` is written
// as sent so a recovery update clears a stale error. The UPDATE is a
// compare-and-set on the state the transition was validated against, so two
// concurrent updates can't both get through.
export async function applyStatusUpdate(
  db: D1Database,
  u: StatusUpdate,
  at: string,
): Promise<ApplyResult> {
  const row = await db
    .prepare("SELECT state, chat_id, message_id FROM jobs WHERE job_id = ?1")
    .bind(u.job_id)
    .first<{ state: string; chat_id: number; message_id: number }>();
  if (!row) return { ok: false, reason: "not_found" };
  if (!canTransition(row.state, u.state)) return { ok: false, reason: "invalid_transition", from: row.state };

  const { meta } = await db
    .prepare(
      "UPDATE jobs SET state = ?2, r2_key = COALESCE(?3, r2_key), summary = COALESCE(?4, summary), " +
        "error = ?5, updated_at = ?6 WHERE job_id = ?1 AND state = ?7",
    )
    .bind(u.job_id, u.state, u.r2_key ?? null, u.summary ?? null, u.error ?? null, at, row.state)
    .run();
  if (meta.changes === 0) return { ok: false, reason: "invalid_transition", from: row.state };
  return { ok: true, chat_id: row.chat_id, message_id: row.message_id };
}

// True once every job from the same Telegram message is saved — a multi-link
// message fans out into several jobs, and only the last one to finish knows
// the message is complete.
export async function allJobsSaved(db: D1Database, chat_id: number, message_id: number): Promise<boolean> {
  const row = await db
    .prepare(
      "SELECT COUNT(*) AS total, SUM(state = 'saved') AS saved FROM jobs WHERE chat_id = ?1 AND message_id = ?2",
    )
    .bind(chat_id, message_id)
    .first<{ total: number; saved: number }>();
  return row !== null && row.total > 0 && row.saved === row.total;
}

interface JobRow {
  job_id: string;
  group_id: string | null;
  chat_id: number;
  message_id: number;
  created_at: string;
  content_type: JobDescriptor["content_type"];
  text: string | null;
  url: string | null;
  url_source: JobDescriptor["url_source"] | null;
  caption: string | null;
  r2_key: string | null;
  retry_count: number;
}

// Count one more scheduled retry and rebuild the job's queue message from its
// row alone (the no-DLQ rule: every row can be re-enqueued from D1). Null when
// the job doesn't exist. Media fields beyond r2_key aren't stored, so they come
// back null — only YouTube links are retried today.
export async function prepareRetry(db: D1Database, jobId: string, at: string): Promise<JobDescriptor | null> {
  const row = await db
    .prepare(
      "UPDATE jobs SET retry_count = retry_count + 1, updated_at = ?2 WHERE job_id = ?1 " +
        "RETURNING job_id, group_id, chat_id, message_id, created_at, content_type, text, url, url_source, caption, r2_key, retry_count",
    )
    .bind(jobId, at)
    .first<JobRow>();
  if (!row) return null;
  const job: JobDescriptor = {
    job_id: row.job_id,
    group_id: row.group_id,
    chat_id: row.chat_id,
    message_id: row.message_id,
    time_received: row.created_at,
    content_type: row.content_type,
    retry_count: row.retry_count,
  };
  if (row.text !== null) job.text = row.text;
  if (row.url !== null) job.url = row.url;
  if (row.url_source !== null) job.url_source = row.url_source;
  if (row.caption !== null) job.caption = row.caption;
  if (row.r2_key !== null) job.media = { r2_key: row.r2_key, mime_type: null, size_bytes: null, duration_seconds: null };
  return job;
}
