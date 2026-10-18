# Spec: Synthetic memory dataset (training + open eval)

**Type:** Spike plan (part of [graph-extraction-distillation.md](graph-extraction-distillation.md)) · **Status:** Draft · **Owner:** Aayush · **Drafted:** 2026-10-17

## Overview

We want to publish a small model that writes to a Graphiti memory graph well. HaluMem is the best public test of personal-memory extraction, but its license (CC-BY-NC-ND 4.0) lets us **report scores** on it and nothing more: no training on it, no modified copies, no commercial use. So we generate our own dataset with the same three layers (dialogues, gold memory points, questions) using an open model whose outputs we can train on and publish.

One pipeline, two outputs:
- **Open eval set:** dialogues + gold memory points + questions, released under an open license as a second benchmark.
- **Training data:** Graphiti's exact prompts paired with correct JSON answers from the teacher, kept only when they match the gold.

Baseline that motivates this (2026-10-17, `spikes/extraction-bench/README.md`): zero-shot Qwen3.5-4B gets 47.9% recall on Re-DocRED (gpt-4.1-mini 53.6%) but 26.0% on HaluMem (gpt-4.1-mini 59.8%). Most of the HaluMem gap is two habits in the entity step: listing only the speaker with every message index, and naming entities differently between steps. Correct examples in Graphiti's format are the direct fix.

## Decisions

| Question | Decision |
|---|---|
| Generator | **Open, distillable model only**: no OpenAI, Gemini or Claude outputs in anything we train on (their terms forbid building competing models; consumer subscriptions also aren't for bulk generation). ChatGPT/Gemini/Codex may help design prompts and spot-check samples |
| Where it runs | **vLLM on Modal**, batched, paid from the free monthly credit (billed $0). Workspace limit stays as Aayush set it |
| Pilot generator | **Qwen3.5-35B-A3B** (Apache 2.0, one A100). Swap for gpt-oss-120b or DeepSeek only if the pilot's quality check fails |
| Pipeline shape | **Lean:** each call gets a fixed context (persona card + running state summary + this session's plan), never the growing history. HaluMem's own generation was 92% input tokens |
| Gold memories | **Come from the plan, not from reading the dialogue.** The pipeline decides the facts first, then writes dialogue that reveals them, so the answer is known by construction |
| Independence from HaluMem | Our own persona design, prompts and generator. Never put HaluMem prompts, personas or examples into the pipeline. Automated overlap check before release |
| HaluMem's role | **Held-out test only.** Model selection uses our own validation split. HaluMem is run for final numbers |
| Pilot size | **5 users × 20 sessions** (~100 sessions, ~200K dialogue tokens) |

## Pipeline

Stages 1–6 are generation and stage 7 is training targets. Every stage writes JSONL to `spikes/memory-gen/out/<run>/`, so each stage can be rerun alone.

1. **Persona.** One card per user: name, age, city, job, family, health, hobbies, preferences, goals. Sampled from our own attribute lists, not HaluMem's template.
2. **Timeline.** 20 dated life events across months: job change, move, new relationship, illness, new hobby, plus some small daily ones. At least 5 events per user **change or contradict** an earlier fact (moves city, quits job, changes a preference).
3. **Session plans.** For each event, a plan: the date, 2–6 memory points the session must reveal (each with type persona/event/relationship, and `replaces` pointing to the old memory point for updates), and 1–2 distractor details that should **not** be remembered (the assistant's suggestions, hypotheticals).
4. **Dialogue.** A 10–20 turn user/assistant chat that reveals the plan's memory points naturally. Input: persona card + running state summary + session plan (~3–4K tokens).
5. **State update.** Rewrite the running summary after each session (current job, city, relationships, open storylines). It's the only memory carried forward.
6. **Questions.** Per user, from the plan: fact recall, update ("where does X live now?"), boundary ("what's X's middle name?" → unknown), multi-hop. Answers come from the plan.
7. **Training targets.** Run Graphiti with the teacher on train-split dialogues and log every call (`bench.py`'s `LOG_CALLS`). Keep an example only if its step's output agrees with the gold: entities cover the plan's entities, facts are supported, updates are linked.

### Verification (automated, before Aayush sees anything)
- **Reveal check:** a judge confirms each planned memory point is actually stated in its dialogue. Drop or regenerate sessions that miss any.
- **Leak check:** a judge confirms distractors aren't stated as the user's facts.
- **Overlap check:** n-gram overlap against HaluMem-Medium must be near zero.

## Output

| File | Contents |
|---|---|
| `users.jsonl` | persona card, timeline |
| `sessions.jsonl` | user id, date, dialogue, memory points (`content`, `type`, `replaces`, `importance`), distractors |
| `questions.jsonl` | question, answer, type, evidence memory points |
| `train_calls.jsonl` | Graphiti prompt name, messages, teacher JSON answer, pass/fail against gold |

Splits are **by user** (no user appears in two splits). After the pilot: train / val / test.

## Phases

1. **Prompts + pilot on 1 user** (Modal, minutes). Aayush reads 3 sessions end to end.
2. **Pilot: 5 users × 20 sessions** with the automated checks. Aayush spot-checks ~50 memory points.
3. **Baseline on the pilot eval:** gpt-4.1-mini, DeepSeek, Qwen3.5-4B through `bench.py` with the same judges. It has to rank models the same way HaluMem does, or the dataset isn't measuring the right thing.
4. **Training targets** for the train users (stage 7).
5. **Scale** only if phases 2–3 pass: ~30 users (20 train / 5 val / 5 test).

## Cost

| Step | Estimate |
|---|---|
| Pilot generation (5 users) | ~30–60 min of one A100 on Modal ≈ $1–2 of free credit |
| Automated checks | same GPU, minutes |
| Training targets (stage 7) | depends on the teacher (open question 1). DeepSeek V4.1 Flash on DeepInfra: ~$1 for the pilot's train users |
| **Billed** | **$0** on Modal (free credit). Any DeepInfra teacher spend comes out of the existing $5 prepaid |

Estimates come from HaluMem's recorded token counts and today's Modal throughput. Unverified until phase 1.

## Invariants

- Nothing from OpenAI, Google or Anthropic models enters training data.
- No HaluMem text, persona or prompt enters the pipeline. HaluMem is never trained on.
- Friends' and Aayush's real saves never enter this dataset.
- Gold comes from the plan, never from a model reading the dialogue.
- Every model pinned to an exact version. Modal servers are ephemeral and stopped after each phase.

## Open questions (Aayush to decide)

1. **Teacher for training targets.** DeepSeek V4.1 Flash is 92% of Opus on documents but only ~52% on hard personal sessions. Options: DeepSeek anyway (filtered by gold, so bad answers are dropped), DeepSeek V4 Pro, or a large open model on Modal.
2. **Document saves in scope?** Personal chat only (like HaluMem), or also article/link saves (closer to real bot use)?
3. **Release license** for the eval set (e.g. CC-BY 4.0), and whether to publish the generator prompts.
4. **Spot-check budget:** is ~50 memory points per batch OK?

## Out of scope

- Training the student (next spec).
- HaluMem official scoring and LongMemEval (separate eval work).
- The gold set from Aayush's own saves (still planned, separate).

## How we know it works

- Phase 1: Aayush reads 3 sessions and agrees they sound natural and the memory points match.
- Phase 2: ≥95% of planned memory points pass the reveal check, and the overlap check is near zero.
- Phase 3: the pilot eval ranks gpt-4.1-mini / DeepSeek / Qwen3.5-4B in the same order as HaluMem.
- Phase 4: a training set of Graphiti calls that pass the gold filter, covering every Graphiti step.
