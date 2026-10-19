# HaluMem eval of the fine-tuned 35B inside Graphiti (draft, 2026-10-19)

Parent: [finetune-35b-pilot.md](finetune-35b-pilot.md). Adapter: `aayush7511/qwen3.5-35b-a3b-graphiti-lora`
(checkpoint-200, 1.08 epochs, val loss 0.082).

## Overview

Run Graphiti over one HaluMem-Medium user with the fine-tuned model doing extraction, then score it with
HaluMem's official code and gpt-4o judge on all three tasks: memory extraction, memory updates and
question answering. Compare with the published leaderboard (Supermemory, Mem0, Zep, MemOS, Memobase)
to answer "are we anywhere close?". One user only; money is tight.

## Decided (Aayush, 2026-10-19)

- User: HaluMem-Medium user 2 (62 sessions, 661 memory points, 169 questions): smallest full user.
- Model routing: the fine-tuned model handles only Graphiti's entity and fact extraction (the steps it
  was trained on: `ExtractedEntities`, `ExtractedEdges`); every other Graphiti call (dedupe, summaries,
  contradiction checks) uses gpt-4.1-mini, as in production.
- Scope: extraction + memory updates + QA (not extraction only).
- Serving: vLLM on Modal, new workspace (`modal profile` `new`), base `unsloth/Qwen3.5-35B-A3B` + LoRA.
- Reranker: Graphiti's cross-encoder on gpt-4.1-nano (as in the Zep setup).
- Judge and answer model: gpt-4o, HaluMem's official setting (needed to compare with the leaderboard).
- HaluMem's prompts and scoring code are used unchanged (search, answer and judge), because that's how
  the leaderboard's memory providers were evaluated.
- If vLLM can't serve LoRA on the MoE experts, merge the adapter into the base weights (16-bit) and
  serve the merged model.

## Pipeline (follows HaluMem's `eval_zep.py`, Zep calls swapped for local Graphiti)

1. **Add:** each session's dialogue → Graphiti episodes for one group, in order, with the session's time
   as reference time (Graphiti 0.30.2, FalkorDB in local Docker, `text-embedding-3-small`).
2. **Extracted memories per session:** the facts Graphiti created from that session's episodes.
3. **Updates:** for each memory point with `is_update`, search the graph with its text (top 10).
4. **QA:** for each question, search the graph (10 edges with cross-encoder rerank + 10 nodes with RRF,
   like the Zep script), keep the context.
5. **Score:** HaluMem's `evaluation.py`, unchanged, with gpt-4o → extraction recall / weighted recall /
   precision / F1, update correct / hallucination / omission, QA correct / hallucination / omission.

## Cost (ask before each)

| Item | Estimate | Paid from |
|---|---|---|
| H100 serving the 35B + LoRA while 62 sessions are added (~1–2 h) | ~$4–8 | new Modal workspace (check credit + spending limit first) |
| gpt-4.1-mini for the other Graphiti steps | free data-sharing tokens (likely) | OpenAI |
| gpt-4o: extraction judge (661 memory points) | ~$8 | OpenAI |
| gpt-4o: 169 answers + judgments, update judgments | ~$3–4 | OpenAI |
| Embeddings + reranker | < $0.20 | OpenAI |

## Open questions

1. **Spend caps** (proposed): Modal GPU job hard timeout 2.5 h (~$10 on an H100); stop scoring if
   OpenAI spend for this run passes $15.

## Results (2026-10-19, user 2, all 62 sessions)

| Metric (%) | Ours: Graphiti + fine-tuned 35B | Supermemory | Mem0 | Zep | MemOS |
|---|---|---|---|---|---|
| Extraction recall | 12.9 (weighted 36.0) | 41.5 | 42.9 | – | 74.1 |
| Extraction F1 | 22.0 | 56.9 | 57.3 | – | 79.7 |
| Target precision | 73.5 | 60.8 | 60.9 | – | 59.6 |
| False-memory resistance | 72.6 | 51.8 | 56.8 | – | 44.9 |
| Update correct | 1.6 (omission 98.4) | 16.4 | 25.5 | 47.3 | 62.1 |
| QA correct / halluc. / omission | 55.0 / 21.3 / 23.7 | 54.1 / 22.2 / 23.7 | 53.0 / 19.2 / 27.8 | 55.5 / 21.9 / 22.6 | 67.2 / 15.2 / 17.6 |

Leaderboard rows are Halu-Medium averages over 20 users; ours is one user (169 questions, ±~4 points).
159 facts were extracted for 661 gold memories: the model keeps the core fact and drops reasons, feelings
and profile values (see specs/profile-attributes.md). Graphiti's default 10 previous sessions pushed one
extraction prompt past 32k tokens; the server ran at 65,536 from session 14 on.
Cost: OpenAI $5.56 ($4.87 gpt-4o; $0.69 gpt-4.1-mini at list, likely free tokens); Modal ≈ $3.09 metered
in the new workspace (weights download, a failed H100 try, the 2-session test, two H200 server starts).

## Out of scope

- Other HaluMem users, Halu-Long, baselines (zero-shot 35B, gpt-4.1-mini) — the leaderboard is the
  comparison. Training more epochs.

## How we know it works

- A 2-session dry run (fine-tuned model reachable, routing log shows extraction → fine-tuned, the
  rest → gpt-4.1-mini, valid JSON) before the full user.
- HaluMem's scorer produces all three metric groups for user 2; a side-by-side table with the
  leaderboard and our earlier Graphiti + DeepSeek extraction numbers.
