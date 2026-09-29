-- Tool-call caps for the MCP connector (kb-mcp): one row per counter per
-- window, e.g. "burst:29497410" (a UTC minute) or "search:2026-09-29" (a UTC
-- day). Rows past window_end are deleted as new calls come in.
CREATE TABLE usage (
  bucket     TEXT PRIMARY KEY,
  count      INTEGER NOT NULL,
  window_end TEXT NOT NULL
);
