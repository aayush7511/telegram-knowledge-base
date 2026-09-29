# telegram-knowledge-base

**A personal AI memory: send anything to a Telegram bot, and Claude can recall it later.**

Share a blog post, YouTube video, X thread, GitHub repo, Stack Overflow answer, PDF, or a plain note with the bot. It fetches the content, summarizes it, and writes it into a temporal knowledge graph. Weeks later, Claude (claude.ai, Desktop, Claude Code) or Codex searches that graph through an MCP connector and answers with the sources you saved, linked and dated.

Deployed and in daily use. Runs entirely on free tiers: **$0/month**.

```text
You, in Telegram:  https://lilianweng.github.io/posts/2023-06-23-agent/
Bot:               👀  → replies with a 3–5 sentence summary → 👌 once it's in the graph

You, in Claude:    "What should I read next on agent memory?"
Claude:            searches the graph → "From your knowledge base: you saved Lilian Weng's
                   'LLM Powered Autonomous Agents', which covers … start there, then …"
```

## Highlights

- **Agentic retrieval over your own data.** An MCP server with two task-shaped tools (`search_memory`, `save_to_memory`), OAuth 2.1 + Google sign-in, and per-tool rate limits. A companion [Claude skill](workers/mcp/skill/kb-memory/SKILL.md) teaches the model *when* personal context would change an answer, and that a saved item means "worth keeping", not "read".
- **Model choices backed by evals.** Before picking Graphiti's extraction model, an [offline eval](docs/design/v2.md#m0-results-2026-09-11) ran 8 real articles plus an unrelated control essay through two models. `gpt-5-nano` was faster but invented links between unrelated articles, so `gpt-4.1-mini` was pinned at temperature 0.
- **Context engineering, measured.** Moving URL/site/author out of the episode text removed every metadata-looking fake entity and took one abstract post from only its site and title to 9 real concepts. Retrieval testing on the live graph found a tokenizer bug that had silently disabled keyword search ([details](docs/design/v3.md#search-endpoint)).
- **Built for retries.** Telegram retries slow webhooks, so the receiver ACKs fast and queues the work. Jobs move through a validated state machine stored in D1, and every row can be re-enqueued on its own. Dedup is keyed on `(chat_id, message_id)`.
- **$0 by design.** Every infrastructure choice fits a free tier, with the trade-offs written down. Example: Direct VPC egress instead of a ~$5–15/month VPC connector.
- **248 tests**, with the Workers suites running inside the real `workerd` runtime rather than against mocked bindings.

## Architecture

![Architecture diagram](docs/architecture.svg)

| Component | Role | Stack |
|---|---|---|
| [`workers/ingest`](workers/ingest) | Telegram webhook: auth, dedup, classify, URL rules, media → R2, enqueue, 👀 | Cloudflare Worker, D1, R2, Queues (TypeScript) |
| [`workers/forward`](workers/forward) | Queue consumer → Cloud Run; the only path to D1 for status; 👀 → 👌 | Cloudflare Worker (TypeScript) |
| [`services/orchestrator`](services/orchestrator) | Fetch → extract → summarize → reply → write to the graph; `/search` for MCP | Cloud Run, FastAPI, Playwright, Trafilatura, Graphiti (Python) |
| [`workers/mcp`](workers/mcp) | MCP connector for Claude and Codex, OAuth + Google sign-in, usage caps | Cloudflare Worker, MCP SDK v2, workers-oauth-provider |
| [`infra/falkordb`](infra/falkordb) | The knowledge-graph store, private to the VPC | FalkorDB in Docker on a GCE e2-micro |

Every component has its own README with local dev and deploy steps. The reasoning behind each decision is in the [architecture decision table](CLAUDE.md#key-architecture-decisions-and-why).

### Job lifecycle

```text
received → queued → forwarded → fetching → summarizing → indexing → saved
                                      └──────────── failed (from any state, re-drivable) ─┘
```

State lives in D1, not in the queue message. Transitions are validated (forward-only; `saved` is terminal), so a retried or out-of-order status update can never move a job backwards.

## What it handles today

| Input | How it's read |
|---|---|
| Blog posts and articles | Headless Chromium render → Trafilatura text + structured metadata |
| YouTube | Captions via Supadata (YouTube blocks Cloud Run's IPs; [spike](spikes/youtube-transcript)) |
| X / Twitter | FxTwitter: full threads, long-form Articles, quoted posts |
| Stack Exchange | Question + accepted (or top-voted) answer via the official API |
| GitHub | Repo README, issue/PR description, gist files |
| PDFs | Links (including arXiv) and files sent in Telegram, via pypdf |
| Text notes | Written to the graph directly |

Links with nothing worth remembering (profiles, channels, playlists, login walls, bot-challenge pages, empty pages) get a "not supported" reply and are never saved. The fetcher refuses private and internal addresses.

## Evaluation and findings

Big decisions were settled with a spike or an eval first. The results live next to the design:

- **Extraction model** ([M0](docs/design/v2.md#m0-results-2026-09-11)): entities, facts, false cross-episode links, schema errors, tokens, latency, and idempotency when re-adding an episode, compared for `gpt-4.1-mini` vs. `gpt-5-nano`.
- **Episode format**: metadata header vs. title + summary, then summary vs. full article text (the full text recovers more facts at ~2.3× the tokens; [spike](spikes/full-article-episode)).
- **Retrieval** ([search endpoint](docs/design/v3.md#search-endpoint)): relevant and unrelated facts overlap in cosine similarity (0.35–0.46 vs. 0.25–0.41), so no similarity cutoff works. A cross-encoder reranker was tried and rejected as too strict. The calling model judges relevance instead.
- **Prompting failure worth remembering**: a forceful prompt to strip newsletter sponsor sections invented a connection between a sponsor and a real person, so it never shipped.
- Every production surprise and its fix is logged in [Problems encountered and fixes](docs/design/v2.md#problems-encountered-and-fixes).

## Tech stack

**LLMs**: OpenAI `gpt-4.1-mini` + `text-embedding-3-small` (graph extraction and search), Gemini `gemini-3.6-flash` (summaries); Groq Whisper planned for speech-to-text.
**Graph**: Graphiti (temporal knowledge graph: facts carry `valid_at` / `invalid_at`), FalkorDB.
**Edge**: Cloudflare Workers, Queues, D1 (SQLite), R2, KV; MCP (Streamable HTTP, stateless) with OAuth 2.1, PKCE, and dynamic client registration.
**Backend**: Python, FastAPI, Playwright, Trafilatura, pypdf on Google Cloud Run (scales to zero, request-based billing).
**Testing**: Vitest + `@cloudflare/vitest-pool-workers`, pytest.

## Run it locally

Prerequisites: Node.js ≥ 22, Python 3.11, a Cloudflare account, and a bot token from [@BotFather](https://t.me/BotFather).

```bash
git clone https://github.com/aayush7511/telegram-knowledge-base.git
cd telegram-knowledge-base

# Workers (run in each of workers/ingest, workers/forward, workers/mcp)
cd workers/ingest && npm install && npm test

# Orchestrator
cd ../../services/orchestrator && pip install -r requirements.txt pytest && pytest
```

Provisioning, secrets, deploys, and webhook registration are covered step by step in each component's README, starting with [workers/ingest](workers/ingest/README.md).

## Roadmap

| Version | Status | Scope |
|---|---|---|
| v1 | ✅ | Ingestion pipeline and blog summaries |
| v2 | ✅ | Temporal knowledge graph (Graphiti + FalkorDB) |
| v3 | 🚧 | More sources ✅, MCP connector ✅; Reddit and in-chat questions still to come |
| v4 | Planned | Voice/video transcription (Whisper), Instagram via a home Pi, a public read-only "brain" page, and remembering what the owner knows, not just what they saved |
| v5 | Planned | Reliability polish, long-content chunking, raw-media cleanup |

Goals, non-goals, and user journeys per version: [ROADMAP.md](ROADMAP.md). Design docs: [v2](docs/design/v2.md), [v3](docs/design/v3.md).
