# kb-orchestrator (Cloud Run)

Processing orchestrator for the knowledge-base pipeline. Currently a **stub**:
authenticates job descriptors pushed by Worker 2, logs them, and exercises the
status-update callback. Real processing (blog extraction, Groq ASR/summarize,
Pi delegation) comes later. See [convo_summary.md](../../convo_summary.md).

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
KB_SHARED_SECRET=devsecret uvicorn main:app --port 8080
curl -s localhost:8080/health
curl -s -X POST localhost:8080/jobs -H "X-KB-Secret: devsecret" \
  -H "Content-Type: application/json" -d '{"job_id":"test-123"}'
```

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
  --allow-unauthenticated --max-instances 1 \
  --set-env-vars KB_SHARED_SECRET=<...>,WORKER2_SHARED_SECRET=<...>
```

Flag rationale: `--allow-unauthenticated` because auth is the app-level shared
secret (Workers can't mint Google OIDC tokens); `--max-instances 1` caps a
retry-loop bug from burning the free tier; request-based billing (the default)
is load-bearing — never switch to instance-based or add a poll loop.
`WORKER2_STATUS_URL` gets set (via `gcloud run services update
--set-env-vars`) once Worker 2 is deployed.

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
