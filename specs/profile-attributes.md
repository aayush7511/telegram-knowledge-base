# Capture profile values in Graphiti (draft, 2026-10-19)

Follows: [halumem-eval-35b.md](halumem-eval-35b.md).

## Overview

In the 2-session HaluMem test (user 2, the profile-heavy first sessions), Graphiti with the fine-tuned
extractor fully captured 8 of 26 gold memories. Most misses were profile values with no second entity
to link to: gender, age, birth date, monthly income, savings, health status, "no children", "dating".
Graphiti stores memories only as facts between two entities, and its own extraction prompt bans dates,
numbers and statuses as entities, so these values are dropped by design. The entity summaries just repeat
the facts, so the values aren't stored anywhere. Our training targets followed the same rules (values only
in the sentence, one-entity memories are trait-only), so the fine-tuned model drops them on purpose.

This spec is about storing those values so a memory system built on Graphiti can recall them.

## Candidate approaches

1. **Graphiti custom entity types.** Define a `Person` entity type with fields such as gender, birth date,
   income, savings, physical / mental health, relationship status, children. Graphiti then runs its
   `extract_nodes.extract_attributes` call and stores the values as node attributes. The HaluMem runner
   would count those attributes as extracted memories (as the Zep eval counts entity summaries).
2. **Training targets that anchor details.** Graphiti's edge prompt (rule 3) says not to drop concrete
   details but to attach them to a second entity (`Entity -> HAS_ATTRIBUTE -> detail-entity`). Our
   GRAPHITIFY targets could do that instead of marking the memory trait-only.

## Open questions

1. Which approach (or both)? Approach 1 adds a model call per entity (`extract_attributes`) on
   gpt-4.1-mini, or the fine-tuned model if we train that step too; approach 2 changes the training data
   and needs a retrain.
2. Which fields go on `Person`? HaluMem's persona fields are one source; our own saves are another.
3. Should attributes count toward HaluMem "extracted memories" in our runner? (Fair only if the other
   providers' extracted memories include profile fields the same way.)
4. Does this go to production (the friends' graphs) or stay an eval experiment?

## Out of scope

- Changing Graphiti's prompts. Rerunning other benchmarks.

## How we know it works

- (To fill once the approach is chosen.) Same 2 profile sessions of HaluMem user 2: gold memories captured
  goes up from 8/26 without precision dropping.
