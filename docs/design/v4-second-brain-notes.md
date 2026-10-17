# v4 notes: second brain + the extraction-cost bet (discussion, 2026-10-16/17)

**Status: discussion notes, nothing here is decided unless marked "Decided".** Source of the measurements: [spikes/extraction-bench/README.md](../../spikes/extraction-bench/README.md). Distillation plan: [specs/graph-extraction-distillation.md](../../specs/graph-extraction-distillation.md).

## Strategy: component, not product

- The "one bottleneck" to solve is **the cost of writing to a memory graph**. Measured: Graphiti processes 15–37× the content in tokens, ~99% input; ≈$12 per 1M content tokens at gpt-4.1-mini list price.
- As a product, a personal memory layer is crowded: **Supermemory** (≈$3M seed; profiles; Notion/Drive connectors; browser extension; MCP; $5 per 1M tokens after halving in May 2026; hosted extraction uses **in-house models**), **Cognee** ($1 per 1M tokens), **Mem0**, **Zep**, **Cloudflare Agent Memory** (private beta, Apr 2026, Llama 4 Scout on Workers AI). Supermemory's cheapness likely = own small models + fewer calls + deferred "dreaming" merges + Cloudflare infra; on HaluMem it gives up update accuracy (16% vs Zep/Graphiti 47%).
- Direction (agreed in conversation): keep the app as the **testbed and launch vehicle**; aim the industry contribution at a **component**: an open, cheap extraction model (or pipeline fixes) that every self-hosted memory system can use. An independent review lists "open-weights extraction models that match the proprietary ones" as the gap.
- "Just cheaper" alone doesn't win: cheap per-token models still pay the multiplier; levers are the multiplier (no context for documents, fewer/shorter calls, deterministic checks) and a distilled model.

## Teacher rules (Decided 2026-10-17)

- **No gpt-4.1-mini (or any OpenAI/Anthropic model) as a distillation teacher**: their terms forbid training competing models on outputs. OpenAI's own "Model Distillation" only distills into OpenAI-hosted models → not the open/local goal.
- Teachers must be open-weights with distillation-friendly licenses (DeepSeek MIT, Qwen/gpt-oss Apache 2.0; check GLM/Kimi terms). Frontier models (Claude Opus via subscription) are **ceiling references only**.
- OpenRouter: a small prepaid credit for benchmarks is OK; GPT-6 Astra on hold (too expensive); run Opus through the `claude -p` adapter on the subscription.

## Second brain: two kinds of memory

| | Personal memory | Content memory |
|---|---|---|
| Examples | "working on X", "late on the assignment", "going to Austin", "trying climbing" | articles, YouTube, Notion pages, PDFs |
| Previous-episode context | **recent personal saves only** (5–10) | **none** (better recall, cheaper) |
| Contradictions | constant → typed relations with single-valued rules as deterministic queries; LLM only for the rest | rare → skip |
| Plans vs facts | store status planned/doing/done/dropped (AgentMemGate problem) | n/a |
| Linked to the user | by extraction | by code: `you —SAVED/WATCHED→ item` |
| Model (current guess) | strongest available; distilled only once it matches | DeepSeek V4.1 Flash, thinking off, strict-schema fix |

Capture sources: Telegram (live), MCP connector + `kb-memory` skill (live), a **Claude plugin** (connector + skill + Claude Code hooks proposing memories), Codex/others via the same MCP, **Notion** (scheduled Worker sync, no Cloud Run polling), **YouTube watch history** (API doesn't expose it as far as known → Google Takeout import or a browser extension).

**Capture policy** (proposed): server-side rules, not prompts: per-category auto-save / ask first / never; sensitive exclusions (health, money, other people); per-source rules; daily caps. Claude only proposes; the server decides → independent of Claude/Codex.

## Conflicts to resolve

1. "Sending is the curation act" (v3) breaks with auto-capture → the capture policy *is* the curation decision ROADMAP flags as highest-risk.
2. Personal memories on OpenAI's **data-sharing** free tokens → OpenAI trains on them. Options: paid no-sharing tokens, a no-training provider, or the local distilled model.
3. Auto-capture multiplies saves → cost levers become required.
4. Head-on with Supermemory as a product; edges: update accuracy, ownership/local, plan-vs-fact.

## Open questions for Aayush

1. Confirmation default: v4's "Claude proposes, you confirm" for everything, or auto-save for low-risk categories?
2. First new source after the Claude plugin: Notion or YouTube history?
3. Personal data on the data-sharing free tokens: OK for now, or no-sharing from day one?
4. Plugin target: Claude Code (hooks), claude.ai (connector + skill), or both?
5. Production changes awaiting a tiny spec: `previous_episode_uuids=[]` for URL/PDF saves; recent-personal context for notes.
