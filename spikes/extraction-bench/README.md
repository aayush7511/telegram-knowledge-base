# Extraction benchmark spike (2026-10-17)

Throwaway benchmark for the **graph-extraction cost bet** (`specs/graph-extraction-distillation.md`): which model, prompt context and pipeline settings make writing to a Graphiti graph cheap *and* good, and which open model can be the distillation teacher. Everything here is a single run on small samples. **Treat the numbers as direction, not publishable results** (see "What's publishable").

## How to run

- Local FalkorDB (never production): `docker start falkordb-bench` (bound to `127.0.0.1:6379`; created with `docker run -d --name falkordb-bench -p 127.0.0.1:6379:6379 falkordb/falkordb`).
- `.env` (gitignored, never print it): `OPENAI_API_KEY` (embeddings, the judge, the gpt-4.1-mini baseline), `OPENROUTER_API_KEY`, `TEACHER_BASE_URL=https://openrouter.ai/api/v1`, `TEACHER_MODEL=deepseek/deepseek-v4.1-flash`, `TEACHER_KEY_ENV=OPENROUTER_API_KEY` (also an unused NVIDIA `TEACHER_API_KEY`).
- Python: `../../services/orchestrator/.venv/bin/python` (graphiti-core 0.30.2).
- Data: `python3 prep.py` downloads nothing; `data/` holds Re-DocRED test (5 docs used), HaluMem-Medium (user 0, first 10 sessions), `items.json`.

| Script | What it does |
|---|---|
| `bench.py <variants…>` | Runs Graphiti per variant into its own local graph, then a gpt-4.1-mini judge scores recall of gold facts. Prints recall, errors, calls, tokens, multiplier, minutes; saves `results/run-*.json` |
| `ctx.py A B C D` | Context-strategy spike: 30 HaluMem sessions + 5 articles + 5 hand-written update probes. `K=3` env sets context size |
| `steps.py` | Per-Graphiti-step token breakdown (baseline) |
| `debug_empty.py "<doc>"` | Logs every model call for one doc (answer, reasoning, host) |
| `claude_adapter.py` | OpenAI-compatible server on `127.0.0.1:8787` that answers with `claude -p` on the **Claude subscription** (no OpenRouter spend). Runs outside the repo with an empty MCP config, otherwise each call loads ~287K tokens of MCP tool definitions or the project CLAUDE.md |

Variant names in `bench.py`: `baseline` (gpt-4.1-mini), `baselinenoctx` (no previous episodes), `teacher…` (OpenRouter model from `TEACHER_MODEL`, or per-variant `TEACHER_MODEL_<NAME>` / `TEACHER_BASE_URL_<NAME>` / `TEACHER_KEY_ENV_<NAME>`). Name flags: `nothink` = reasoning disabled, `lowthink` = reasoning effort low (gpt-oss can't disable it), `frontier` = drop `temperature` (frontier reasoning models reject it), `noctx` = `previous_episode_uuids=[]`. Env: `DATASETS=redocred`, `RESUME=results/run-….json` (rerun only failed items).

Example (Opus on the subscription): start `claude_adapter.py`, then `DATASETS=halumem TEACHER_MODEL_TEACHERFRONTIERCLAUDE=opus TEACHER_BASE_URL_TEACHERFRONTIERCLAUDE=http://127.0.0.1:8787/v1 TEACHER_KEY_ENV_TEACHERFRONTIERCLAUDE=NO_KEY python bench.py teacherfrontierclaude`.

## Production cost (measured from the OpenAI dashboard, Oct 10–17)

- 10 saves, ~78K content tokens → **2.21M tokens processed (~28×)**; one day of long content was ~20×. **~99% is input** (Oct 11: 454.85K in / 5.35K out). Embeddings: 236 requests but only 9K tokens (≈0.02% of cost).
- List price (gpt-4.1-mini $0.40/$1.60 per 1M): **≈ $0.09 per save, ≈ $12 per 1M content tokens**; actual spend $0 (data-sharing free tokens).
- Scale: 1,000 users × 5 saves/day ≈ $13.5K/month at list; FalkorDB RAM ~0.2–0.6MB per save (~200–600GB for 1,000 heavy users) — extraction cost, not RAM, is the scaling wall.

## Per-step cost (`steps.py`, gpt-4.1-mini)

| Step | HaluMem share | Re-DocRED share |
|---|---|---|
| Extract facts | 28.9% | 37.2% |
| Extract entities | 26.4% | 14.3% |
| Decision: entity dedup (~11.6K tokens/call) | 24.3% | 16.9% |
| Decision: fact dedup + contradiction (65 small calls) | 14.7% | 20.4% |
| Entity summaries | 5.7% | 10.0% |

Extraction calls average ~11K input for ~2.8K of new dialogue: most input is the 10 previous episodes Graphiti attaches as context.

## Model results (same 15 items, same judge, list prices)

| Model (license) | Re-DocRED recall | HaluMem recall | HaluMem excl. profile session | Errors | $/1M content (HaluMem) |
|---|---|---|---|---|---|
| gpt-4.1-mini (ref, **not distillable**) | 53.6% | 59.8% | 33.7% | 0 | $6.32 |
| DeepSeek V4.1 Flash (MIT), thinking on, `json_object` | 36.1% | 56.8% | — | 2 empty docs | $9.32 (34× more output) |
| DeepSeek V4.1 Flash, thinking off, before fix | 49.5% | 39.1% | — | 3 | $3.09 |
| **DeepSeek V4.1 Flash, thinking off, with fix** | **63.4%** | 57.4% | 27.4% | **0** | **$2.69** |
| gpt-oss-120b (Apache 2.0), thinking low | 56.2% | 36.1% | 28.4% | 0 | $3.28 |
| Qwen3.5-35B-A3B (Apache 2.0), "thinking off" (didn't take effect: 109K output on 5 docs) | 39.7% | 52.7% | 21.1% | 1 | $4.93 |
| **Claude Opus 5** (ceiling; via subscription adapter; **not usable for training**) | **68.6%** | **71.6%** | **52.6%** | 0 | n/a |

- Documents: DeepSeek is ~92% of the frontier → good enough as a document teacher.
- Conversations/personal memory: DeepSeek is ~52% of Opus on the hard sessions → **not** good enough; Opus extracts far more facts (117 vs 73). Caveat: recall-only scoring rewards volume (see next steps).
- Re-DocRED without previous-episode context (gpt-4.1-mini): recall **53.6% → 65.5%**, cost −2% (docs too short to show savings).

## Failure modes found (and fixes)

1. **Schema echo.** Graphiti's `OpenAIGenericClient` sends `json_schema` without `strict` (raw Pydantic schemas violate OpenAI's strict subset), so many OpenRouter hosts don't enforce it; DeepSeek sometimes returned the schema itself → Pydantic `ValidationError` on `EdgeDuplicate` → whole save lost. Also rare runaway JSON (~25K chars). **Fix in `bench.py` `_CountingCompletions`:** `_strict()` rewrites the schema (closed objects, all fields required) + `"strict": true` + `provider.require_parameters`; `_bad_answer()` detects echo/unparseable answers and retries 2× with a correction; `max_tokens` capped at 8192. Result: 0 failures, big recall gain. **Candidate upstream PR to Graphiti.**
2. **Thinking models:** DeepSeek with thinking on sometimes reasons about 7 entities and outputs 1 (nondeterministic, same host; temperature 0 not honored) and writes ~30× more output. `reasoning: {enabled: false}` fixes both.
3. Hosting: NVIDIA NIM free DeepSeek/GLM-5.3-Flash timed out (>120s on a 7-word prompt); GLM-5.3 answered but took 600s/doc on Graphiti prompts. gpt-oss rejects disabling reasoning (use effort low). Frontier reasoning models reject `temperature` → with `require_parameters` OpenRouter returns "No endpoints found". OpenRouter balance ran out once (402: "can only afford N tokens").

## Context strategy spike (`ctx.py`, DeepSeek thinking off, 45-item timeline)

| Strategy (personal saves; articles get none except A) | Recall | Update recall | Probes | Personal input | Cost |
|---|---|---|---|---|---|
| A Graphiti default (last 10 of anything) | 51.9% | 54.8% | 5/5 | 2.63M | $0.45 |
| B no context | 40.5% | **9.6%** | 5/5 | 0.45M | $0.12 |
| C last 10 personal | 50.1% | 52.1% | 5/5 | 2.64M | $0.49 |
| C3 last 3 personal | 44.4% | 39.7% | 3/5 | 1.15M | $0.21 |
| D 10 most similar personal (embeddings) | 48.5% | 39.7% | 4/5 | 2.58M | $0.47 |

- Conversations need recent context (updates 10% → 55%); recency beats similarity; most value comes from the first few episodes.
- Probes didn't separate strategies: Graphiti finds old facts to invalidate through **graph search over facts**, not episode context (even B handled 5/5). Probe scoring is lenient and noisy.
- **Working rule:** documents/articles → no context; personal saves → recent personal saves only (5–10).

## What's publishable

- Now: the Graphiti structured-output fix (PR) and the cost anatomy (multiplier, 99% input, per-step split), with sample-size caveats.
- Not yet: model rankings and context effects (5 docs / 10–30 sessions / 1 user / 1 run / our own judge).

## Next steps (proposed, not decided)

1. Add a **precision/hallucination judge** (are extracted facts supported by the source?) and rescore existing runs from `results/*.json` (cents).
2. Personal-memory teacher candidates (distillable only): DeepSeek V4.1 Flash thinking on + fix; DeepSeek V4 Pro; Kimi K3 / GLM-5.3 (check licenses); merge 2–3 DeepSeek passes.
3. Benchmarks: HaluMem with official scoring, 3–5 users, recall + hallucination; a gold set from Aayush's own saves (~100) instead of relying on Re-DocRED (short Wikipedia, fixed 96 relations, ~70% ceiling); LongMemEval subset + the 30-question eval for end-to-end. Re-DocRED stays a sanity check. HaluMem is CC-BY-NC-ND: eval only, never training.
4. Scale-up for publication: ~50 Re-DocRED docs, 3–5 HaluMem users, 3 runs each.
5. Context size 5 for personal saves; deterministic contradiction checks for typed personal relations (single-valued `LIVES_IN`, `WORKS_AT`…) — worth ~20–30% of cost.
