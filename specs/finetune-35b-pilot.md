# Fine-tune Qwen3.5-35B-A3B on the memory set, check against HaluMem (2026-10-18)

## Overview

Fine-tune Qwen3.5-35B-A3B on our synthetic Graphiti extraction examples
([aayush7511/graphiti-memory-synth](https://huggingface.co/datasets/aayush7511/graphiti-memory-synth), private),
then score only the fine-tuned model on one HaluMem user with HaluMem's official gpt-4o judge, to see
whether it is anywhere near the published memory systems. Money is tight: smallest run that answers
"are we close?".

## Decided (Aayush, 2026-10-18)

- Model: `unsloth/Qwen3.5-35B-A3B` directly (no 9B pilot).
- Where: Google Colab, opened in the desktop app's built-in browser, starting from Unsloth's official
  notebook `nb/Qwen3_5_MoE.ipynb`.
- Eval: fine-tuned model only (no zero-shot baseline), 1 full HaluMem-Medium user (~70 sessions,
  ~750 memory points, ~170 questions), official gpt-4o judge. Compared with the published HaluMem
  leaderboard (Supermemory, Mem0, Zep, MemOS, Memobase) and our earlier Graphiti + DeepSeek run.
- Serving for the eval: vLLM on Modal (`spikes/extraction-bench/modal_vllm.py`) with the LoRA adapter.

## Training setup (from Unsloth's Qwen3.5 guide + our data)

- bf16 LoRA, not 4-bit QLoRA (Unsloth: MoE QLoRA not recommended). Needs ~74 GB: an 80 GB GPU
  (Colab A100-80GB or H100).
- `max_seq_length` 6144: our train examples run median 3,389 tokens, max 5,695 (Qwen tokenizer,
  chat template applied); none fit 2048.
- LoRA r=16, alpha=16, dropout 0, q/k/v/o + gate/up/down; gradient checkpointing "unsloth"; batch 1.
- Loss on the assistant answer only (the gold JSON), thinking off (Graphiti calls the model without it).
- Train split only (742 examples, ~2.5M tokens/epoch); validation split for loss; 2 epochs.
- Output: LoRA adapter pushed to a private HF model repo.

## Cost (ask before each)

| Step | Estimate | Paid from |
|---|---|---|
| Training | ~1–1.5 h on an 80 GB GPU; exact rate shown in Colab before starting | Colab compute units |
| Graphiti ingesting 1 HaluMem user with the fine-tuned model | ~$3–6 | Modal credit (~$9 left this month; past $30 is billed) |
| gpt-4o judge, 1 user | ~$9 | OpenAI |

## Out of scope

- Zero-shot / gpt-4.1-mini baselines, full Halu-Medium, Halu-Long.
- Our own test split scoring (free; can be added later).

## How we know it works

- Training: loss falls on train and validation; adapter loads and answers a Graphiti prompt with valid JSON.
- Eval: HaluMem official scores (extraction recall / precision / F1, update and QA correct rates) for
  the one user, side by side with the leaderboard rows.
