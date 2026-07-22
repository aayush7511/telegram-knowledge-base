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

Everything currently built. All of this is **implemented, tested (69 tests), deployed, and verified live**. Messages now flow Telegram → queue → Worker 2 → Cloud Run and status updates flow back into D1 — but Cloud Run does no real processing yet.

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
- `queue()` consumer on `kb-jobs` (batch 5, 5 retries, 60s retry delay): POSTs each job descriptor to Cloud Run `/jobs` with shared-secret auth, marks the D1 row `forwarded` on success
- Per-message ack/retry — a failing job is redelivered without recycling its batch-mates
- `POST /status` — Cloud Run's only path to D1: `{job_id, state, r2_key?, error?}`, secret-authed; validates state against the pipeline machine, COALESCEs `r2_key`, 404s unknown jobs
- No DLQ by choice: dropped messages stay recoverable because every D1 row carries its content
- Tests reuse Worker 1's migrations as the single schema truth; Cloud Run is faked in-test

**Cloud Run stub — `kb-orchestrator` (processing orchestrator, contract only), deployed on us-central1**
- `POST /jobs` intake with `X-KB-Secret` shared-secret auth (401 otherwise); logs the descriptor, no processing yet
- Status-update callback to Worker 2 implemented per contract (`{job_id, state, r2_key, error}` + secret header); no-op until Worker 2 exists
- Deployed via source buildpacks, request-based billing, scales to zero, `--max-instances 1` free-tier cap
- See [services/orchestrator/README.md](services/orchestrator/README.md)

## Features Not Started

Everything designed (see [convo_summary.md](convo_summary.md)) but with zero code written:

- **Cloud Run orchestrator (processing)** — the deployed stub does no work yet; still to build: handle `text`/`blog` jobs directly (HTTP fetch + readability extraction + LLM summarization), pull native media from R2 via S3-compatible API and send it to Groq for ASR, delegate Instagram/YouTube URLs to the Pi
- **Raspberry Pi fetcher** — polls for fetch jobs over outbound HTTPS (no port-forwarding), runs yt-dlp with dedicated-account cookies + `bgutil-ytdlp-pot-provider` for YouTube PO tokens, normalizes audio with ffmpeg, uploads to R2; Layer-2 URL validation (e.g. IG `/p/` posts that turn out to be image-only) with fail/reroute
- **Groq integration** — Whisper large-v3-turbo transcription (fallback: local faster-whisper distil-large-v3 int8); Llama 3.3 70B summarization/curation; YouTube auto-caption shortcut to skip ASR when quality suffices
- **Knowledge graph** — self-hosted Graphiti + FalkorDB via Docker on the Pi; ingestion of transcripts/summaries with temporal metadata; retrieval that surfaces related past content in conversation
- **Pipeline state progression** — `forwarded` / `fetching` / `transcribing` / `summarizing` / `saved` / `failed` state updates through the full flow (only `received` → `queued` happens today)
- **Ingestion-complete UX** — final Telegram reply with a short summary of what was captured (or a failure message naming the stage that died)
- **Raw media cleanup** — explicit R2 delete after graph ingestion (`saved`); today only the 2-day lifecycle rule exists
- **`job_events` audit table** — append-only per-stage timing/audit trail alongside `jobs`
- **Curation policy** — the highest-risk open question: deciding what's worth remembering vs. discarding from long/dense content, before the graph layer is built
- **Long-content handling** — chunked/map-reduce summarization for hour-long videos and large PDFs; size caps with "too big to ingest" messaging
