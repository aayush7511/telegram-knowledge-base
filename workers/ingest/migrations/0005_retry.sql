-- YouTube home worker (specs/youtube-home-worker.md). `url_source` lets a link
-- job's queue message be rebuilt from its row alone (Worker 2's /retry);
-- `retry_count` is how many retries have been scheduled for it.

ALTER TABLE jobs ADD COLUMN url_source TEXT;
ALTER TABLE jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
