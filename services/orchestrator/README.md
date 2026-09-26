# kb-orchestrator (Cloud Run)

Processing orchestrator for the knowledge-base pipeline. **Blog URL jobs are
fully processed here**: Playwright renders the page, Trafilatura extracts the
body text and extruct extracts title/author/sitename (JSON-LD → microdata →
rdfa → opengraph cascade), the article text is archived in R2, Gemini
summarizes, the summary is sent back on Telegram, and then written into the
knowledge graph (Graphiti → FalkorDB). **Text notes** go straight into the
graph. Other job types (native-media ASR, Instagram/YouTube Pi delegation) are
still stubs. See [CLAUDE.md](../../CLAUDE.md) for the architecture and
[docs/design/v2.md](../../docs/design/v2.md) for the graph decisions.

## Module map

- `main.py` — FastAPI app; `POST /jobs` branches blog URLs into `process_blog_job`
  and text notes into `process_text_job`, both running **synchronously inside
  the request** (see below).
- `fetcher.py` — `render(url)`: headless Chromium → HTML.
- `extract.py` — `extract_content(html, url)` → `ResponseObject` (text + metadata cascade).
- `articles.py` — `store_article(job_id, text)`: cleaned article text → R2
  `articles/{job_id}.txt` (S3 API via boto3). Best-effort; no-op until `R2_*` is set.
- `summarize.py` — `Summarizer`: Gemini with a 5-RPM sliding-window limiter.
- `telegram.py` — `send_summary(...)`: Bot API reply, threaded to the source message.
- `graph.py` — `write_episode(...)`: one Graphiti episode per job into FalkorDB
  (graph `second-brain`), `gpt-4.1-mini` at temperature 0 for extraction,
  `text-embedding-3-small` for embeddings. Built lazily on first use — the
  FalkorDB driver connects in its constructor. `blog_episode(ro)` assembles the
  episode: title + summary in the body, URL/site/author in `source_description`.
- `test/` — pytest suite (offline; Playwright/Gemini/Telegram/Graphiti/R2 mocked).

## Why blog jobs are processed synchronously

`/jobs` runs the whole pipeline before responding, so Worker 2's push stays open
for ~20-30s of render + summarize plus the graph write (Graphiti makes ~7 LLM
calls per episode; ~15s in M0, longer under rate limits — hence `--timeout 600`). Cloud Run only guarantees CPU **during request processing**, so
anything deferred past the response (a FastAPI `BackgroundTask`, say) can be
throttled mid-render and stall without ever writing a terminal state. Holding
the request keeps that guarantee without needing `--no-cpu-throttling`.

Two consequences worth knowing:

- `post_status` is async and `summarize()` runs via `asyncio.to_thread` — the
  rate limiter's sleeps would otherwise block the event loop and freeze
  `/health` and every other in-flight request for the duration of a job.
- `/jobs` returns **2xx even when a job fails**. The failure is already terminal
  in D1, so Worker 2 should ack the queue message rather than replay an
  identical render+summarize that will fail the same way and consume the Gemini
  rate budget. Genuinely transient failures are re-driven from D1, not the queue.

Worker 2 delivers one job at a time (`max_batch_size 1`, `max_concurrency 1`),
so there is never a second pipeline running in this instance — which also keeps
Graphiti's entity dedup serial.

### Blog pipeline order

`fetching` (render → extract → archive text in R2) → `summarizing` (Gemini) →
Telegram reply → `indexing` (status post carries the episode text, then the
Graphiti write) → `saved`. The reply goes out *before* the graph write, so a
graph failure still leaves the user with the summary; the row ends `failed`
with the error and the episode text sits in D1's `summary` column for a
re-drive. Text notes: `indexing` → `saved`, no reply — Worker 2's 👌 reaction is
the acknowledgement.

## Endpoints

- `POST /jobs` — job descriptor intake. Requires `X-KB-Secret` header matching
  the `KB_SHARED_SECRET` env var; 401 otherwise. Returns
  `{"accepted": true, "job_id": ...}`.
- `GET /health` — liveness check. (Not `/healthz`: Google's frontend reserves
  that path on run.app and 404s it before it reaches the container.)

## Status-update contract (this service → Worker 2 → D1)

Cloud Run has no D1 driver, so state changes go through Worker 2's fetch
handler:

```
POST {WORKER2_STATUS_URL}
Headers: X-KB-Secret: {WORKER2_SHARED_SECRET}
Body: { "job_id": string, "state": string, "r2_key": string|null, "error": string|null, "summary": string|null }
```

`state` is one of `fetching | transcribing | summarizing | indexing | saved |
failed` (`forwarded` is written by Worker 2 itself). `summary` is sent with
`indexing` for blog jobs. Worker 2 validates transitions and answers `409` for
a backwards move or anything after `saved`; like every other status failure
that's logged, not fatal. Until `WORKER2_STATUS_URL` is set, the callback is a
logged no-op.

## Develop

```bash
pip install -r requirements.txt
playwright install chromium          # one-time: browser for fetcher.py
KB_SHARED_SECRET=devsecret uvicorn main:app --port 8080
curl -s localhost:8080/health
# non-blog stub job:
curl -s -X POST localhost:8080/jobs -H "X-KB-Secret: devsecret" \
  -H "Content-Type: application/json" -d '{"job_id":"test-123"}'
# blog job (needs GEMINI_API_KEY; set TELEGRAM_BOT_TOKEN + chat_id for a reply):
curl -s -X POST localhost:8080/jobs -H "X-KB-Secret: devsecret" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"b1","content_type":"url","url_source":"blog","url":"https://example.com/post","chat_id":123,"message_id":9}'
```

Run tests: `pytest` (from this directory) — 21 tests. The suite is offline:
Playwright, Gemini, Telegram, Graphiti, and R2 are mocked. Graph-related env
vars for a real local run: `FALKORDB_HOST` (+ `FALKORDB_PORT`,
`FALKORDB_PASSWORD`), `OPENAI_API_KEY`; article archive: `R2_ACCOUNT_ID`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` (+ `R2_BUCKET`, default
`kb-raw-media`).

## Deploy (one-time provisioning)

```bash
gcloud auth login
gcloud projects create <project-id>            # globally unique id
gcloud billing projects link <project-id> --billing-account <ACCOUNT_ID>
gcloud config set project <project-id>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# generate two secrets (32+ random chars each):
#   KB_SHARED_SECRET       — Worker 2 → Cloud Run   (also Wrangler secret CLOUD_RUN_SECRET later)
#   WORKER2_SHARED_SECRET  — Cloud Run → Worker 2   (checked by Worker 2 when built)

gcloud run deploy kb-orchestrator --source . --region us-central1 \
  --allow-unauthenticated --max-instances 1 --memory 1Gi --timeout 600 \
  --network default --subnet default --vpc-egress private-ranges-only \
  --set-env-vars KB_SHARED_SECRET=<...>,WORKER2_SHARED_SECRET=<...>,GEMINI_API_KEY=<...>,TELEGRAM_BOT_TOKEN=<...>,OPENAI_API_KEY=<...>,FALKORDB_HOST=<vm internal ip>,FALKORDB_PASSWORD=<...>,R2_ACCOUNT_ID=<...>,R2_ACCESS_KEY_ID=<...>,R2_SECRET_ACCESS_KEY=<...>
```

The `--network/--subnet/--vpc-egress` flags are Direct VPC egress: the
instance gets an address in the VPC and reaches FalkorDB on the VM's internal
IP, while `private-ranges-only` keeps Gemini/OpenAI/Telegram/blog traffic on
the normal internet path (`all-traffic` would need paid Cloud NAT). No
connector VMs, so no compute charge. `--timeout 600` covers the graph write.

`--source .` now builds from the **Dockerfile** in this directory (Playwright
needs Chromium + system libs, which buildpacks don't provide); the `Procfile`
is only used by local buildpack runs. `--memory 1Gi` gives headless Chromium
room (default 512Mi is tight); low volume keeps GiB-seconds well inside the
free tier. Flag rationale: `--allow-unauthenticated` because auth is the
app-level shared secret (Workers can't mint Google OIDC tokens); `--max-instances 1`
caps a retry-loop bug from burning the free tier and lets the summarizer's
in-process 5-RPM limiter be authoritative; request-based billing (the default)
is load-bearing — never switch to instance-based or add a poll loop.
Secrets: `GEMINI_API_KEY` (summarizer), `TELEGRAM_BOT_TOKEN` (summary replies),
`OPENAI_API_KEY` (Graphiti extraction + embeddings), `FALKORDB_PASSWORD`, and
the `R2_*` S3 credentials (article archive).

### Deploy gotchas (hit for real on 2026-07-27)

- **Quote `--set-env-vars` in PowerShell.** Unquoted, PowerShell parses the
  comma-separated list as an array and the *entire* string lands in the first
  variable — the rest are silently never set. The symptom is a correct secret
  getting a 401. Wrap the whole `KEY=v,KEY=v` value in single quotes. Env vars
  persist across deploys, so prefer setting them once (or via
  `gcloud run services update --update-env-vars`) rather than re-passing them.
- **`--clear-base-image` is required once.** The service carried an automatic
  base image from its buildpack days; deploying from a Dockerfile fails with
  `Missing required argument [--clear-base-image]` until that's cleared.
- **Verify env vars landed** — names and lengths only, never print the values:
  ```bash
  gcloud run services describe kb-orchestrator --region us-central1 \
    --format="value(spec.template.spec.containers[0].env.name)"
  ```

### Model availability

`gemini-2.5-flash` is **closed to new API users** — `generateContent` returns
`404 no longer available to new users`, even though the model still shows up in
the `/v1beta/models` list. That list is not a reliable capability check; probe
with an actual generate call. Verified working on this key: `gemini-3.6-flash`
(what `summarize.py` pins) and `gemini-flash-latest`. The pinned version is
deliberate — the `-latest` alias could shift models under a rate budget tuned
to one.

Region is us-central1: free tier applies to Tier-1 pricing regions, and
latency is irrelevant for an async pipeline.

**Service URL**: `https://kb-orchestrator-135554694779.us-central1.run.app`
(project `kb-orchestrator-8yuto1`, region `us-central1` — this is Worker 2's
`CLOUD_RUN_URL`). Secrets live in the gitignored `.dev.vars` here and as env
vars on the service.

## Watch it run

```bash
gcloud run services logs read kb-orchestrator --region us-central1 --limit 50
```
