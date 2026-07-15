export type ContentType = "text" | "voice" | "photo" | "video" | "document" | "url";
export type UrlSource = "instagram" | "youtube" | "blog";

export interface JobMedia {
  r2_key: string | null; // null at enqueue for URL jobs; the Pi fills it in after fetch
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
}

export interface Env {
  JOB_QUEUE: Queue<JobDescriptor>;
  RAW_MEDIA: R2Bucket;
  DB: D1Database;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_WEBHOOK_SECRET: string;
  OWNER_CHAT_ID: string;
}
