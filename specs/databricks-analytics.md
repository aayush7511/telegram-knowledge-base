# Spec: Pipeline analytics on Databricks

**Type:** Analytics side-project · **Status:** Draft · **Owner:** Aayush · **Drafted:** 2026-10-14 · **Due:** 2026-11-01 (after the Oct 22 launch)

## Overview

A read-only copy of the bot's job history lands in Databricks Free Edition every few hours. A Lakeflow pipeline cleans it with PySpark into bronze → silver → gold Delta tables in Unity Catalog, and a small Databricks App shows how the bot is used and how healthy the pipeline is. Nothing in Databricks writes back to the bot. If Databricks breaks, the bot is unaffected.

**Why:** it answers real questions about the bot (which sources people save, where jobs fail, how retries behave after the YouTube home worker went live). It also gives true resume lines for Spark, Delta Lake, Unity Catalog, Lakeflow and Databricks Apps.

## Free Edition limits that shape this

From the [Free Edition limitations docs](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations) (check the live page; mirrors differ):

| Limit | Effect on this spec |
|---|---|
| Serverless compute only, no custom clusters or GPUs | Every notebook, job and pipeline runs serverless |
| 1 active pipeline per pipeline type | One Lakeflow pipeline does bronze → silver → gold |
| 1 SQL warehouse, 2X-Small | Fine for gold tables at this size |
| 1 Databricks App, stops 24 h after start/redeploy | Restart it before a demo or an interview |
| 1 Vector Search endpoint; Direct Vector Access not supported | Stretch goal must use a Delta Sync index |
| Non-commercial use only | Fine: personal project |

## Data flow

```
D1 (jobs table) --[D1 REST API, scheduled Lakeflow Job]--> UC Volume (raw JSON)
   --[Lakeflow pipeline: Auto Loader]--> bronze.jobs
   --[PySpark: clean, dedupe, derive]--> silver.jobs
   --[aggregates]--> gold.daily_saves, gold.job_health, gold.retry_outcomes
   --> Databricks App (reads gold via the SQL warehouse)
```

## 1. Extract (Lakeflow Job, Python notebook)

- **Source:** the D1 HTTP query endpoint (`POST /accounts/{account_id}/d1/database/{database_id}/query`) with a Cloudflare API token scoped to **D1 read only**, stored in a Databricks secret scope (`kb/cf_d1_token`). Never in the notebook.
- **Incremental:** `SELECT ... FROM jobs WHERE updated_at > :watermark ORDER BY updated_at LIMIT 500`, paging until empty. Keep the watermark in a small Delta table `ops.watermarks`.
- **Columns pulled (metadata only):** `job_id, chat_id, content_type, url_source, state, error, retry_count, created_at, updated_at`.
- **Never pulled:** `text`, `caption`, `summary`, `url`, `r2_key`. Same rule as the bot: user content stays out of third-party systems it doesn't need to be in.
- **chat_id:** hash with SHA-256 + a salt from the secret scope before writing. Users show up as `user_1`…`user_n` in the app.
- **Output:** one JSON file per run in `/Volumes/kb/raw/jobs/`.
- **Schedule:** every 6 hours.

## 2. Transform (Lakeflow Declarative Pipeline, PySpark)

**bronze.jobs:** Auto Loader over the volume, schema enforced, `_ingested_at` added.

**silver.jobs:** one row per `job_id` (latest `updated_at` wins, since the same job arrives again as its state changes), plus:
- `source`: `url_source`, or `note` / `media` / `pdf` from `content_type`
- `latency_s`: `updated_at - created_at` for jobs in a final state
- `is_final`, `succeeded`, `error_class` (bucket the `error` text: `blocked`, `timeout`, `extraction`, `other`)
- Expectations (data quality checks): `job_id` not null, `state` in the known state list, `updated_at >= created_at`. Drop rows that fail, and count them.

**gold tables:**

| Table | Grain | Columns |
|---|---|---|
| `gold.daily_saves` | day × source | saves, distinct users |
| `gold.job_health` | day | jobs, success rate, p50/p95 latency, failures by `error_class` |
| `gold.retry_outcomes` | source | jobs that retried, retries per job, % that eventually succeeded |

## 3. Serve (Databricks App, Streamlit)

One page, 4 panels:
1. Saves per day, stacked by source
2. Success rate + p95 latency per day
3. Failures by error class (last 14 days)
4. Retry outcomes for YouTube jobs before and after the home worker shipped (2026-10-10)

Reads gold tables only, through the SQL warehouse, with the app's own service principal granted `SELECT` on `kb.gold`.

## 4. Stretch: Vector Search comparison

Only if 1–3 ship by Nov 1. Needs a decision first: the facts and embeddings live in FalkorDB (private to the VPC), and copying user content into Databricks breaks the "metadata only" rule above. Options: run it on the **owner's own saves only**, or skip it. If it goes ahead, use a Delta Sync index (Direct Vector Access isn't available on Free Edition) and compare its top-5 against the FalkorDB hybrid search on the 30-question retrieval eval.

## Optional: token usage per job

D1 doesn't store token counts today; they only exist in the M0 spike output. To add a `gold.llm_cost` table, the orchestrator would have to record `input_tokens` / `output_tokens` per job (new D1 migration `0006_usage_tokens.sql`). Check first how the orchestrator reports state back to D1 before planning this.

## Done when

- [ ] Extract job runs on schedule; watermark advances; no `text`/`caption`/`summary`/`url` in any Databricks table
- [ ] Pipeline builds all 3 gold tables, and its expectations report dropped rows
- [ ] App shows the 4 panels from live gold data
- [ ] A short README section with a screenshot of the app and the pipeline graph

## Resume lines this would back (only after it's built)

- Built a **Lakeflow** pipeline on **Databricks** that ingests the bot's job history into **Delta Lake** bronze/silver/gold tables in **Unity Catalog**, cleaning and deduplicating it with **PySpark** and data-quality expectations.
- Shipped a **Databricks App** showing usage and pipeline health (success rate, p95 latency, retry outcomes) for the bot's 10+ beta users.
