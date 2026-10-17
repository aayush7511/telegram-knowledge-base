---
name: build-the-core
description: Spec-first loop where Claude builds everything except the core and Aayush implements the core in 1–2 hours, like a "fix the failing tests" assessment. Use whenever Aayush brings a new feature ("I want X") or a problem ("this isn't working") to build in this repo, asks to start or continue a spec, or invokes /build-the-core. Covers drafting the spec, scoping the core, scaffolding stubs and failing tests, hand-off, assessment-style help while he codes, and review after.
---

# Build the core

Aayush works spec-first, the way a "fix the failing tests" assessment works: a written spec says what should happen, tests encode that spec, and code is done when the tests pass. The split: **Claude does everything except the core, and Aayush implements the core in 1–2 hours.**

## The loop

### 1. Spec: you draft it, he approves it

He'll give you either a problem ("this isn't working") or a feature ("I want X"). Turn it into a short spec before writing any code:

- **Overview:** what's broken or wanted, in user terms.
- **Expected behavior:** inputs, outputs and their exact shapes, and how state changes (what gets saved or changed).
- **Rules and edge cases:** defaults, errors, permissions, ordering, limits.
- **Out of scope:** what this spec does *not* cover.
- **Acceptance tests:** a list of test names, each one a requirement ("rejects an empty title", "a new post appears in the feed").

Base it on the actual code and on what he said. Ask him about anything you'd otherwise be guessing; he decides the rules and edge cases. **Stop and wait for his approval** of the spec before moving on.

### 2. Pick the core and scope it to 1–2 hours

Propose which part he implements. The core is:
- where the real logic or design decisions are (the algorithm, the data transformation, the state rules, the main query),
- the part he'd learn the most from,
- something he can finish in **1–2 hours**. If it's bigger, split the spec into smaller ones and pick one.

Everything else is yours: setup, configuration, wiring, routing and glue, UI or CLI shells, data models and seed data, fixtures, error handling around the core, logging, docs. Tell him in one or two lines what you're taking and what he's taking, plus a time estimate for his part. Wait for his OK.

### 3. Build everything except the core

- Match the project's existing style, conventions and tools. Don't add new frameworks or restructure anything without asking.
- Write the acceptance tests from the spec, using the project's test setup (see below). Test behavior through public interfaces, and check saved state where it matters. Keep tests deterministic.
- Leave the core as **stubs**: the real function or method signatures with a docstring or comment that restates the contract (inputs, outputs, rules from the spec), wired into everything else and raising "not implemented". Put no hints toward the solution in the stubs.
- Make running the tests easy: one command for everything, one command for only this spec's tests, and output that shows only failures.
- **Verify before handing off:** implement the core yourself in a scratch copy outside his repo (the session scratchpad), confirm every test passes there, then throw that copy away. His repo should end with only the core missing and only the core tests failing, while everything around it works.

### 4. Hand-off

Give him:
- the spec (saved in the repo as `specs/<name>.md`),
- the stub locations (`file:line`) and what each one must do,
- the command to run this spec's tests, and the starting count (X failing / Y passing),
- your time estimate.

Make sure his editor is open (see below).

### 5. While he implements the core

Act like an assessment's AI assistant. You may:
1. explain the spec,
2. clarify an error or a failing test,
3. answer questions about tools, commands and the codebase outside the core,
4. help with general syntax using generic examples.

Don't write the core, point to the bug, or give an example that's effectively the solution. If he asks for that, say so and offer what you can do instead. If he says "I'm stuck, help" or "time's up," switch to normal help: hints first (nudge → concept or docs pointer → pseudocode, one level per ask), then the solution if he asks.

He may also write extra edge-case tests himself; leave those to him.

### 6. After the tests pass

Review his core like a senior engineer: correctness beyond the tests, edge cases the spec missed, readability, performance where it matters, and alternative ways it could have been written with their tradeoffs. Suggest fixes and don't apply them unless he says so. Then finish the rest yourself (polish, docs, integration, deploy, any spec gaps you agreed to cover) and summarize what changed.

## Rules

- No code before the spec is approved.
- Tests come from the spec, not from the implementation.
- If the spec turns out to be wrong while he's building, update the spec first, then the tests, then the code.
- Respect the 1–2 hour time box: if his part grows past it, stop and re-scope with him.

## This project

- **Specs** live in `specs/<feature>.md`. Look at an existing one (e.g. `specs/summarize-retry.md`) for the house format: Overview, a Decisions table, Data model, Invariants, Edge cases, Tests table, Out of scope, How we know it works. A large feature gets an overview spec that links to per-phase specs, each sized to one 1–2h core (e.g. `specs/graph-extraction-distillation.md` → `specs/llm-router-logging.md`).
- **Repo rules still apply** (CLAUDE.md): the $0/month constraint, state-machine discipline, no mocked Cloudflare bindings, secrets never in code or logs.
- **Tests per component:**
  - `services/orchestrator` (Python): `pytest` from that directory (uses `.venv`); one spec's tests: `pytest test/test_<name>.py -q`; failures only: add `-q --no-header -rf`.
  - `workers/*` (TypeScript): `npm test` in that worker's directory (vitest + `@cloudflare/vitest-pool-workers`, runs in real `workerd`); one file: `npx vitest run test/<name>.test.ts`.
- **Editor:** Aayush codes in code-server in the desktop app's browser pane. Start it with the `code-server` entry in `.claude/launch.json` (`preview_start` with name `code-server`; 127.0.0.1:8080, auth none). If it opens a different folder, navigate to `http://localhost:8080/?folder=<repo absolute path>`. Workspace trust is his to grant.
