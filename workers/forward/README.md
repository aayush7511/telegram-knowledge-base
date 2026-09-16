# kb-forward (Worker 2)

Queue consumer + status endpoint for the knowledge-base pipeline. Pulls job
descriptors from the `kb-jobs` queue, POSTs each to the Cloud Run orchestrator
(push keeps Cloud Run on request-based billing), and marks the D1 row
`forwarded`. Its `POST /status` endpoint is Cloud Run's only path to D1:
`{job_id, state, r2_key?, error?, summary?}` with an `X-KB-Secret` header. It
also owns the 👀 → 👌 swap on the Telegram message once every job from it is
`saved`. See [CLAUDE.md](../../CLAUDE.md) for the architecture and
[docs/design/v2.md](../../docs/design/v2.md) for the v2 decisions.

Deployed: `https://kb-forward.aayush7511.workers.dev` (status endpoint at `/status`).

## Behavior notes

- **One job at a time**: `max_batch_size` 1 and `max_concurrency` 1. Cloud Run
  holds each request for the whole pipeline (a graph write can take minutes
  under free-tier rate limits), and parallel ingests into the same graph can
  create the same entity twice. Failures redeliver after `retry_delay` (60s),
  up to `max_retries` (5).
- **No dead-letter queue**: after max retries the queue message drops, but the
  D1 row keeps full job content (text/url/caption inline, media via r2_key) and
  stays in `queued` — recoverable by a future re-enqueue tool.
- **States**: this worker writes `forwarded` itself after a successful push.
  `/status` accepts only `fetching | transcribing | summarizing | indexing |
  saved | failed` — earlier states belong to Worker 1.
- **Transitions are validated** (`canTransition` in `src/db.ts`): a job only
  moves forward through the pipeline order (skips are fine — a text note goes
  `forwarded → indexing`), `saved` is terminal, and `failed` can be entered
  from any non-terminal state and left again when a job re-driven from D1
  starts reporting progress. Anything else is a `409` with
  `invalid transition <from> -> <to>` and the row is untouched. The UPDATE is a
  compare-and-set on the validated state, so concurrent updates can't both win.
- `r2_key` and `summary` in a status update use COALESCE: omitted → existing
  value kept; provided → overwritten. Blog jobs send `summary` (the graph
  episode text) with `indexing`, so the graph can be rebuilt from D1.
- **👌 reaction**: on a `saved` update, if every job sharing the message's
  `(chat_id, message_id)` is `saved`, the worker calls `setMessageReaction` 👌
  (replacing Worker 1's 👀) via `ctx.waitUntil`. Best-effort: a Telegram error
  is logged and the update still returns 200. A message with a `failed`
  sibling keeps its 👀.

## Develop

```bash
npm install
npm test                 # 43 tests: queue consumer, /status, 👌 reaction (runs inside workerd)
npm run typecheck
npm run dev              # local server; secrets come from .dev.vars
```

`.dev.vars` (gitignored): `CLOUD_RUN_SECRET`, `WORKER2_SHARED_SECRET` — same
values as `services/orchestrator/.dev.vars` (`KB_SHARED_SECRET` and
`WORKER2_SHARED_SECRET` respectively) — and `TELEGRAM_BOT_TOKEN` (same bot as
Worker 1).

Tests reuse Worker 1's D1 migrations (`../ingest/migrations`) — single source
of schema truth. Outbound calls are served by fakes in `vitest.config.ts`:
Cloud Run (job ids containing "boom" get a 500 to exercise retries) and
Telegram, which records every Bot API call and serves the list back on
`GET https://api.telegram.org/__reactions` so `reaction.test.ts` can assert
whether the 👌 was sent.

## Deploy (one-time provisioning)

```bash
# pipe secrets without a trailing newline — a stray \r\n breaks header comparison
printf '%s' "<KB_SHARED_SECRET value>"      | npx wrangler secret put CLOUD_RUN_SECRET
printf '%s' "<WORKER2_SHARED_SECRET value>" | npx wrangler secret put WORKER2_SHARED_SECRET
printf '%s' "<bot token>"                    | npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler deploy      # registers this worker as the kb-jobs consumer
```

Schema changes ship from Worker 1's migrations. Apply them to the remote D1
**before** deploying a worker that relies on them (v2's `summary` column is
migration `0003`):

```bash
cd ../ingest && npx wrangler d1 migrations apply kb-jobs --remote
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
