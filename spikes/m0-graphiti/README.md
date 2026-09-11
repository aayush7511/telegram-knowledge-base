# M0 spike — Graphiti LLM comparison

Throwaway harness for [docs/design/v2.md](../../docs/design/v2.md) M0: run the same episodes through Graphiti with `gpt-4.1-mini` and `gpt-5-nano` (same model in both Graphiti slots), then compare tokens, time, schema retries, extraction quality, and `job_id`-style episode keying. Findings go into the design doc; this directory isn't production code.

## Setup

```bash
cd spikes/m0-graphiti
python3 -m venv .venv
.venv/bin/pip install "graphiti-core[falkordb,google-genai]==0.30.2" -r ../../services/orchestrator/requirements.txt
.venv/bin/playwright install chromium
docker run -d --rm --name falkordb-m0 -p 6379:6379 falkordb/falkordb:latest
```

Keys go in `services/orchestrator/.dev.vars` (gitignored): `OPENAI_API_KEY` — used for summaries, Graphiti's LLM, and embeddings (`text-embedding-3-small`).

Inputs (gitignored — they hold your own content):
- `urls.txt` — one blog URL per line. Pick 6–8, with 2–3 sharing a topic so entity dedup gets exercised.
- `notes.txt` — a few text notes, separated by blank lines, ideally touching the same topics. Notes are sent to OpenAI under the data-sharing program, so use ones you're fine sharing.

## Run

```bash
.venv/bin/python spike.py prepare --notes notes.txt          # → episodes.json (gpt-4.1-mini summaries, one pass)
.venv/bin/python spike.py run --model gpt-4.1-mini-2025-04-14  # → results/<model>.json + .md
.venv/bin/python spike.py run --model gpt-5-nano-2025-08-07
.venv/bin/python spike.py compare
```

Each run writes to its own FalkorDB graph (`m0_<model>`) and clears it first. To test a variant (e.g. a different episode format), pass `--episodes <file> --label <name>`; results land in `results/<model>+<name>.*`.

## What to look at

- `compare` — success rate, seconds/episode, tokens/episode (sets the free-token headroom), retries (schema failures), and the re-add check (new entities/facts after re-adding episode 1 under the same uuid — ideally 0/0).
- `results/<model>.md` — the entities and facts each model extracted, per episode. Read them side by side: are the entities real, are duplicates merged across related posts, are facts accurate to the summary?
