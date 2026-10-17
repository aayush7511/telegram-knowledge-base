# Spec: Small model + Jev for Graphiti's model calls

**Type:** Overview: each phase gets its own spec, sized so its core code is a 1–2h session for Aayush · **Status:** Draft · **Owner:** Aayush · **Drafted:** 2026-10-16

## Overview

Writing a save to the graph costs several `gpt-4.1-mini` calls through Graphiti. Those calls are the main reason for the token bill and the per-user daily caps. Graphiti's docs warn against small models: they break on the JSON for dedup and invalidation. This spec splits Graphiti's model calls by kind:

- **Text-writing steps** (extracting entities, facts, timestamps, attributes and summaries) go to a **small distilled model**. To build it, we take a strong open-weights *teacher*, check that it beats `gpt-4.1-mini`, then distill it into the smallest *student* that keeps ≥95% of its quality. The student runs on the home Mac and is published on Hugging Face.
- **Decision steps** (entity dedup, plus duplicate and contradicted facts) go to **TypeSafe Jev**, but only once Jev beats `gpt-4.1-mini` on the gold set.

The goal is a component that other Graphiti users can adopt. Lowering our own bill is a side effect.

## Decisions

| Question | Decision |
|---|---|
| Who does text-writing steps | Small distilled student |
| Who does decision steps | Jev, "for right now" |
| Jev billing | **Prepaid OpenRouter credit, auto-recharge off**: the same pattern as the OpenAI exception. Spend can never exceed the prepaid amount. No free tier exists (checked 2026-10-16). Pinned to `typesafe/jev-1.13` |
| Jev's bar for production | **Beats** `gpt-4.1-mini` on the gold set's dedup + invalidation scores |
| Teacher's bar | **Beats** `gpt-4.1-mini` on the gold set's per-step scores **and** the 30-question retrieval eval |
| No teacher passes | **Try more teachers** (bigger models, other families) before giving up |
| Student's bar | Smallest student whose end-to-end retrieval score is **≥95% of the teacher's** |
| Gold set | **~100 items**, labeled by Aayush |
| Teacher training data | **Owner saves + public text**. Friends' saves are excluded |
| Where the teacher runs | **Free hosted APIs** (OpenRouter free models, Groq free tier). Accepted: owner saves sent there may be logged by the provider |
| Student offline (Mac asleep) | **Fall back to `gpt-4.1-mini`**. Saves never wait |
| Scope | Whole pipeline in one spec, phased |
| Timing | Start now, in parallel with the Oct 22 launch |

## How it plugs in

Graphiti calls `llm_client.generate_response(..., prompt_name=...)` for every model call (graphiti-core 0.30.2, pinned). A **router client** replaces `OpenAIClient` in `services/orchestrator/graph.py` and dispatches each call on `prompt_name`:

| `prompt_name` | Kind | Route (when its phase passes) |
|---|---|---|
| `extract_nodes.extract_text` / `extract_message` / `extract_json` | Text-writing | Student |
| `extract_edges.edge` | Text-writing | Student |
| `extract_nodes_and_edges.extract_message` | Text-writing | Student |
| `extract_edges.extract_timestamps` / `extract_timestamps_batch` | Text-writing | Student |
| `extract_nodes.extract_attributes`, `extract_edges.extract_attributes` | Text-writing | Student |
| `extract_nodes.extract_summaries_batch` / `extract_entity_summaries_from_episodes` | Text-writing | Student |
| `dedupe_nodes.nodes` → `NodeResolutions` | Decision | Jev: one **Choice** per entity over its candidates + "none" |
| `dedupe_edges.resolve_edge` → `EdgeDuplicate` | Decision | Jev: per existing fact, two **Noul** checks (duplicate? contradicted?) |
| anything else / any route failing | — | `gpt-4.1-mini` (today's behavior) |

Until a phase passes its gate, its steps stay on `gpt-4.1-mini`. The router is the only production code change. Embeddings and the cross-encoder are untouched.

## Phases

Each phase has its own spec in `specs/`; this doc holds the shared decisions.

| # | Spec | Status |
|---|---|---|
| 1 | [llm-router-logging.md](llm-router-logging.md): router + call logging | Draft |
| 2 | Jev adapter (`dedupe_nodes.nodes`, then `resolve_edge`) | Not started |
| 3 | Baseline scorer (gold set vs. models) | Not started |
| 4–7 | Teacher labeling, distill, serve, publish | Not started |


1. **Log.** The router records every Graphiti call in production: prompt name, input messages, response schema, output, model, tokens, latency, job id and user. It changes no routes. This produces the training-input pool and the gold-set source.
2. **Gold set.** Aayush labels ~100 owner saves: the correct entities, facts, duplicate entities, duplicate facts and contradicted facts.
3. **Baseline.** Run `gpt-4.1-mini`, 2–3 open teacher candidates and Jev (decision steps only) over the gold set using Graphiti's real prompts. Score:
   - quality per step;
   - valid-JSON rate;
   - end-to-end: build a separate FalkorDB graph per model and run the 30-question retrieval eval on it.

   Gates: the teacher must beat `gpt-4.1-mini`, and Jev must beat `gpt-4.1-mini` on the decision steps. If Jev passes, decision steps switch to Jev in production.
4. **Label.** The winning teacher labels owner saves plus public text for the text-writing steps only.
5. **Distill.** LoRA-train students at a few sizes on Kaggle's free GPUs. Pick the smallest that meets ≥95% of the teacher.
6. **Serve.** The student runs on the home Mac behind the same Tailscale Funnel + `X-KB-Secret` pattern as the YouTube worker, as an OpenAI-compatible endpoint. The router sends text-writing steps there and falls back to `gpt-4.1-mini` on any failure.
7. **Publish.** Weights + GGUF on Hugging Face. The gold set and eval code are published only if Aayush decides to (see open questions).

## Invariants

- A save never fails because of the router. Any student or Jev error falls back to `gpt-4.1-mini` within the same request.
- Friends' saves never enter training data or the published gold set.
- Jev spend can never exceed the prepaid OpenRouter credit (auto-recharge off).
- A route switches to the student or Jev only after its gate passes on the gold set.
- Every model is pinned to an exact version: teacher, student and Jev.
- Cloud Run stays request-triggered. Calls to the Mac or Jev happen inside the job's request.

## Open questions (Aayush to decide)

1. ~~**Where logs live.**~~ Decided 2026-10-16: Cloud Run logs, exported to local files before the 30-day expiry, kept until labeled. See spec 1.
2. **How the gold set gets labeled.** Correct `gpt-4.1-mini`'s pre-filled outputs (fast, but biased toward it), or label from scratch (slow, unbiased)?
3. **Teacher candidates.** Which 2–3 models? Each must have a license that allows training on its outputs, and the free API's terms must allow it too.
4. **Public text.** Which sources, and how many items, for training volume?
5. **Student sizes and base model.** Which family, and which sizes (e.g. ~0.5B / 1.5B / 3B)?
6. **Prepaid amount for Jev** on OpenRouter.
7. **What gets published.** The model only, or also the gold set (it's your saves) and the eval code?
8. ~~**Launch-week risk.**~~ Decided 2026-10-16: spec 1 (logging only, every route still `gpt-4.1-mini`) ships before Oct 22.

## Out of scope

- The plan-vs-fact gate (AgentMemGate-style) and relevance filtering at search time. They're decision steps Jev could do, but they're new behavior, not existing Graphiti calls, so they get separate specs.
- Replacing Jev with the student for decision steps (possible later).
- Embeddings and the cross-encoder.
- Changing Graphiti's prompts. They stay as pinned in 0.30.2, so outputs remain comparable to `gpt-4.1-mini`.

## How we know it works

- Phase 1: every Graphiti call for a test save appears in the log with prompt name, input and output, and the save still ends `saved`.
- Phase 3: a results table of each model × each step score, valid-JSON rate and retrieval-eval score, with gate pass or fail recorded.
- Phase 6: a save with the Mac on uses the student for text-writing steps (visible in the log). With the Mac off, it falls back to `gpt-4.1-mini` and still ends `saved`.
- End state: OpenAI token use per save drops, and the 30-question retrieval score is no worse than `gpt-4.1-mini` today.

## Follow-ups once approved

- Add the Jev exception to the CLAUDE.md hard-constraint section.
