# Spec: YouTube home worker (captions)

**Type:** Integration · **Status:** Approved 2026-10-10 · **Owner:** Aayush · **Drafted:** 2026-10-10

## Overview

YouTube blocks Cloud Run's IPs, so captions currently come from Supadata (100 videos/month free). A small Python web server on Aayush's Mac fetches English captions from YouTube over the home connection and returns them to Cloud Run when asked. If the Mac is asleep or offline, the job waits in a new `retrying` state and is retried up to 3 times, an hour apart, only between 6 a.m. and midnight Chicago time.

## Components

| Piece | Decision |
|---|---|
| Worker | Python web server on the Mac, listening on `127.0.0.1` only |
| Starts | At login, as a `launchd` LaunchAgent (`~/Library/LaunchAgents/`), restarted if it crashes |
| Reached by | Tailscale Funnel: a stable public `https://<mac>.<tailnet>.ts.net` URL forwarding to `127.0.0.1` |
| Who may call it | Only Cloud Run (`kb-orchestrator`), proven by a secret header checked against `YT_WORKER_SECRET` — its own value, separate from `X-KB-Secret`'s, so a leak on the Mac opens nothing else |
| Mac sleep | Allowed. A sleeping Mac is just "unreachable" and goes through the retry flow; no keep-awake setting |
| Direction | Cloud Run calls the worker. The worker never calls Cloud Run or anything else except YouTube |

## Contract: Cloud Run → Mac worker

**Request:** `POST /transcript` with the secret header and `{"video_id": "<11-char id>"}`. Cloud Run parses the URL; the worker only ever sees the ID.

**Responses:**

| Outcome | HTTP | Body |
|---|---|---|
| English captions found (auto-generated or human-written) | 200 | `{"status": "ok", "text": ..., "language": ..., "is_generated": true\|false}` |
| No captions, or captions only in other languages | 200 | `{"status": "no_captions"}` |
| YouTube blocked the request | 200 | `{"status": "blocked"}` |
| Video is private, deleted, or doesn't exist | 200 | `{"status": "unavailable"}` |
| Secret missing or wrong | 401 | nothing fetched |

Every real answer is a 200, so any other status (e.g. Tailscale's 502 when the Mac is off), a connection error, or no answer counts as **worker unreachable**.

Cloud Run waits at most **30 seconds** for an answer.

## What Cloud Run does with each outcome

| Outcome | Action | Reply to the user | Job ends |
|---|---|---|---|
| Captions | Use them, **no Supadata call** | Normal summary | `saved` |
| No captions | **No Supadata call** (and never Supadata's AI-generated mode) | "No captions" | `failed` |
| Blocked by YouTube | Fall back to Supadata, as today | Normal summary (or Supadata's own failure reply) | as today |
| Private / unavailable video | Stop, straight to `failed`, no retry | "Unavailable at the moment" | `failed` |
| Worker rejects the secret | Stop | "There was some error" | `failed` |
| `YT_WORKER_URL` not set on Cloud Run (setup mistake) | Stop, **no Supadata call**, no retry | "There was some error" | `failed` |
| Worker unreachable: connection error, any non-200/401 status, or timed out | Start the retry flow (below) | "Unavailable at the moment, I'll try again later" | `retrying` |

**Reply format:** every reply above except the normal summary uses the existing skip format, with the text as the reason:
`Skipped (not ingestible):\n• <video link> — <reason>`

## Retry flow (Mac asleep or offline)

1. Cloud Run moves the job to **`retrying`** and calls Worker 2's new **`POST /retry`** (with `X-KB-Secret`) with the job ID and a delay.
2. **Delay:** 1 hour from now. If that lands between midnight and 6 a.m. **America/Chicago** (follows CDT/CST), push it to the next 6:00 a.m. Chicago time.
3. Worker 2 puts the job back on `kb-jobs` with that delay, rebuilding the message from the D1 row (the existing "re-enqueue from D1 alone" rule). This needs a producer binding to `kb-jobs` on Worker 2.
4. A new D1 column on the job holds **how many retries have been scheduled**. Worker 2 increments it on each `/retry` and puts it in the rebuilt queue message, so **Cloud Run reads the count from the message and decides** (missing = 0, as for jobs straight from Worker 1).
5. When the delayed message arrives, the job goes `retrying → fetching` and runs again.
6. **Replies:** only the first failure messages the user ("Unavailable at the moment, I'll try again later"). Retries that fail send nothing.
7. After **3 retries** that still can't reach the worker: reply **"Unable to get captions"**, job ends `failed`.
8. **If the `/retry` call itself fails:** Cloud Run tries it again, up to 3 times. If it still fails, mark the job `failed` and move on. Ordinary `/status` posts stay best-effort, unchanged.
9. **If Worker 2 is down** so that marking the job `failed` also doesn't land, the job is left in `retrying`. Accepted for now (see Future work).

## Data model changes

- **New job state `retrying`**. Transitions: `fetching → retrying`, `retrying → fetching` (the **one allowed backward step**, an explicit exception in `canTransition`), `retrying → failed`.
- **New D1 column** on `jobs`: the retry count (name proposed: `retry_count`, integer, default 0).
- **New D1 column** on `jobs`: `url_source` (text, null for non-link jobs), written by Worker 1 for every link, so `/retry` can rebuild a complete queue message from the row alone.

## Invariants

- A captioned English video never triggers a Supadata call.
- A "no captions" result never triggers a Supadata call.
- A job is never retried more than 3 times.
- A retry never fires between midnight and 6 a.m. Chicago time.
- Only `retrying → fetching` may move backward; every other backward move is still a 409.
- The worker serves nothing to a request without the correct secret.

## Tests (one per rule)

| # | Situation | Expected |
|---|---|---|
| 1 | Worker returns English captions | Summary saved; no Supadata call |
| 2 | Only auto-generated English captions | Same as 1 |
| 3 | No captions | "No captions" reply right away; no Supadata call; `failed` |
| 4 | Captions only in another language | Same as 3 |
| 5 | Worker reports blocked | Supadata called |
| 6 | Private / deleted video | "Unavailable at the moment"; `failed` |
| 7 | Wrong or missing `YT_WORKER_SECRET` (including the `X-KB-Secret` value) | Worker returns 401; user gets "There was some error"; `failed` |
| 8 | Worker unreachable / 5xx / no answer in 30s | "Unavailable at the moment, I'll try again later"; `retrying`; `/retry` called with 3600s |
| 9 | Failure at 11:30 p.m. Chicago | Retry delay lands at 6:00 a.m. Chicago, not 12:30 a.m. |
| 10 | Failure across the Nov 1 CDT→CST change | 6 a.m. window follows Chicago local time |
| 11 | Delayed message arrives | `retrying → fetching` accepted by Worker 2 |
| 12 | Any other backward move | Still rejected (409) |
| 13 | 1st and 2nd retries can't reach the worker | No message sent; still `retrying`; next retry scheduled |
| 14 | 3rd retry also can't reach the worker | "Unable to get captions"; `failed`; no 4th retry |
| 15 | `/retry` call fails 3 times | Job marked `failed` |
| 16 | `POST /retry` on Worker 2 | Re-enqueues from the D1 row with the given delay; increments the retry count; rejects a bad `X-KB-Secret` |
| 17 | `YT_WORKER_URL` not set | No worker call, no Supadata call; "There was some error"; `failed` |
| 18 | Worker 1 receives a link | D1 row has its `url_source` (e.g. `youtube`); non-link jobs have none |

## Out of scope

- Audio download for captionless videos (its own spec, after transcription is built)
- Moving the worker to the Linux laptop
- Caption languages other than English
- Any change to how Supadata is used (including its AI-generated mode)

## Future work (noted, not built here)

- **Stuck-job sweep over D1.** A separate job that scans D1 for jobs still in `retrying` long after they started (hours or days, judged from their timestamps) and marks them `failed`. Covers the case where Worker 2 was down and the job could never be marked failed.

## How we know it works

- All 18 tests above pass (Workers via `vitest` + `vitest-pool-workers`, orchestrator and worker via `pytest`).
- **Live:** with the worker running on the Mac, a captioned YouTube video goes end to end, and the orchestrator logs show **no Supadata call**.

## Rollout note

Once deployed, YouTube links only work with `YT_WORKER_URL` set, since Supadata no longer covers an unset URL. Bring up the worker and the Funnel, and set `YT_WORKER_URL` and `YT_WORKER_SECRET` on Cloud Run, before or together with the orchestrator deploy.

## Open questions

None.
