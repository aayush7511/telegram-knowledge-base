-- Blog jobs persist the exact text written to the knowledge graph (title +
-- summary) when they enter `indexing`, so the graph can be rebuilt by replaying
-- D1 without re-fetching pages that may have changed. Text notes don't use it —
-- their content is already in `text`.

ALTER TABLE jobs ADD COLUMN summary TEXT;
