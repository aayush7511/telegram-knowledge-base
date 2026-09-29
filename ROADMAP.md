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

## v2 — Knowledge graph (done 2026-09-17)

Design decisions: [docs/design/v2.md](docs/design/v2.md)

**Goals**
- Every blog summary and plain-text note sent to the bot is written into a temporal knowledge graph, timestamped with when it was received
- A deliberate curation policy exists and is applied consistently before any graph writes happen
- Each job's D1 row shows whether it reached the graph (`indexing` → `saved` / `failed`) and holds enough content to rebuild its graph entry
- The bot's 👀 reaction on a message changes to 👌 once everything from that message is in the graph

**Non-Goals**
- No retrieval of any kind yet — no in-chat questions, no query connector (v3)
- No weekly global Leiden community recompute (v4)
- Native media is not written to the graph — it isn't transcribed until v4
- No cross-user graph sharing — the graph remains scoped to the single owner
- No automatic re-curation of already-ingested items if the policy changes later

**User Journey**
1. User pastes a blog URL into the Telegram chat
2. Bot reacts 👀, fetches and summarizes the page, and replies with the summary (as in v1)
3. Bot writes the summary into the knowledge graph as an episode timestamped with when the message was received
4. The job ends as `saved` in D1, the bot's 👀 on the message changes to 👌, and its entities and relationships are in FalkorDB ready for v3 retrieval

## v3 — Reach + retrieval

Design decisions: [docs/design/v3.md](docs/design/v3.md)

**Goals**
- Links to YouTube, X, Reddit, Stack Overflow, and GitHub get fetched and processed like blog URLs, using the text each source already has (captions, post text, answers) — one pinned tool per source, chosen from [Agent-Reach](https://github.com/Panniantong/Agent-Reach)'s research ([per-source tools](docs/design/v3.md#per-source-tools-mined-from-agent-reach-2026-09-26))
- PDFs are processed, both as links and as files sent in Telegram (text PDFs; scanned ones need OCR)
- A link to a page with nothing to remember (a profile, a search page, a login wall, an empty or blocked page) gets a "not supported" reply and is never saved
- `fetching` reflects real work for every URL source, not just blogs
- The graph is retrievable: an MCP connector lets Claude Code, Codex, claude.ai, and other MCP clients query the graph and save new things to it, and questions asked in the chat get answers grounded in past content

**Non-Goals**
- No audio transcription — a video with no captions, and any native voice memo or video, waits for v4
- The bot doesn't search the web — it ingests the links it's sent
- No public brain, public/private split, link fan-out, or Leiden recompute — moved to v4 (2026-09-29) to finish the MCP connector first

**User Journey**
1. User pastes a YouTube link into the Telegram chat
2. Bot reacts 👀, fetches the video's captions and metadata, summarizes them, and replies with the summary
3. The summary lands in the graph and the 👀 changes to 👌
4. Later, in Claude Code, the user asks what that video said about agent memory, and the answer comes from the graph

## v4 — Native media transcription + public brain

Design carried over from v3: [docs/design/v3.md#moved-to-v4](docs/design/v3.md#moved-to-v4)

**Goals**
- A voice memo or video sent to the bot gets transcribed and summarized automatically
- YouTube videos without usable captions get transcribed instead of skipped
- Instagram posts and reels get fetched (via the home Pi) and transcribed
- `transcribing` reflects real work
- Links inside a fetched post (an X post, a Reddit link post) become their own jobs, one level deep
- **Public brain**: a public, read-only web page where anyone can browse the graph built from what the owner reads and ask it questions, with answers grounded in it and linking back to the source articles
- Private content (text notes, voice memos) can never reach the public page — which side an item lands on is decided when it's written to the graph, not filtered out when the graph is read
- Public queries can't exceed the $0 constraint — a hard daily cap turns querying off rather than drawing down credit
- A weekly global Leiden recompute corrects Graphiti's incremental community drift (design carried over in [docs/design/v2.md](docs/design/v2.md#moved-to-v3))
- **What the owner knows, not just what they saved**: things that come up in conversations with Claude (through the MCP connector) about the owner's relationship to topics and sources — what they've actually read, how well they know a subject, what they're trying to do with it — get saved to the graph, linked to the topics and sources they're about. Retrieval then returns both the sources and the owner's intent and proficiency around them, so answers can meet them where they are. Follows from the v3 finding that a saved source signals *worth keeping*, not *read* (the `kb-memory` skill, [workers/mcp/skill/kb-memory/SKILL.md](workers/mcp/skill/kb-memory/SKILL.md))

**Non-Goals**
- No live/streaming transcription — only complete, already-sent files
- No non-English or multi-language ASR tuning beyond Whisper's own defaults
- Visitors to the public brain can't add content, sign in, or get a graph of their own — it's read-only and fed only by the owner
- The public brain never serves full article text — facts, entities, and links to the source only
- What the owner knows about themselves never reaches the public brain — it's the most private content the graph holds

**User Journey**
1. User sends a voice memo to the bot
2. Bot reacts 👀 to acknowledge receipt
3. Bot downloads the audio, transcribes it with Whisper, and summarizes the transcript
4. Bot replies in the same thread with the summary

**User Journey (public brain visitor)**
1. Visitor opens the public brain page and sees the graph of what the owner has been reading, most recent first
2. Visitor asks "what's been read about agent memory?"
3. Page answers from the public graph, citing the articles each fact came from, with links

**User Journey (what the owner knows)**
1. In Claude, the owner mentions they finished the Transformer paper but still find multi-head attention fuzzy, and want to build an agent with memory
2. Claude offers to remember that; the owner says yes
3. The graph now links the owner to the paper (read), to attention (partial understanding), and to agent memory (a goal)
4. Weeks later, asking "what should I learn next?", Claude finds both the saved sources and that context, and skips re-explaining the paper while going deeper on attention

## v5 — Reliability + UX polish

**Goals**
- Every ingested item ends in a clear, final Telegram reply — either a summary or a specific failure reason
- Raw media is cleaned up from storage once safely captured in the graph
- Long content (hour-long videos, large PDFs) is handled without failing outright

**Non-Goals**
- No new content types beyond what v1–v4 already accept
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
- Resolve short links (`bit.ly`, `t.co`, `tinyurl.com`) in Worker 1 before checking them, so the link rules see the real destination
- RSS subscriptions — auto-ingest new posts from followed sites. Needs a scheduled job and an exception to "sending is the curation act" ([v3 notes](docs/design/v3.md#per-source-tools-mined-from-agent-reach-2026-09-26))

## Open questions to resolve before committing a version

None open for v2 — M0 settled the Graphiti model (`gpt-4.1-mini` at temperature 0), embeddings, and episode format; see [docs/design/v2.md](docs/design/v2.md#m0-results-2026-09-11).

**v3** — open; tracked in [docs/design/v3.md](docs/design/v3.md#open-questions).

**v4, what the owner knows** — to resolve before building it:
- **Curation.** Capturing from conversations bends "sending is the curation act". Does Claude propose each item and the owner approves it (like the journey above), or does only an explicit "remember that I…" save anything? Silent automatic capture is the riskiest option: wrong inferences ("finished the paper" from "skimmed the paper") would quietly shape every later answer.
- **Shape in the graph.** Statements about the owner as their own episodes, with the owner as an entity linked to topic and source entities? Proficiency and goals change, which Graphiti's temporal edges (`valid_at` / `invalid_at`) already model: "fuzzy on attention" should be superseded by "understands attention", not sit beside it.
- **Tooling.** A dedicated MCP tool (a `remember_about_me`-style write with a clear description of what belongs there) vs. `save_to_memory` with a note; and the `kb-memory` skill updated to both read and propose these.
- **Privacy.** Always the private side of the public/private split, and part of that design rather than bolted on after.
