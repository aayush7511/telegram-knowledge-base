# Spec: Retry summarizing later when Gemini is overloaded

**Type:** Integration · **Status:** Approved 2026-10-14 · **Owner:** Aayush · **Drafted:** 2026-10-14

## Overview

When Gemini answers 503 ("high demand") or 429 (rate limited), `summarize.py` retries inside the request, waiting 2, 4, 8 and then 16 seconds between tries (~30s in all). An overload that outlasts that window currently fails the job; this happened on 2026-10-13 to job `85efae35…`. Under this spec, a job that is still getting 503/429 after the in-request backoff moves to `retrying`. Worker 2 then re-enqueues it an hour later, the same way it already does for YouTube jobs waiting on the home worker. When the retry arrives, the job **resumes at summarizing** from the R2 archive and doesn't fetch the source again.

## Decisions

| Question | Decision |
|---|---|
| Which errors | Gemini **503 and 429**, after the existing in-request backoff (unchanged) runs out |
| Delay | **1 hour**, pushed to the next 6:00 a.m. America/Chicago if that lands between midnight and 6 a.m. (the existing `retry_delay_seconds`) |
| How many | Up to **3** retries |
| Retry count | **Shared** with the YouTube home-worker retries: the existing `retry_count` column and `MAX_RETRIES`. No new column |
| Where the retry starts | **summarizing**, reading the archived text and metadata from R2 |
| Metadata for the resume | A **JSON sidecar** `articles/{job_id}.json` (url, title, author, sitename), written next to the existing `articles/{job_id}.txt` at fetch time |
| How Cloud Run knows to resume | **Archive exists**: if the message has `retry_count > 0` and both `articles/{job_id}.txt` and `.json` are in R2, skip fetching. No new message field |
| Archive missing on retry | **Re-fetch**: run from `fetching` as normal |
| Replies | First failure: "Unavailable at the moment, I'll try again later". Silent on retries 1–2. Final give-up: "Couldn't summarize it, please send it again later". A retry that succeeds sends the normal summary |

## Data model changes

- **State machine:** `retrying` may now also be entered from **`summarizing`**, and left to **`summarizing`** (resume) as well as `fetching` (YouTube, and re-fetch when the archive is missing) and `failed`. `canTransition` in `workers/forward/src/db.ts`:
  - `→ retrying` allowed from `fetching` or `summarizing`
  - `retrying →` allowed to `fetching`, `summarizing`, or `failed`
- **R2:** new object `articles/{job_id}.json`, `{"url", "title", "author", "sitename"}`. It's best-effort like the `.txt`, and the `raw-media/` lifecycle rule doesn't touch it.
- **D1:** no schema change.
- **Worker 2 `/retry`:** unchanged. It already rebuilds the message from D1 and bumps `retry_count`.

## Flow

1. Fetching runs as today and archives `.txt` **and** `.json` to R2.
2. Summarizing: the in-request backoff runs as today. If the last attempt still fails with 503/429:
   - `retry_count >= 3` → final-failure reply, job `failed`.
   - Otherwise → post `retrying` (from `summarizing`) and call Worker 2 `/retry` with `retry_delay_seconds(now)`. The `/retry` call is attempted up to 3 times, and the job is marked `failed` if all three fail (same as YouTube). On `retry_count == 0`, reply "Unavailable at the moment, I'll try again later".
3. The delayed message arrives (`retry_count > 0`). Cloud Run reads `articles/{job_id}.txt` and `.json`:
   - Both present → post `summarizing` (from `retrying`), summarize, reply with the summary, then continue `indexing → saved` as today.
   - Either missing or unreadable → post `fetching` and run the full pipeline.
4. Any other summarize error (e.g. 400) → `failed` immediately, as today.

## Invariants

- The in-request backoff (2/4/8/16s on 503/429) is unchanged.
- A job is never retried more than 3 times in total, counting YouTube and summarize retries together.
- A retry never fires between midnight and 6 a.m. Chicago time.
- A resumed job never calls the fetcher (no Playwright, home worker or Supadata call) when both archive objects exist.
- Backward moves other than `retrying → fetching` and `retrying → summarizing` are still a 409.
- The user gets at most one "I'll try again later" message per job.

## Tests (one per rule)

| # | Situation | Expected |
|---|---|---|
| 1 | Fetch succeeds | `articles/{job_id}.txt` and `articles/{job_id}.json` (url, title, author, sitename) both written |
| 2 | Summarize still 503 after backoff, `retry_count` 0 | `retrying` posted; `/retry` called with `retry_delay_seconds`; "Unavailable at the moment, I'll try again later" sent |
| 3 | Same with 429 | Same as 2 |
| 4 | Summarize 400 | `failed`; no `/retry` call |
| 5 | Still 503, `retry_count` 1 or 2 | `retrying`; `/retry` called; no message sent |
| 6 | Still 503, `retry_count` 3 | Final-failure reply; `failed`; no `/retry` call |
| 7 | `/retry` call fails 3 times | `failed` |
| 8 | Retry arrives, both archive objects exist | Fetcher not called; `summarizing` posted; summary reply uses the archived title; `saved` |
| 9 | Retry arrives, `.json` missing | Fetcher called; normal pipeline from `fetching` |
| 10 | First delivery (`retry_count` 0) and archive somehow exists | Fetches as normal (resume only when `retry_count > 0`) |
| 11 | Worker 2: `summarizing → retrying` | Accepted |
| 12 | Worker 2: `retrying → summarizing` | Accepted |
| 13 | Worker 2: `indexing → retrying`, `saved → retrying`, `indexing → summarizing` | Rejected (409) |
| 14 | YouTube: `fetching → retrying → fetching` | Still accepted (unchanged) |

## Out of scope

- Changing the in-request backoff timings
- Fallback to another model or provider when Gemini is overloaded
- Saving without a summary
- Retrying failures in other stages (e.g. graph writes / OpenAI errors)
- Re-driving jobs that already failed before this ships (e.g. `85efae35…`; just resend the link)
- The stuck-job sweep from `specs/youtube-home-worker.md` (still future work)

## How we know it works

- All 14 tests pass (orchestrator `pytest`, Worker 2 `vitest` in `workerd`).
- **Live:** hard to force a real 503. After deploy, a normal blog link still goes end to end and both archive objects appear in R2, and the next real overload shows `retrying` in D1 followed by `saved`.

## Rollout

Deploy Worker 2 (the new transitions) **before** the orchestrator. Otherwise Cloud Run's `summarizing → retrying` post is rejected with a 409, and the job is left at `summarizing` while still being re-enqueued.

## Open questions

None. Final-failure reply: "Couldn't summarize it, please send it again later" (approved 2026-10-14).
