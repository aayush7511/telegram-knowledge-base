-- Inline message content: every job row now carries its content or a pointer
-- to it (text/url/caption inline — Telegram caps these at ≤4,096 chars;
-- binary media via r2_key). Makes jobs re-enqueueable from D1 alone and
-- failed rows self-describing.

ALTER TABLE jobs ADD COLUMN text TEXT;
ALTER TABLE jobs ADD COLUMN url TEXT;
ALTER TABLE jobs ADD COLUMN caption TEXT;
