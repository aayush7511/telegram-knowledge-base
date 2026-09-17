import { env } from "cloudflare:test";
import type { JobDescriptor } from "../src/types";

export function textJob(job_id: string, overrides: Partial<JobDescriptor> = {}): JobDescriptor {
  return {
    job_id,
    group_id: null,
    chat_id: 12345,
    message_id: 1,
    time_received: "2026-07-22T00:00:00.000Z",
    content_type: "text",
    text: "a note",
    ...overrides,
  };
}

// Seed a D1 row the way Worker 1 leaves it after enqueue (state=queued).
export async function seedJob(
  job: JobDescriptor,
  state = "queued",
  r2_key: string | null = null,
): Promise<void> {
  await env.DB.prepare(
    "INSERT INTO jobs (job_id, chat_id, message_id, group_id, content_type, state, r2_key, text, url, caption, created_at, updated_at) " +
      "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?11)",
  )
    .bind(
      job.job_id,
      job.chat_id,
      job.message_id,
      job.group_id,
      job.content_type,
      state,
      r2_key ?? job.media?.r2_key ?? null,
      job.text ?? null,
      job.url ?? null,
      job.caption ?? null,
      job.time_received,
    )
    .run();
}

export interface JobRow {
  job_id: string;
  state: string;
  r2_key: string | null;
  error: string | null;
  summary: string | null;
  updated_at: string;
}

export async function getRow(job_id: string): Promise<JobRow | null> {
  return env.DB.prepare("SELECT job_id, state, r2_key, error, summary, updated_at FROM jobs WHERE job_id = ?1")
    .bind(job_id)
    .first<JobRow>();
}
