# kb-ingest (Worker 1)

Telegram webhook receiver for the knowledge-base pipeline. Validates Updates,
classifies content, uploads native media to R2, records jobs in D1, enqueues
job descriptors to the `kb-jobs` queue, and ACKs fast. See
[convo_summary.md](../../convo_summary.md) for the full architecture.

## Develop

```bash
npm install
npm test                 # unit + integration tests (runs inside workerd)
npm run typecheck
npx wrangler d1 migrations apply kb-jobs --local
npm run dev              # local server; secrets come from .dev.vars
```

`.dev.vars` (gitignored): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `OWNER_CHAT_ID`.

## Deploy (one-time provisioning)

```bash
npx wrangler login
npx wrangler queues create kb-jobs
npx wrangler r2 bucket create kb-raw-media
npx wrangler d1 create kb-jobs        # paste the returned id into wrangler.jsonc database_id
npx wrangler d1 migrations apply kb-jobs --remote
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
# set OWNER_CHAT_ID in wrangler.jsonc vars (your own Telegram chat id)
npx wrangler deploy
```

Then register the webhook:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<worker-url>/webhook&secret_token=<secret>
```

Also set an R2 lifecycle rule (dashboard): expire `raw-media/` after 2 days —
the safety net that deletes orphaned media from failed jobs.

## Watch it run

```bash
npx wrangler tail
npx wrangler d1 execute kb-jobs --remote --command "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 10"
```
