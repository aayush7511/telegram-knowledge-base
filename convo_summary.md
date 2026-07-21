# Knowledge Base Project — Conversation Summary

> Living document tracking all decisions and state for the personal AI memory/knowledge capture tool.
> Last updated: 2026-07-21

## The Idea

A personal tool that remembers everything you share with it. Content (text notes, voice memos, Instagram reels, YouTube videos, blogs) is sent through Telegram, ingested, transcribed/summarized, and stored in a knowledge graph with temporal awareness (when a project started/ended, when you learned something). Later, when you talk about something related, it surfaces relevant past context.

## Core Constraints

- **Cost: everything free** — $0/month recurring in service fees (personal project)
- **Speed: transcription as fast as possible**
- **Cheap models OK, local models on old hardware OK**

---

## Architecture (settled)

```
Telegram message
   ↓  (webhook POST, one registered URL via setWebhook + secret_token)
Cloudflare Worker 1  — validate, classify, split, upload media to R2, enqueue, fast ACK
   ↓
Cloudflare Queue    — carries small job descriptors (128KB/message limit)
   ↓
Cloudflare Worker 2 — queue consumer: forwards jobs to Cloud Run (push, HTTP POST)
                      + fetch() handler: receives status updates from Cloud Run → writes D1
   ↓
Google Cloud Run    — processing orchestrator (request-based billing, scales to zero)
   │
   ├─ text/blog jobs: handle directly (HTTP fetch + readability + LLM summarize)
   ├─ native media: pull bytes from R2, send to Groq for ASR
   └─ Instagram/YouTube URLs: delegate to home Pi (datacenter IP would get flagged)
   ↓
Home Raspberry Pi   — polls for fetch jobs (outbound HTTPS, no port-forwarding needed)
                      runs yt-dlp + cookies + PO-token provider → uploads audio to R2
   ↓
Groq API            — Whisper large-v3-turbo ASR (free tier: 2,000 req/day)
                      Llama 3.3 70B for summarization/curation (free tier: 1,000 req/day)
   ↓
Knowledge graph     — self-hosted Graphiti (Apache 2.0) + FalkorDB, on the Pi via Docker
   ↓
Telegram reply      — ingestion confirmation w/ summary, or failure message
```

### Key architecture decisions and why

| Decision | Reasoning |
|---|---|
| Telegram as the single ingestion channel | Free, natively supports text/voice/video/documents/links in one chat |
| Webhook (not polling) | Telegram pushes Updates as POSTs to one registered URL; Worker never polls |
| Fast ACK + queue | Telegram retries on slow/non-2xx responses → duplicate Updates. Heavy work must be async |
| Cloudflare Worker as receiver | Free (100k req/day), always warm, can't run yt-dlp/ffmpeg (no binaries) but perfect for validate+enqueue |
| Google Cloud Run over Fly.io | Fly.io killed its free tier (2024, ~$2–5/mo minimum). Cloud Run has a permanent free tier: 2M requests, 180k vCPU-sec (~50 CPU-hours), 360k GiB-sec per month |
| Cloud Run must be push-triggered, NOT polling | Request-based billing = CPU billed only while handling a request. A poll loop would force instance-based (always-on) billing and burn the free tier. Worker 2 pushes jobs via HTTP |
| Home Pi for yt-dlp fetches | Instagram/YouTube flag datacenter IPs on sight. Residential IP required. Pi ≈ $60–100 one-time + ~$0.65/mo electricity |
| Pi polls (vs. tunnel) | Pi is behind home NAT; outbound HTTPS polling needs zero network setup. Tailscale is the later upgrade if latency matters |
| Groq for ASR | Whisper large-v3-turbo at ~216x realtime, $0.04/hr paid but free tier covers personal volume. Fastest AND cheapest option. Local fallback: faster-whisper + distil-large-v3 int8 |
| Graphiti + FalkorDB self-hosted over Zep hosted | Zep Community Edition deprecated; hosted Zep free tier limited (~10K messages). Graphiti is the open-source engine under Zep (Apache 2.0). FalkorDB lighter than Neo4j (Redis-based, no JVM) for Pi hardware |
| R2 for file storage | 10GB free, zero egress fees, S3-compatible (Cloud Run talks to it directly with S3 creds — no proxy needed, unlike D1) |
| D1 for job tracking | Full SQLite (multiple tables, joins, FKs, transactions). Free: 5GB, 100k writes/day, 5M reads/day — never a real constraint |
| Delete raw media after graph ingestion | Raw video/audio is the only large data. Transcript ≈ 60–90KB/hr of speech. Explicit delete after `saved` + R2 lifecycle rule (e.g. 2 days on `raw-media/` prefix) as safety net for failed jobs |

---

## Job Descriptor Schema (queue message)

```js
{
  job_id: string,            // UUID generated in Worker 1 — D1 primary key + R2 key prefix
  group_id: string | null,   // media_group_id from Telegram (albums) or generated UUID (multi-URL fan-out)
  chat_id: number,           // Telegram chat (needed for replies)
  message_id: number,        // unique per chat — (chat_id, message_id) also used for webhook-retry dedup
  time_received: string,     // ISO 8601
  content_type: "text" | "voice" | "photo" | "video" | "document" | "url",

  text: string,              // only for content_type "text" (Telegram caps at 4,096 chars — safe inline)
  url: string,               // only for "url"
  url_source: "instagram" | "youtube" | "blog",  // detected in Worker 1 via domain check

  media: {                   // only for binary types — bytes already in R2 before enqueue
    r2_key: string,          // null at enqueue for URL jobs; Pi fills it in after yt-dlp fetch
    mime_type: string,
    size_bytes: number,
    duration_seconds: number
  },
  caption: string            // optional; also carries surrounding text for fanned-out URL jobs
}
```

### Rules
- **Inline vs. R2 split**: text/captions/URLs inline (Telegram caps them: 4,096 / 1,024 chars — guaranteed under queue's 128KB). All binary media → R2 first, queue carries only the key. Base64-inlining binary would inflate ~33% — never do it.
- **R2 keys are chosen by us**, not generated by R2 (e.g. `raw-media/{job_id}.ogg`). `put()` returns R2Object metadata: key, size, etag, version, uploaded — log size+etag to D1.
- **Multi-URL messages**: single Update with one text field. Worker 1 regex-extracts URLs and fans out N separate url-jobs sharing a generated `group_id`. Splitting is for failure isolation (independent pipelines/retries), not queue size (40 URLs still ≈ 4–16KB).
- **Media albums**: each item arrives as its own Update sharing Telegram's `media_group_id`. Decision: NO synchronization/buffering logic — just pass `media_group_id` through as `group_id` and let the graph use it if useful. Each item is its own job.
- **Early URL validation (Layer 1, Worker 1)**: reject on URL shape — profiles, channels, playlists, comment permalinks. Accept `/reel/`, `/watch`, `/shorts/`. `/p/` posts are ambiguous (image vs video vs carousel) → only resolvable at fetch time (Layer 2, on the Pi via yt-dlp metadata → fail/reroute + Telegram error reply).
- **Telegram getFile limit**: standard Bot API can only download files ≤ 20MB. Larger native attachments can't be retrieved without self-hosting Telegram's local Bot API server.

---

## D1 Schema (two tables)

```sql
CREATE TABLE jobs (
  job_id      TEXT PRIMARY KEY,   -- UUID from Worker 1
  chat_id     INTEGER,
  message_id  INTEGER,
  group_id    TEXT,
  content_type TEXT,
  state       TEXT,
  error       TEXT,               -- populated on failure
  r2_key      TEXT,               -- nullable: filled at ingestion (native media) or after Pi fetch (URLs)
  text        TEXT,               -- added 0002: inline content for text jobs (≤4,096 chars)
  url         TEXT,               -- added 0002: the URL for url jobs
  caption     TEXT,               -- added 0002: media caption / surrounding prose for URL fan-outs
  created_at  TEXT,
  updated_at  TEXT
);

CREATE TABLE job_events (          -- optional audit trail, append-only, add when timing data wanted
  event_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id    TEXT REFERENCES jobs(job_id),
  state     TEXT,
  at        TEXT,
  note      TEXT
);
```

- **Content rule (added 2026-07-17): every job row carries its content or a pointer to it** — text/url/caption inline (message-scale, Telegram-capped), binary media via r2_key. Rationale: the queue message was previously the only copy of text/url content (~4-day retention, no consumer yet); D1 copy makes jobs re-enqueueable and failed rows self-describing.
- Start with `jobs` only (Option A: state + error + created_at + updated_at). Add `job_events` later if per-stage timing is wanted. Rejected: column-per-state (`fetched_at`, `saved_at`...) — mostly-null columns, schema migration per new state, can't represent retries.
- Use `db.batch([...])` to atomically update `jobs` + insert `job_events` when both tables are live.
- Dedup webhook retries via (chat_id, message_id) guard on insert.

### State machine (flat, linear; jobs skip states that don't apply)

```
received → verified → queued → forwarded → fetching → transcribing → summarizing → saved
                                                                              ↘ failed (terminal, + error)
```

- **State lives in D1, not the queue message** — queue messages are in-flight and immutable; each pipeline stage advances the D1 row.
- **No per-source state values** (no `fetching_youtube` vs `fetching_blog`) — `state` = pipeline stage, `content_type`/`url_source` = what kind. Query by combining columns. Litmus test for a state: "would I want the bot to tell me it died *there*?"
- Reading from R2 is not a state — it's internal I/O inside `transcribing`.
- Text notes skip `fetching`/`transcribing`; native media skips `fetching`.

---

## Access patterns / integration notes

- **Cloud Run → D1**: no native driver. Use a thin proxy Worker (Worker 2's fetch handler) with the D1 binding; Cloud Run POSTs status updates with a shared-secret header. (D1's raw REST API exists but shares the global Cloudflare API rate limit — admin use only.)
- **Status-update contract (settled 2026-07-21, implemented on the Cloud Run side)**: `POST {WORKER2_STATUS_URL}` with header `X-KB-Secret: {WORKER2_SHARED_SECRET}` and body `{job_id, state, r2_key|null, error|null}`. `state` ∈ fetching | transcribing | summarizing | saved | failed (`forwarded` is written by Worker 2 itself after a successful push). Worker 2 will `UPDATE jobs SET state=?, r2_key=COALESCE(?, r2_key), error=?, updated_at=?` and later batch a `job_events` insert. Two secrets: `KB_SHARED_SECRET` (Worker 2 → Cloud Run; Wrangler secret `CLOUD_RUN_SECRET` later) and `WORKER2_SHARED_SECRET` (Cloud Run → Worker 2). Status posts are best-effort — failures logged, never fail job handling; D1 state drives retries.
- **Cloud Run → R2**: direct via S3-compatible API + access keys. No proxy needed.
- **Worker 1 → Queue**: native binding, `env.MY_QUEUE.send(job)`.
- **Queue → Worker 2**: native push consumer (`queue()` handler). One Worker can export both `queue()` and `fetch()` handlers — isolated execution contexts, no contention. Both halves of the same round trip (job out / status back), so combining is sensible.
- **Worker 2 → Cloud Run**: outbound `fetch()` POST. Keeps Cloud Run on request-based billing.
- **Telegram auth**: `secret_token` set at setWebhook, checked via `X-Telegram-Bot-Api-Secret-Token` header in Worker 1.
- **Worker 2 inbound auth**: shared secret header from Cloud Run — it's a public endpoint otherwise.

## yt-dlp / scraping realities

- **Instagram**: increasingly requires login — use cookies from a **dedicated bot account** (not personal), exported as cookies.txt (Netscape format) or via occasional Playwright login script. Sessions expire → on auth failure, set state=failed and message the user via Telegram to re-auth. Account-ban risk is real; low volume + spacing mitigates.
- **YouTube PO Tokens**: BotGuard attestation ("this request came from a real browser"), separate from cookies ("this is a logged-in session"). Bound to visitor ID and increasingly per-video. Without: HTTP 403 / blocks. Solution: `bgutil-ytdlp-pot-provider` — lightweight Node/Deno service (port 4416) that solves the BotGuard challenge WITHOUT a full headless browser. Runs continuously on the Pi.
- **Headless browser (Playwright)**: only needed occasionally, for cookie refresh — not per-request.
- **Home IP fixes IP reputation but NOT**: PO token requirement, rate-limiting/behavioral detection, ToS/account risk, CGNAT shared-IP reputation, extractor breakage (expect `yt-dlp -U` maintenance).
- **YouTube shortcut**: check auto-generated captions first (`--write-auto-sub` / youtube-transcript-api) — free, instant, skips ASR entirely when quality suffices.

## ASR decision

- **Primary**: Groq Whisper large-v3-turbo API — ~216x realtime (1hr audio ≈ 15s), $0.04/hr, free tier 2,000 req/day covers personal volume. Fastest and cheapest simultaneously.
- **Fallback (offline/rate-limited)**: faster-whisper with distil-large-v3, int8 quantized — ~6x faster than large-v3, WER within ~1%, runs on old CPUs (13 min audio ≈ 22–26s on modern CPU).
- ffmpeg normalizes audio to 16kHz mono WAV between download and ASR (most wrappers do this internally).

## Cost summary

| Component | Cost |
|---|---|
| Telegram Bot API | $0 |
| Cloudflare Worker (100k req/day), Queues (10k ops/day), R2 (10GB), D1 (5GB) | $0 |
| Google Cloud Run (2M req, 50 CPU-hr/mo free; personal volume ≈ 2.5 CPU-hr/mo) | $0 |
| Groq Whisper + Llama free tiers | $0 |
| Graphiti + FalkorDB self-hosted | $0 (maintenance is yours) |
| Raspberry Pi | ~$60–100 one-time + ~$0.65/mo electricity |
| **Recurring total** | **≈ $0.65/mo (electricity only)** |

---

## Open questions (not yet resolved)

1. **HIGHEST RISK — curation policy**: how does the system decide what's worth remembering vs. discarding from long/dense content (e.g., a textbook)? Options: (a) always store full raw + generated summary, summary for retrieval matching, raw as fallback; (b) bot asks a clarifying question at ingestion when intent is ambiguous. Flagged as more important than infra — silent bad curation is hard to debug later. **Decide before building the graph layer.**
2. Knowledge graph specifics: how content is added to the graph, how retrieval surfaces related content in conversation, how Graphiti stores/queries time, what breaks with large files.
3. Long-content handling: chunked/map-reduce summarization for 1-hr videos / 400-page PDFs; size caps and "too big to ingest" messaging.
4. Ingestion confirmation UX: bot replies with a short summary of what it captured (design intent, not yet spec'd).
5. Media album (`media_group_id`) items are treated as independent jobs — revisit if the graph turns out to need stronger grouping.

## Build order (agreed starting point)

**Part 1: Worker 1 — BUILT (2026-07-15)** — lives in `workers/ingest/` (TypeScript + Wrangler + Vitest). Secret-token check, owner-chat allowlist, Update parsing, classification, URL-shape validation, multi-URL fan-out, R2 upload for native media (≤20MB getFile cap enforced), D1 insert with state-aware dedup, enqueue, fast ACK. Ingestion ack = 👀 reaction (setMessageReaction); rejections get a text reply. 45 tests green (pure logic + workerd integration via vitest-pool-workers), verified locally with wrangler dev + curl.
- Not yet done: cloud provisioning + deploy (queue, R2 bucket, D1 create + real database_id in wrangler.jsonc, secrets, setWebhook, R2 lifecycle rule) — steps in `workers/ingest/README.md`.
- Implementation notes: dedup rule = rows for (chat_id, message_id) in state ≥ queued → skip; stale `received` rows → delete + reprocess (safe because queue delivery is at-least-once; consumer must be idempotent anyway). Permanent rejections reply + 200; transient failures 500 → Telegram retries.

**Part 1.5: Cloud Run stub — PROVISIONED (2026-07-21)** — lives in `services/orchestrator/` (Python + FastAPI, deployed via `gcloud run deploy --source` buildpacks). Deployed **before** Worker 2 so the queue consumer has a real endpoint from day one (otherwise every consumed job would fail/retry into the void) and so `CLOUD_RUN_URL` is pinned (service URL is stable across deploys). Service: `kb-orchestrator`, project `kb-orchestrator-8yuto1`, region us-central1 (free tier = Tier-1 regions; latency irrelevant for async), URL `https://kb-orchestrator-135554694779.us-central1.run.app`. `--allow-unauthenticated` (auth = app-level shared secret; Workers can't mint Google OIDC tokens) + `--max-instances 1` (free-tier burn cap) + request-based billing (default — never add a poll loop). Endpoints: `POST /jobs` (X-KB-Secret auth, logs descriptor, fires placeholder status update), `GET /health` (NOT `/healthz` — Google's frontend reserves that path on run.app and 404s it). Verified live: 401 without secret, 200 with, logs show descriptor + skipped status callback. No processing yet — pure contract stub.

**Part 2 (next): Worker 2** — queue consumer + status-update fetch endpoint (D1 proxy for Cloud Run). Inputs ready: service URL above, both secrets (in `services/orchestrator/.dev.vars`, gitignored), status-update contract (§Access patterns).

## Reference commands

```bash
# yt-dlp audio-only with browser cookies
yt-dlp --cookies-from-browser chrome -f bestaudio -x --audio-format mp3 -o "%(id)s.%(ext)s" "<URL>"

# ffmpeg normalize for ASR
ffmpeg -i in.m4a -ar 16000 -ac 1 -c:a pcm_s16le out.wav

# Telegram webhook registration
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<worker-url>&secret_token=<secret>
```
