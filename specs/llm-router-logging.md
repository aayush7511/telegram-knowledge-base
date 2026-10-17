# Spec: Router client + Graphiti call logging (phase 1)

**Type:** Integration · **Status:** Draft · **Owner:** Aayush · **Drafted:** 2026-10-16 · **Parent:** [graph-extraction-distillation.md](graph-extraction-distillation.md)

## Overview

A **router client** replaces `OpenAIClient` as Graphiti's `llm_client` in `services/orchestrator/graph.py`. For each model call it picks a route from the call's `prompt_name`. In this spec every route is still `gpt-4.1-mini`, so graph output doesn't change. It also **logs every call** (prompt, input, output, timing) to Cloud Run's logs. Those logs become the training-input pool and the gold-set source for later phases. A local script exports them before Cloud Logging's 30-day expiry. Ships before Oct 22.

## Decisions

| Question | Decision |
|---|---|
| Where logs go | **Cloud Run logs** (structured JSON on stdout). No new storage |
| Retention | **Until labeled**: an export script saves them to local `.jsonl` files, run by hand at least every 3 weeks (Cloud Logging deletes after 30 days) |
| Log entry over the size cap | **Split into numbered parts** sharing a `call_id`. The export script rejoins them |
| Logging fails | **Save continues** (best-effort, like status posts) |
| Routes in this spec | All `gpt-4.1-mini`. The route table exists but is empty |
| Ship | Before Oct 22 |

## Data model: one log record per call

| Field | Meaning |
|---|---|
| `type` | Always `"llm_call"` (the export script filters on it) |
| `call_id` | New UUID per call |
| `job_id` | The job whose save triggered the call |
| `prompt_name` | Graphiti's name, e.g. `extract_edges.edge` |
| `route` | Which route answered, e.g. `gpt-4.1-mini` |
| `fallback` | `true` if the chosen route failed and `gpt-4.1-mini` answered |
| `response_model` | Name of the Pydantic schema asked for, or `null` |
| `messages` | `[{role, content}]` |
| `output` | The dict returned to Graphiti, or `null` on error |
| `error` | Error message, or `null` |
| `latency_ms` | Wall time of the call |
| `logged_at` | ISO 8601 |

**Parts:** if the serialized record is over **200 KB** (leaves headroom under Cloud Logging's 256 KB entry cap), it's written as several entries instead. Each entry is `{type: "llm_call_part", call_id, part, parts, chunk}`, where the `chunk`s concatenated in `part` order are the full record's JSON.

## The router

- `RouterClient` subclasses Graphiti's `LLMClient` and overrides `generate_response(messages, response_model, max_tokens, model_size, group_id, prompt_name, *, attribute_extraction)`.
- It holds a **default client** (today's `OpenAIClient`, `gpt-4.1-mini`, temperature 0) and a **route table** `{prompt_name: client}`, empty in this spec.
- On each call: pick the client from the table (default if absent), call it, and if a routed (non-default) client raises, call the default. Then log and return the output, or re-raise if the default also failed.
- `job_id` reaches the router through a `contextvars.ContextVar` set by `write_episode` around `add_episode`.

## Who writes what

| Aayush (the meat, ~1–2h) | Claude (boilerplate) |
|---|---|
| `RouterClient.generate_response`: route choice, fallback, timing, building the record | `RouterClient` class shell, constructor, wiring into `get_graphiti()` |
| `log_entries(record) -> list[dict]`: serialize + split into parts over 200 KB | `job_id` context var + setting it in `write_episode` |
| Edge-case tests | Emitting entries to stdout as Cloud Run structured JSON |
| | `scripts/export_llm_logs.py`: `gcloud logging read` → rejoin parts → `data/llm-logs/*.jsonl` (gitignored) |
| | Main tests from the table below, deploy |

## Invariants

- Graph output is unchanged: with an empty route table, every call goes to the same `gpt-4.1-mini` client with the same arguments as today.
- A logging failure never fails the call or the save.
- An error from the default client still reaches Graphiti exactly as today (after it's logged).
- Every call produces exactly one record (as one entry, or as parts).
- No secrets in logs (no API keys or headers, only messages and output).

## Edge cases (Aayush to decide)

Questions to answer here before building:
- Graphiti's `generate_response` **edits `messages` in place** (it appends the JSON schema and the language instruction). Which version gets logged, before or after? And if a routed client fails, what does the default client receive?
- What does the record look like when `prompt_name` is `None`?
- Can a single message be bigger than 200 KB, and does splitting still work if so?
- What happens when Graphiti's response cache hits (it's off in our config)?

## Tests

Main cases (Claude writes these, failing first):

| # | Situation | Expected |
|---|---|---|
| 1 | Empty route table, call with `prompt_name="extract_edges.edge"` | Default client called once with the same args; output returned unchanged; one record with `route="gpt-4.1-mini"`, `fallback=false` |
| 2 | Route table maps a name to a client that raises | Default client answers; record has `fallback=true` |
| 3 | Default client raises | Error re-raised to the caller; record has `error` set, `output=null` |
| 4 | Record under 200 KB | `log_entries` returns 1 entry, `type="llm_call"` |
| 5 | Record over 200 KB | Several `llm_call_part` entries, each ≤ 200 KB; joining the chunks in order gives the original JSON |
| 6 | Logging raises | Call still returns the output |
| 7 | `write_episode` for job X | Every record from that episode has `job_id=X` |

Edge-case tests: Aayush writes these, from the section above.

## Out of scope

- Any non-default route (Jev and the small model are later specs).
- Friends' graphs and tagging logs by user. Today every write goes to `second-brain` (owner). This must be added once friends' graphs exist, since friends' saves are excluded from training.
- Labeling, scoring, training.
- Logging embedder or cross-encoder calls.

## How we know it works

- Tests 1–7 and Aayush's edge-case tests pass.
- After deploying, one real save ends `saved`, and its calls show up in Cloud Logging as `llm_call` entries with that job's `job_id`.
- `scripts/export_llm_logs.py` writes those calls to `data/llm-logs/`, with any parted records rejoined.
