import type { JobDescriptor } from "./types";

export interface ExistingJob {
  job_id: string;
  state: string;
}

export async function findJobsForMessage(
  db: D1Database,
  chat_id: number,
  message_id: number,
): Promise<ExistingJob[]> {
  const { results } = await db
    .prepare("SELECT job_id, state FROM jobs WHERE chat_id = ?1 AND message_id = ?2")
    .bind(chat_id, message_id)
    .all<ExistingJob>();
  return results;
}

export async function deleteJobs(db: D1Database, jobIds: string[]): Promise<void> {
  if (jobIds.length === 0) return;
  await db.batch(jobIds.map((id) => db.prepare("DELETE FROM jobs WHERE job_id = ?1").bind(id)));
}

export async function insertJobs(db: D1Database, jobs: JobDescriptor[]): Promise<void> {
  await db.batch(
    jobs.map((j) =>
      db
        .prepare(
          "INSERT INTO jobs (job_id, chat_id, message_id, group_id, content_type, state, r2_key, text, url, caption, created_at, updated_at) " +
            "VALUES (?1, ?2, ?3, ?4, ?5, 'received', ?6, ?7, ?8, ?9, ?10, ?10)",
        )
        .bind(
          j.job_id,
          j.chat_id,
          j.message_id,
          j.group_id,
          j.content_type,
          j.media?.r2_key ?? null,
          j.text ?? null,
          j.url ?? null,
          j.caption ?? null,
          j.time_received,
        ),
    ),
  );
}

export async function markQueued(db: D1Database, jobIds: string[], at: string): Promise<void> {
  await db.batch(
    jobIds.map((id) =>
      db.prepare("UPDATE jobs SET state = 'queued', updated_at = ?2 WHERE job_id = ?1").bind(id, at),
    ),
  );
}
