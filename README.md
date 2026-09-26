# telegram-knowledge-base

A personal AI memory tool. Send anything to a Telegram bot — text notes, voice memos, links, videos, documents — and it gets ingested, transcribed/summarized, and stored in a temporal knowledge graph that resurfaces relevant context later.

## Idea

Content flows in through a single Telegram chat and out into a knowledge graph with temporal awareness (when a project started, when you learned something). Later conversations surface related past context automatically. Core constraints: **$0/month in recurring service fees** (free tiers + one-time Raspberry Pi hardware), transcription as fast as possible, cheap/local models where needed.

Full architecture and every design decision: [convo_summary.md](convo_summary.md).

```
Telegram → CF Worker 1 (validate/classify/store) → CF Queue → CF Worker 2 → Google Cloud Run
                                                                                │
              Groq (Whisper ASR + Llama summarize) ← Raspberry Pi (yt-dlp) ←────┤
                                                                                ↓
                                              Graphiti + FalkorDB knowledge graph
```

## Tech Stack

**Live today**
- **Cloudflare Workers** — webhook receiver + queue-consumer/forwarder (TypeScript, Wrangler)
- **Cloudflare Queues** — job transport between pipeline stages
- **Cloudflare R2** — raw media storage (2-day lifecycle on `raw-media/`)
- **Cloudflare D1** — SQLite job tracking + inline message content
- **Telegram Bot API** — the single ingestion channel (webhook + secret token)
- **Vitest + @cloudflare/vitest-pool-workers** — tests run inside real workerd
- **Google Cloud Run** — processing orchestrator, deployed as an auth-checking stub (Python + FastAPI, request-based billing, scales to zero); real processing not built yet

**Planned**
- **Groq API** — Whisper large-v3-turbo ASR + Llama 3.3 70B summarization (free tiers)
- **Raspberry Pi** — residential-IP fetcher running yt-dlp + PO-token provider
- **Graphiti + FalkorDB** — self-hosted temporal knowledge graph (Docker on the Pi)

## Installation

Prereqs: Node.js ≥ 20, a Cloudflare account, a Telegram bot token from @BotFather.

```bash
git clone https://github.com/aayush7511/telegram-knowledge-base.git
cd telegram-knowledge-base/workers/ingest
npm install

# local dev
cp .dev.vars.example .dev.vars   # or create .dev.vars with:
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_WEBHOOK_SECRET=...   (any random string you invent)
#   OWNER_CHAT_ID=...             (your numeric Telegram id)
npx wrangler d1 migrations apply kb-jobs --local
npm test          # 49 tests: pure logic + workerd integration
npm run dev       # local server on :8787
```

Cloud provisioning, secrets, deploy, and webhook registration: see [workers/ingest/README.md](workers/ingest/README.md).

## Features in Progress

Everything currently built. All of this is **implemented, tested (111 tests), deployed, and verified live**. Messages flow Telegram → queue → Worker 2 → Cloud Run → knowledge graph, and status updates flow back into D1 — but Cloud Run does no real processing yet.

**Worker 1 — `kb-ingest` (Telegram webhook receiver), deployed on workers.dev**
- Webhook auth: `X-Telegram-Bot-Api-Secret-Token` check, 401 otherwise
- Single-user allowlist: updates from any chat but `OWNER_CHAT_ID` are silently ACKed
- Webhook-retry dedup on `(chat_id, message_id)`, state-aware: fully-ingested messages are skipped; partial attempts (inserted but never enqueued) are deleted and reprocessed
- Content classification: `text` / `voice` (incl. audio files) / `video` (incl. video notes) / `photo` / `document` / `url`; unsupported types get an explanatory reply
- Layer-1 URL validation by shape: accepts IG `/reel/`, `/reels/`, `/p/`, `/tv/`, YouTube `/watch?v=`, `/shorts/`, `/live/`, `youtu.be`; rejects profiles, channels, playlists, stories, comment permalinks (with a reply listing each rejected URL and why); any other http(s) URL is accepted as `blog`
- Multi-URL fan-out: one job per accepted URL sharing a generated `group_id`; surrounding prose carried as `caption`; URLs glued together without whitespace are split on scheme boundaries
- Native media ingestion: 20MB Bot API cap enforced (with size-specific reply), largest photo size selected, bytes streamed from Telegram into R2 at `raw-media/{job_id}.{ext}`, mime→extension mapping
- Media albums: each item is its own job; Telegram's `media_group_id` passes through as `group_id` (no buffering)
- D1 `jobs` table: full job row per message with state machine (`received` → `queued`), plus inline content columns (`text`, `url`, `caption`) so every row carries its content or a pointer to it (`r2_key`) — jobs are re-enqueueable from D1 alone
- Job descriptors enqueued to the `kb-jobs` queue (single `send` or `sendBatch`)
- Ack UX: 👀 reaction on accepted messages; permanent rejections reply + HTTP 200 (no Telegram retry); transient failures return 500 so Telegram redelivers safely
- Provisioned infra: `kb-jobs` queue, `kb-raw-media` R2 bucket (2-day expiry lifecycle rule on `raw-media/`), `kb-jobs` D1 database (2 migrations applied), secrets in Wrangler, webhook registered with `allowed_updates=["message"]`

**Worker 2 — `kb-forward` (queue consumer + D1 proxy), deployed on workers.dev**
- `queue()` consumer on `kb-jobs` (one job at a time: batch 1, concurrency 1; 5 retries, 60s retry delay): POSTs each job descriptor to Cloud Run `/jobs` with shared-secret auth, marks the D1 row `forwarded` on success
- Per-message ack/retry — a failing job is redelivered without recycling its batch-mates
- `POST /status` — Cloud Run's only path to D1: `{job_id, state, r2_key?, error?, summary?}`, secret-authed; validates transitions against the pipeline order (forward-only, `saved` terminal, 409 otherwise), COALESCEs `r2_key`/`summary`, 404s unknown jobs
- 👀 → 👌: when the last job from a Telegram message reaches `saved`, swaps Worker 1's 👀 for 👌 (best-effort)
- No DLQ by choice: dropped messages stay recoverable because every D1 row carries its content
- Tests reuse Worker 1's migrations as the single schema truth; Cloud Run is faked in-test

**Cloud Run — `kb-orchestrator` (processing orchestrator), deployed on us-central1**
- `POST /jobs` intake with `X-KB-Secret` shared-secret auth (401 otherwise); the whole pipeline runs synchronously inside the request (request-based billing, scales to zero, `--max-instances 1`, `--timeout 600`)
- Blog URLs: Playwright render → Trafilatura text + extruct metadata → cleaned text archived to R2 (`articles/{job_id}.txt`) → Gemini summary → Telegram reply → Graphiti episode (title + summary; URL/site/author as provenance) → FalkorDB
- Text notes: straight into the graph as an episode, no reply — the 👌 is the acknowledgement
- Graphiti runs `gpt-4.1-mini` (both slots, temperature 0) + `text-embedding-3-small` on OpenAI's complimentary data-sharing tokens; episodes are keyed by `job_id` so reprocessing never duplicates
- Status updates to Worker 2 at each stage (`fetching`/`summarizing`/`indexing`/`saved`/`failed`); the `indexing` post carries the episode text so the graph can be rebuilt from D1
- See [services/orchestrator/README.md](services/orchestrator/README.md)

**FalkorDB — `falkordb` VM (knowledge-graph store), GCE e2-micro in us-central1**
- FalkorDB in Docker on Container-Optimized OS, data on the persistent stateful partition with append-only persistence; survives reboots
- Reached by Cloud Run over Direct VPC egress on the internal IP — port 6379 is never open to the internet; password-protected
- One graph, `second-brain`, holding Episodic nodes, Entity nodes, `MENTIONS` and temporal `RELATES_TO` edges, with range + full-text indexes and stored embeddings for v3 retrieval
- See [infra/falkordb/README.md](infra/falkordb/README.md)

## Features Not Started

Planned (see [ROADMAP.md](ROADMAP.md)) but with zero code written:

- **Raspberry Pi fetcher** — polls for fetch jobs over outbound HTTPS (no port-forwarding), runs yt-dlp with dedicated-account cookies + `bgutil-ytdlp-pot-provider` for YouTube PO tokens, normalizes audio with ffmpeg, uploads to R2; Layer-2 URL validation (e.g. IG `/p/` posts that turn out to be image-only) with fail/reroute
- **Groq integration** — Whisper large-v3-turbo transcription (fallback: local faster-whisper distil-large-v3 int8); Llama 3.3 70B summarization/curation; YouTube auto-caption shortcut to skip ASR when quality suffices
- **Knowledge-graph retrieval** — in-chat questions answered from the graph, a connector for Claude / Claude Code, and the weekly Leiden community recompute (v3)
- **Pipeline states for media** — `fetching` becomes real once Instagram/YouTube are fetched (v3) and `transcribing` once native media is transcribed (v4); text notes and blog URLs already run the full state machine
- **Ingestion-complete UX** — final Telegram reply with a short summary of what was captured (or a failure message naming the stage that died)
- **Raw media cleanup** — explicit R2 delete after graph ingestion (`saved`); today only the 2-day lifecycle rule exists
- **`job_events` audit table** — append-only per-stage timing/audit trail alongside `jobs`
- **Long-content handling** — chunked/map-reduce summarization for hour-long videos and large PDFs; size caps with "too big to ingest" messaging
