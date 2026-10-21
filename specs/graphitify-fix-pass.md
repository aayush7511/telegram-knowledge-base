# Graphitify fix pass (draft, 2026-10-18)

Spike code in `spikes/memory-gen/`. Parent spec: [memory-dataset-generation.md](memory-dataset-generation.md).

## Overview

`to_graphiti.py` turns each planned memory into Graphiti pieces (entities + one edge) with one gpt-oss pass
(`graphitify.json`). On the 2-person test, the GRAPHITIFY v3 prompt still left mistakes: 7 flagged by
`check_pieces`, plus misses the checks can't see because the model dropped an entity from its list.
The fix pass repairs every miss after graphitify and before the training examples are written:

1. **Code fix** what code can fix safely.
2. **Model retry once**: re-ask gpt-oss for each memory still flagged, telling it what's wrong.
3. **Drop** every session that still has a flagged memory from the training examples (logged, not
   deleted): a target missing one fact would teach the model to skip facts that are in the chat.

Target: more than 95% of sessions kept across the whole set (per person is reported, not gated).

## Decided (Aayush, 2026-10-18)

- Full run: all ~30 people now, no spot-check first.
- The fix pass covers all misses: the 6 flag types and the hidden misses.
- One retry each, by code and by model. Anything still flagged: its session is dropped from training
  (no Jev, 2026-10-18).
- Done = more than 95% of sessions kept across the whole set. Below that: stop before writing the
  training file and look. (Was also per person; dropped 2026-10-18 after the full run kept 95.7% overall
  with 12 people under 95%, mostly from strict update-drift flags: "just drop the bad ones".)
- Hidden misses: flag a memory when the plan's `object` isn't the person and isn't in its entity list.
  Code drops obvious non-entities (dates, numbers, status words like "Active"); the model retry judges
  the rest against Graphiti's entity rules (specific enough for its own Wikipedia or database entry; not
  an abstract concept, feeling, descriptive phrase, sentence fragment or date) and adds the entity and
  edge when it is one ("crowded places", "hypertension", "Lima & Associados"), else it stays trait-only.
- Code fixes (step 1): split "X and Y" entities (edge to the first); fill dates (month → 1st of the
  month, a full date in the memory text fills a null `valid_at`). The plan-based fixes (add the plan's
  `object`, build the edge from the plan triple) are dropped: plan objects are often values, so hidden
  misses go to the model instead.
- Code also reformats relations to SCREAMING_SNAKE_CASE ("plans to travel" → `PLANS_TO_TRAVEL`).
- Dates follow Graphiti's own edge-prompt rules (`extract_edges.edge`, 0.30.2), since training targets
  that contradict the prompt teach the model to ignore it: an ongoing (present-tense) fact gets
  `valid_at` = the session's timestamp; an explicit date gives that date at 00:00:00; a year alone gives
  January 1st; a change or end sets `invalid_at`; no resolvable time leaves both null. This replaces our
  GRAPHITIFY rule of `valid_at: null` for standing facts.
- Job titles can be entities (Graphiti only rules out vague ones like "new role"). A job gives two
  edges when an employer is named: {name} WORKS_AT <employer> and {name} WORKS_AS <job title>; only the
  second when there's none ("Freelance Retail Consultant").
- Health conditions are facts: `{name} HAS_CONDITION hypertension`.
- Model retry: one call per person, with all of that person's flagged memories, the reason for each
  flag, and their other pieces (so update chains stay consistent).
- False positives are settled against the gold plan: a flagged name (e.g. "Retail Efficiency 101") that
  appears word for word in the plan's memory text or `object` is a real name, not a mistake.

## Data model

- In: `out/<run>/user{N}.json` (plans) + `graphitify.json` (`{user_id: {memory_id: {id, entities, edge}}}`).
- Data model change: a memory can now have more than one edge (jobs), so each item's `edge` becomes
  `edges` (a list, possibly empty).
- The date and job rules change the GRAPHITIFY prompt itself, so graphitify reruns on the full set.
- Out: `graphitify.json` repaired in place (original kept as `graphitify-raw.json`), plus
  `fix-log.json`: per memory, flags before, what changed (code / model / dropped), flags after.

## Operations

1. `check_pieces` → flags per memory (exists).
2. Code fixes → re-check.
3. Model retry for still-flagged memories → re-check.
4. Drop sessions with a still-flagged memory; report kept % overall and per person.
5. Write training examples from the repaired pieces (kept sessions only).

## Open questions

(none)

## Edge cases

Found while building and testing (2026-10-18); each was flagged to Aayush.

- **Gate was strict per person.** With 20 sessions, "more than 95%" meant 20/20. The per-person gate was
  dropped after the full run; the overall gate stays `>` 95%.
- **"X and Y" splitting.** Code splits only when every part is a proper name ("Portugal and Italy");
  descriptions stay whole ("red and purple lighting" is one entity in Graphiti's own example). Other
  joins go to the model retry.
- **Year-only dates are not filled by code.** "Postponed the launch to 2028" names a year that isn't when
  the fact became true; the model sets those under Graphiti's rules. Code fills full dates and months only.
- **Sessions gen.py excluded** (chat contradicts the plan) are left out of training and of the 95%
  denominator. Before this pass they went into the training file.
- **People with ids 10+** were skipped by `to_graphiti.py` (`user[0-9].json`); fixed.
- **Old caches** (single `edge`) are read as a one-edge list.

## Out of scope

- Merging different spellings of one entity within a person ("Lima & Associados" / "Lima & Associados Advogados").
- Repairing broken update chains in the plans (~10 of 262 in the full run).
- Regenerating chats or plans; this pass only touches graphitify pieces.
- Changing Graphiti's prompts or the training-example format.

## How we know it works

- Offline tests on `out/test3-gptoss` caches (v1/v2/v3): each flag type gets fixed, code fixes need
  no model, the log matches the before/after flags.
- On the full run: > 95% of sessions kept overall; per-person shares reported; spend reported per step.
