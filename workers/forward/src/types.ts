// JobDescriptor types are duplicated from workers/ingest/src/types.ts — the two
// workers are deliberately self-contained; revisit a shared package if a third
// consumer of these types appears.
export type ContentType = "text" | "voice" | "photo" | "video" | "document" | "url";
export type UrlSource = "instagram" | "youtube" | "blog" | "x" | "reddit" | "stackexchange" | "github" | "pdf";

export interface JobMedia {
  r2_key: string | null; // null at enqueue for URL jobs; the fetcher fills it in after fetch
  mime_type: string | null;
  size_bytes: number | null;
  duration_seconds: number | null;
}

export interface JobDescriptor {
  job_id: string;
  group_id: string | null;
  chat_id: number;
  message_id: number;
  time_received: string;
  content_type: ContentType;
  text?: string; // "text" only — Telegram caps messages at 4,096 chars, safe inline
  url?: string; // "url" only
  url_source?: UrlSource;
  media?: JobMedia; // binary types only — bytes are already in R2 before enqueue
  caption?: string; // media caption, or surrounding text for fanned-out URL jobs
  retry_count?: number; // retries scheduled so far — set on messages rebuilt by /retry; missing = 0
}

// States Cloud Run may report via POST /status. Earlier states belong to
// Worker 1 (received/queued), and `forwarded` is written by this worker itself
// after a successful push — never accepted from outside.
export const REPORTABLE_STATES = [
  "fetching",
  "retrying",
  "transcribing",
  "summarizing",
  "indexing",
  "saved",
  "failed",
] as const;
export type ReportableState = (typeof REPORTABLE_STATES)[number];

export interface StatusUpdate {
  job_id: string;
  state: ReportableState;
  r2_key?: string | null;
  error?: string | null;
  summary?: string | null; // sent with `indexing` for blog jobs: the graph episode text
}

export interface RetryRequest {
  job_id: string;
  delay_seconds: number;
}

export interface Env {
  DB: D1Database;
  JOB_QUEUE: Queue<JobDescriptor>;
  CLOUD_RUN_URL: string;
  CLOUD_RUN_SECRET: string;
  WORKER2_SHARED_SECRET: string;
  TELEGRAM_BOT_TOKEN: string;
}
