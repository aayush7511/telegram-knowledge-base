# Spec: Reply with what was saved (entities + facts), not a summary

**Type:** Logic · **Status:** Approved 2026-10-17 · **Owner:** Aayush · **Drafted:** 2026-10-17

## Overview

Today a URL or PDF save gets a Gemini summary as its Telegram reply, sent *before* the graph write. The summary is used for nothing else: the graph stores the full text (`main.py` comment at the `indexing` post). Under this spec, every save (URL, PDF file and text note) gets a reply **after** the graph write that shows what actually went into memory: the **entities** and the **facts** (relationships) Graphiti extracted. Gemini summarizing is no longer called.

## Decisions

| Question | Decision |
|---|---|
| Summarizing | **Dropped**: no Gemini call. Jobs go `fetching → indexing → saved` (URL/PDF) and `indexing → saved` (text) |
| Gemini code | **Left in place, unused** (`summarize.py`, its tests, the overload-retry path). Removed later in its own change |
| Which saves get the reply | **All**: URLs, PDF files and text notes (text notes got no reply before) |
| What it shows | **Header + entities + facts.** Facts are Graphiti's one-sentence `fact` strings |
| Header | **URL/PDF:** title, author/site line, link (same as today's header). **Text note:** none |
| Long items | **Cap with "+N more"**: at most **15 entities** and **10 facts**, each list followed by "+N more" when cut |
| Duplicates | **None shown**: repeated entities and facts are removed (first one kept) before capping. "+N more" counts unique items only |
| Long entities/facts | **Truncated** so the full 15 + 10 always fit in one message: entity ≤ **60** chars, fact ≤ **200** chars, title ≤ **200** chars, cut with "…" |
| Nothing extracted | Reply **"Saved — nothing extracted"** (after the header, if any) |
| Retry resume | **Always re-fetch** (decided 2026-10-17): the resume-from-R2-archive branch (from summarize-retry) is removed, so a retried job always starts at `fetching` (allowed from `retrying`). Without it, a resumed job would go `retrying → indexing`, which `canTransition` rejects. The archive is still written. Before deploying, check D1 for jobs sitting in `retrying` |
| Graph write fails | Reply **"Couldn't save this to memory"**. The job ends `failed` as today and can be re-driven from D1 |

## Expected behavior

**Data:** `graph.write_episode(...)` now **returns** what Graphiti extracted instead of `None`:
- `entities`: list of entity names (`EntityNode.name`), in Graphiti's order
- `facts`: list of fact sentences (`EntityEdge.fact`), in Graphiti's order

**Flow (URL / PDF):**
1. `fetching` (also on every retry; no resume from the archive).
2. `indexing`, then the graph write.
3. Reply with `format_extraction_reply(header, entities, facts)`.
4. `saved`.

**Flow (text note):** `indexing` → graph write → reply (no header) → `saved`.

**Reply format** (Telegram HTML; every piece of user or extracted text HTML-escaped):

```
<b>Title</b>
✍️ Author  ·  🌐 site
<link>

<b>Entities</b>
Zep, Graphiti, FalkorDB, … (up to 15, comma-separated)
+N more

<b>Facts</b>
• Zep built Graphiti.
• Graphiti stores graphs in FalkorDB.
… (up to 10)
+N more
```

- No header for text notes.
- An empty section is left out entirely (no "Entities" heading with nothing under it). If both are empty, the body is "Saved — nothing extracted".
- The whole message must stay under Telegram's 4,096-character limit.

## Rules and edge cases (Aayush to confirm or change)

- Order is Graphiti's. No sorting.
- "+N more" appears only when the list was cut. N = how many were left out.
- A reply that fails to send is logged and doesn't change the job: it still ends `saved`. This matches the status posts being best-effort.
- Only a **graph-write** failure gets "Couldn't save this to memory". Other failures (fetch errors, not supported) behave as today.
- Duplicates: two entities (or two facts) count as the same when they match **ignoring case and surrounding whitespace**. The first one's spelling is kept. Dedup happens before the cap.
- Truncation: an item over its limit is cut to `limit − 1` characters plus "…". Lengths count the text *before* HTML escaping (Telegram's 4,096 limit counts visible characters).
- Budget check: 15 × 60 + 10 × 200 + title 200 + headings ≈ 3,200 characters, which leaves ~900 for the author/site line and the link. A link longer than what's left is shown cut with "…" (the text only; the `href` stays whole).

## The core (Aayush, ~1–1.5h)

`telegram.format_extraction_reply(ro: ResponseObject | None, entities: list[str], facts: list[str]) -> str`. It's a pure function that does everything in "Reply format" above: the header (when `ro` is given), both capped sections with "+N more", the empty case, escaping, and staying under 4,096 characters.

Claude does the rest:
- `write_episode` returns the lists;
- the reorder in `process_source_job` / `process_text_job` (no summarize, reply after indexing);
- the failure reply;
- the `send` call;
- tests;
- updating the CLAUDE.md / README state-machine text;
- deploy.

## Acceptance tests

| # | Test | Expected |
|---|---|---|
| 1 | `test_reply_shows_header_entities_and_facts` | Title, author/site, link, then both sections |
| 2 | `test_text_note_reply_has_no_header` | `ro=None` → starts with the Entities section |
| 3 | `test_caps_entities_at_15_with_more` | 20 entities → 15 shown, "+5 more" |
| 4 | `test_caps_facts_at_10_with_more` | 13 facts → 10 shown, "+3 more" |
| 5 | `test_no_more_line_at_exact_cap` | Exactly 15 / 10 → no "+N more" |
| 6 | `test_empty_section_omitted` | Entities but no facts → no Facts heading |
| 7 | `test_nothing_extracted` | Both empty → "Saved — nothing extracted" |
| 8 | `test_escapes_html` | `<script>` in an entity or fact appears escaped |
| 9 | `test_reply_under_telegram_limit` | Long names and facts → message under 4,096 characters |
| 9a | `test_duplicates_removed_before_cap` | `["Zep", "zep ", "Graphiti"]` → "Zep, Graphiti". 20 entities with 5 duplicates → 15 shown, no "+N more" |
| 9b | `test_long_entity_and_fact_truncated` | 100-char entity → 59 chars + "…". 500-char fact → 199 chars + "…" |
| 9c | `test_full_caps_with_max_length_items_fit` | 15 max-length entities + 10 max-length facts + 200-char title + long link → under 4,096, and all 25 items shown |
| 10 | `test_url_job_skips_summarizing_and_replies_after_indexing` | No Gemini call. Statuses `fetching, indexing, saved`. Reply sent after the graph write |
| 11 | `test_text_job_replies` | Text note → a reply is sent, ends `saved` |
| 12 | `test_graph_failure_replies_couldnt_save` | Graph write raises → "Couldn't save this to memory", ends `failed` |
| 13 | `test_reply_send_failure_still_saved` | Telegram send raises → job still ends `saved` |
| 14 | `test_write_episode_returns_entities_and_facts` | Names and facts from Graphiti's result, in order |
| 15 | `test_retry_refetches_even_with_an_archive` | `retry_count` 1 with an archive in R2 → `fetching, indexing, saved`, page rendered again |

## Out of scope

- Removing the Gemini code (a later change).
- Section episodes (one long item = many graph writes). When that lands, the reply needs to combine the sections; that's its own spec.
- Showing which entities are new versus already in memory.
- Replies for the connector's `save_to_memory` beyond what the text-job path already does.

## How we know it works

- Tests 1–14 pass, plus Aayush's edge-case tests.
- After deploying, a real blog link gets a reply listing its entities and facts, with no Gemini call in the logs, and a text note gets one too.
