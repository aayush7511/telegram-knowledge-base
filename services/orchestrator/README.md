# kb-orchestrator (Cloud Run)

Processing orchestrator for the knowledge-base pipeline. **Blog URL jobs are
fully processed here** (Jira Epic SCRUM-6): Playwright renders the page,
Trafilatura extracts the body text and extruct extracts title/author/sitename
(JSON-LD → microdata → rdfa → opengraph cascade), Gemini 2.5 Flash summarizes,
and the summary is sent back on Telegram. Other job types (native-media ASR,
Instagram/YouTube Pi delegation) are still stubs. See
[convo_summary.md](../../convo_summary.md).

## Module map

- `main.py` — FastAPI app; `POST /jobs` branches blog URLs into `process_blog_job`,
  which runs **synchronously inside the request** (see below).
- `fetcher.py` — `render(url)`: headless Chromium → HTML.
- `extract.py` — `extract_content(html, url)` → `ResponseObject` (text + metadata cascade).
- `summarize.py` — `Summarizer`: Gemini 2.5 Flash with a 5-RPM sliding-window limiter.
- `telegram.py` — `send_summary(...)`: Bot API reply, threaded to the source message.
- `test/` — pytest suite (offline; Playwright/Gemini/Telegram mocked).

## Why blog jobs are processed synchronously

`/jobs` runs the whole pipeline before responding, so Worker 2's push stays open
for ~20-30s. Cloud Run only guarantees CPU **during request processing**, so
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

Watch the interaction with Worker 2's consumer settings (`max_batch_size 5`): a
full batch of blog jobs is processed serially, so ~30s each ≈ 150s of wall clock
in one `queue()` invocation. Fine today; revisit if batches grow or renders slow.

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
Body: { "job_id": string, "state": string, "r2_key": string|null, "error": string|null }
```

`state` is one of `fetching | transcribing | summarizing | saved | failed`
(`forwarded` is written by Worker 2 itself). Until `WORKER2_STATUS_URL` is set,
the callback is a logged no-op.

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

Run tests: `pytest` (from this directory). The suite is offline — Playwright,
Gemini, and Telegram are mocked.

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
  --allow-unauthenticated --max-instances 1 --memory 1Gi \
  --set-env-vars KB_SHARED_SECRET=<...>,WORKER2_SHARED_SECRET=<...>,GEMINI_API_KEY=<...>,TELEGRAM_BOT_TOKEN=<...>
```

`--source .` now builds from the **Dockerfile** in this directory (Playwright
needs Chromium + system libs, which buildpacks don't provide); the `Procfile`
is only used by local buildpack runs. `--memory 1Gi` gives headless Chromium
room (default 512Mi is tight); low volume keeps GiB-seconds well inside the
free tier. Flag rationale: `--allow-unauthenticated` because auth is the
app-level shared secret (Workers can't mint Google OIDC tokens); `--max-instances 1`
caps a retry-loop bug from burning the free tier and lets the summarizer's
in-process 5-RPM limiter be authoritative; request-based billing (the default)
is load-bearing — never switch to instance-based or add a poll loop.
New secrets: `GEMINI_API_KEY` (summarizer), `TELEGRAM_BOT_TOKEN` (summary replies).

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
