# Roadmap

Forward-looking plans by version. This tracks *what's planned*, not current state — see [README.md](README.md) for what's built today and [CLAUDE.md](CLAUDE.md) for architecture/rules.

Each version is scoped as **Goals** (outcomes this version must achieve), **Non-Goals** (explicitly out of scope, to prevent creep), and a **User Journey** (the single happy-path walkthrough, no edge cases or error states — those live in [CLAUDE.md](CLAUDE.md) working conventions or get filed as issues once a version is underway).

## v1 — Ingestion + blog pipeline (done)

**Goals**
- Any Telegram message reaches durable storage (D1 + R2) without being lost, even under retries
- A shared blog URL gets automatically fetched, summarized, and replied to with no manual step
- The pipeline never costs more than free-tier usage

**Non-Goals**
- Native voice/video/photo content is not transcribed or summarized yet (accepted and stored only)
- No knowledge graph — nothing is retrievable later, only stored
- No multi-user support — single owner chat only

**User Journey**
1. User pastes a blog URL into the Telegram chat
2. Bot reacts 👀 to acknowledge receipt
3. Bot fetches the page, extracts the article text and metadata, and summarizes it
4. Bot replies in the same thread with the summary

## v2 — Knowledge graph

Design decisions: [docs/design/v2.md](docs/design/v2.md)

**Goals**
- Every blog summary and plain-text note sent to the bot is written into a temporal knowledge graph, timestamped with when it was received
- A deliberate curation policy exists and is applied consistently before any graph writes happen
- Each job's D1 row shows whether it reached the graph (`indexing` → `saved` / `failed`) and holds enough content to rebuild its graph entry
- The bot's 👀 reaction on a message changes to 👌 once everything from that message is in the graph

**Non-Goals**
- No retrieval of any kind yet — no in-chat questions, no query connector (v3)
- No weekly global Leiden community recompute (v3)
- Native media is not written to the graph — it isn't transcribed until v3
- No cross-user graph sharing — the graph remains scoped to the single owner
- No automatic re-curation of already-ingested items if the policy changes later

**User Journey**
1. User pastes a blog URL into the Telegram chat
2. Bot reacts 👀, fetches and summarizes the page, and replies with the summary (as in v1)
3. Bot writes the summary into the knowledge graph as an episode timestamped with when the message was received
4. The job ends as `saved` in D1, the bot's 👀 on the message changes to 👌, and its entities and relationships are in FalkorDB ready for v3 retrieval

## v3 — Native media + retrieval

**Goals**
- A voice memo or video sent to the bot gets transcribed and summarized automatically
- Instagram/YouTube links get fetched (via the home Pi) and processed the same way as native media
- Pipeline states `fetching` / `transcribing` / `summarizing` reflect real work, not just the blog path
- The graph is retrievable: questions asked in the chat get answers grounded in past content, and a separate connector lets Claude / Claude Code query the graph directly
- A weekly global Leiden recompute corrects Graphiti's incremental community drift (design carried over in [docs/design/v2.md](docs/design/v2.md#moved-to-v3))

**Non-Goals**
- No live/streaming transcription — only complete, already-sent files
- No non-English or multi-language ASR tuning beyond Whisper's own defaults

**User Journey**
1. User sends a voice memo to the bot
2. Bot reacts 👀 to acknowledge receipt
3. Bot downloads the audio, transcribes it with Whisper, and summarizes the transcript
4. Bot replies in the same thread with the summary

## v4 — Reliability + UX polish

**Goals**
- Every ingested item ends in a clear, final Telegram reply — either a summary or a specific failure reason
- Raw media is cleaned up from storage once safely captured in the graph
- Long content (hour-long videos, large PDFs) is handled without failing outright

**Non-Goals**
- No new content types beyond what v1–v3 already accept
- No user-facing settings/configuration UI — still a single hardcoded owner and pipeline

**User Journey**
1. User sends a long video well beyond normal length
2. Bot chunks and processes it in parts instead of failing
3. Bot replies with a single combined summary once complete
4. Raw media is deleted from storage now that it's safely in the graph

## Future ideas (unscheduled)

- Revisit whether media albums (`media_group_id`) need stronger grouping once the graph exists, vs. today's independent-jobs-per-item approach
- A dedicated retrieval/query interface beyond inline conversational surfacing (e.g. on-demand recap or digest generation)
- Revisit a shared package for Worker 1/Worker 2 duplicated types if a third consumer appears

## Open questions to resolve before committing a version

None open for v2 — M0 settled the Graphiti model (`gpt-4.1-mini` at temperature 0), embeddings, and episode format; see [docs/design/v2.md](docs/design/v2.md#m0-results-2026-09-11).
