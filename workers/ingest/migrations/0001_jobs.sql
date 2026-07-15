-- Job tracking table (Option A from the design doc: state machine lives in one row).
-- Dedup of Telegram webhook retries is a state-aware SELECT on (chat_id, message_id),
-- not a UNIQUE constraint — multi-URL fan-out legitimately creates N rows per message.

CREATE TABLE jobs (
  job_id       TEXT PRIMARY KEY,
  chat_id      INTEGER NOT NULL,
  message_id   INTEGER NOT NULL,
  group_id     TEXT,
  content_type TEXT NOT NULL,
  state        TEXT NOT NULL DEFAULT 'received',
  error        TEXT,
  r2_key       TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE INDEX idx_jobs_chat_message ON jobs (chat_id, message_id);
