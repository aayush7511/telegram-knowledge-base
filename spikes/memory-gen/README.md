# Synthetic memory dataset spike (2026-10-18)

Generates HaluMem-style users for training and evaluating Graphiti's extraction steps. Plan and decisions:
[specs/memory-dataset-generation.md](../../specs/memory-dataset-generation.md). Generated data goes to `out/` (gitignored).

**Idea:** decide the story first, then write chats that reveal it. Gold memories, update chains and
question answers come from the plan, so they're known before any model reads the chat.

| Script | What it does |
|---|---|
| `gen.py` | Per user: person card (seeded: gender, age, country, field, life stage, traits) → plan of dated sessions with structured memory points, updates (`replaces`) and false-claim distractors → `fix_plan` (moves sessions forward past planned events, retries the plan up to 2× on rule breaks) → one chat per session (parallel; "story so far" computed from the plan in code) → model check (missing / leaked / contradicted) → chat regenerated once on hard problems, else `excluded` → questions in 5 typed batches. Saves `user{N}-sessions.json` then `user{N}.json`; reruns resume. Budget guard stops new users when Modal usage ≥ `BUDGET_STOP` ($19) |
| `validate.py` | Free code-only checks: future dates, update chains, plan rules, chat format, questions, rough word-overlap "mentioned?" flag (noisy) |
| `fix_pass.py` | Graphitify fix pass ([spec](../../specs/graphitify-fix-pass.md)): checks (incl. hidden misses, gold-plan filter), code fixes, one gpt-oss retry per person, session drop + 95% gate. Tests: `../../services/orchestrator/.venv/bin/python -m pytest test_fix_pass.py -q` |
| `to_graphiti.py` | Plans → Graphiti 0.30.2 training examples (run with the orchestrator venv, which has graphiti-core): inputs built with Graphiti's own prompt functions (`extract_nodes.extract_message`, `extract_edges.edge`, 3 previous sessions), targets = `ExtractedEntities` / `ExtractedEdges` JSON. One model pass (`graphitify.json`, cached) decides entities and facts per memory |

## Running

Keys come from `../extraction-bench/.env` (must contain `DEEPINFRA_API_KEY` and `MODAL_VLLM_KEY`).

```bash
# DeepSeek on DeepInfra (paid)
GEN_MODEL=deepseek-ai/DeepSeek-V4.1-Flash RUN=myrun SEED=2 python gen.py --users 5 --sessions 20
RUN=myrun python to_graphiti.py
python validate.py out/myrun
```

gpt-oss-120b on Modal (free credit): start the server from `../extraction-bench`
(`MODEL=openai/gpt-oss-120b GPU=H100 modal serve modal_vllm.py`, refuses to start without `MODAL_VLLM_KEY`),
check that a request without the key gets 401, then run with
`GEN_MODEL=openai/gpt-oss-120b GEN_BASE_URL=<url>/v1 GEN_KEY_ENV=MODAL_VLLM_KEY REASONING=medium USERS_AT_ONCE=2 CONCURRENCY=32`.
Stop the Modal app by its id (`modal app stop -y <id>`) as soon as the run ends.

## Findings so far (one person per model, same seed)

| Generator | Plan | Chats | Own checker |
|---|---|---|---|
| DeepSeek V4.1 Flash | good (50–65 memories, 8–10 updates), 0 future dates in 100 sessions | natural | plausible, slightly strict |
| gpt-oss-120b, medium | good counts; future-dated events (repaired by `fix_plan`) | formal "business memo" tone before the casual-texting prompt | wrong 10/10 on "missing" before the prompt fix |
| gpt-oss-120b, low | 1 memory/session, 3 updates | natural | too strict |
| Qwen3.5-35B-A3B | sessions with 0 memories | emoji-heavy | broken |

## Known issues / next

- gpt-oss sometimes writes `"replaces": ["m3"]` (a list): crashed the retest in `fix_plan` → `validate.check_user`. Fixed: `validate.replaces_list` normalizes id/list/null; multi-id lists are flagged.
- Retest 2 (`out/test3-gptoss`, seed 3): user1 clean (50 memories, 9 updates, 0 plan problems, 1 missing, 0 excluded, 20 questions); user0 crashed when the chat checker hit `max_tokens=1000` (medium reasoning ate the budget, empty answer). Cap raised to 4000; user0 rerun clean (47 memories, 8 updates, 0 plan problems, 1 missing, 0 leaked, 0 excluded, 20 questions, no truncations). Remaining validate flags are only the noisy `mention` check.
- `to_graphiti` on test3-gptoss: 80 examples, but only 37/97 memories got a fact (first test: 64/96). Same model and prompt, so graphitify is inconsistent: hobbies/preferences got edges 12/15 times in test 1, 4/22 in test 3 (the GRAPHITIFY rule "habit → null" vs "specific things are entities" is ambiguous). Also 9 memories name 2+ entities but got no edge (e.g. son enrolled at a school, separation from Rogério, trip to Portugal/Italy), and some entities are abstract ("AI tools", "European legal tech trends"). Decided: hobbies/preferences are edges (LIKES/PREFERS/PRACTICES ... -> the activity or food). GRAPHITIFY tightened (edge never null with 2+ entities) and `to_graphiti` now prints memories with 2+ entities but no edge (offline: test 1 has 1, test 3 has 9). Rerun with the new prompt (`graphitify.json`; old in `graphitify-v1.json`): 90/97 facts, 0 two-entity misses; hobby edges good (PRACTICES yoga, PLAYS cricket). Overshoot: values as entities ("Active", "22% increase...", "national level"), values in relation names (POSTPONED_LAUNCH_TO_2028, INCREASED_DISTANCE_TO_4KM), compound entities ("Portugal and Italy"), and an update chain that drifts ("5 km morning run" -> "3 km morning run" -> "morning run", so the old fact can't be invalidated). Month-level dates ("in February 2026") still get valid_at null.
- GRAPHITIFY v3 (not yet run on a model): values only in the sentence, short verbs, one entity per name, updates keep the target (value changed) or the relation (thing replaced), month dates -> 1st of month; memory lines carry `(replaces mX: <earlier edge>)`. `check_pieces` flags: no edge with 2+ entities, long/value-carrying relations, digits/% in entity names (false positives: "Retail Efficiency 101"), "X and Y" entities, updates keeping neither target nor relation, month date with null valid_at. Offline on test3: v1 14 flags, v2 30. v3 on gpt-oss (test3, `graphitify.json`; v1/v2 kept as `graphitify-v1/-v2.json`): 77/97 facts, 7 flags (3 are false positives or borderline); update chains now hold (running 5→3→4 km stays PRACTICES running, coffee/latte stays PREFERS, MARRIED_TO→SEPARATED_FROM Rogério). Left: some trait-only misses where the model leaves the second entity out of the list, which hides it from the no-edge check ("dislikes crowded places", "aims to expand Lima & Associados", "Priya Nair began as COO"), and health conditions (hypertension) have no rule.
- Full run (`out/full-gptoss`, seed 10, 2026-10-18, $3.63 Modal): 30 people, 600 sessions, 1,471 memories, 262 updates, 600 questions; checker 59 missing / 11 leaked; 14 sessions excluded (2.3%). Leftover plan problems in 18 people: mostly cosmetic (type 'goal'/'health' x33, a session with 1 memory x22); ~10 broken update chains (replaced twice, replaces a later/unknown memory, unrelated relation). Several people over-use emojis (validate flags 67–152 per 20 sessions). Graphitify + fix pass ([spec](../../specs/graphitify-fix-pass.md), $0.80): 186 flagged memories -> 26; 25 sessions dropped, 561/586 kept (95.7%, gate is overall only); `train_graphiti.jsonl` = 1,122 examples (561 sessions × nodes + edges), 1,457 edges (valid_at: 825 session time, 587 explicit date, 45 null; 50 with invalid_at).
- Pilot (`out/pilot-v1`, DeepSeek, 5 users) was generated before the date-prefix and casual-style fixes.
- `valid_at` only for memories that say when something started/happened; standing facts get null.
