# kb-forward (Worker 2)

Queue consumer + status endpoint for the knowledge-base pipeline. Pulls job
descriptors from the `kb-jobs` queue, POSTs each to the Cloud Run orchestrator
(push keeps Cloud Run on request-based billing), and marks the D1 row
`forwarded`. Its `POST /status` endpoint is Cloud Run's only path to D1:
`{job_id, state, r2_key?, error?}` with an `X-KB-Secret` header. See
[convo_summary.md](../../convo_summary.md) for the full architecture.

Deployed: `https://kb-forward.aayush7511.workers.dev` (status endpoint at `/status`).

## Behavior notes

- **Per-message ack/retry**: one failing job doesn't recycle its batch-mates.
  Failures redeliver after `retry_delay` (60s), up to `max_retries` (5).
- **No dead-letter queue**: after max retries the queue message drops, but the
  D1 row keeps full job content (text/url/caption inline, media via r2_key) and
  stays in `queued` — recoverable by a future re-enqueue tool.
- **States**: this worker writes `forwarded` itself after a successful push.
  `/status` accepts only `fetching | transcribing | summarizing | saved |
  failed` — earlier states belong to Worker 1.
- `r2_key` in a status update uses COALESCE: omitted → existing value kept;
  provided → overwritten (the Pi fetch filling it in).

## Develop

```bash
npm install
npm test                 # 20 tests: queue consumer + /status (runs inside workerd)
npm run typecheck
npm run dev              # local server; secrets come from .dev.vars
```

`.dev.vars` (gitignored): `CLOUD_RUN_SECRET`, `WORKER2_SHARED_SECRET` — same
values as `services/orchestrator/.dev.vars` (`KB_SHARED_SECRET` and
`WORKER2_SHARED_SECRET` respectively).

Tests reuse Worker 1's D1 migrations (`../ingest/migrations`) — single source
of schema truth. Outbound Cloud Run calls are served by a fake in
`vitest.config.ts`; job ids containing "boom" get a 500 to exercise retries.

## Deploy (one-time provisioning)

```bash
# pipe secrets without a trailing newline — a stray \r\n breaks header comparison
printf '%s' "<KB_SHARED_SECRET value>"      | npx wrangler secret put CLOUD_RUN_SECRET
printf '%s' "<WORKER2_SHARED_SECRET value>" | npx wrangler secret put WORKER2_SHARED_SECRET
npx wrangler deploy      # registers this worker as the kb-jobs consumer
```

Then point Cloud Run's status callback here:

```bash
gcloud run services update kb-orchestrator --region us-central1 \
  --update-env-vars WORKER2_STATUS_URL=https://kb-forward.aayush7511.workers.dev/status
```

## Watch it run

```bash
npx wrangler tail
npx wrangler d1 execute kb-jobs --remote \
  --command "SELECT job_id, content_type, state, updated_at FROM jobs ORDER BY created_at DESC LIMIT 10"
```

Full-pipeline check: send the bot a text note → the D1 row should walk
`queued → forwarded → summarizing` (the stub's placeholder callback) within a
few seconds.
