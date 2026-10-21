"""Turn generated users into Graphiti training examples (prompt in -> correct JSON out).

Inputs come from Graphiti 0.30.2's own prompt functions with the context Graphiti builds
(default entity types, previous episodes), so they match what the model sees in production.
Targets come from the story plan, not from a model reading the chat:

  1. graphitify (one model pass over the plans, cached in graphitify.json): for each memory point, the
     concrete entities it involves and its fact as source -> RELATION -> target, or no fact (a trait)
  2. fix pass (fix_pass.py, specs/graphitify-fix-pass.md): code fixes, one model retry per person, then
     sessions that still have a flagged memory are dropped; stops before writing if fewer than 95% are kept
  3. code: per kept session, ExtractedEntities and ExtractedEdges targets + the matching prompts

    RUN=pilot-v1 python to_graphiti.py

Files in out/<RUN>/: graphitify-raw.json (model pass, cached), graphitify-retry.json (retry answers,
cached), graphitify.json (repaired pieces), fix-log.json, train_graphiti.jsonl.
"""
import asyncio
import copy
import json
import os
import re
from datetime import datetime, timezone

from graphiti_core.prompts import prompt_library
from graphiti_core.utils.maintenance.node_operations import _build_entity_types_context

import fix_pass
import gen

CTX = 3  # previous sessions given as context (our working rule for personal saves: a few recent ones)
BATCH = 10  # memories per graphitify call: 30 overflowed 6000 tokens once answers carried edge lists + reasoning

GRAPHITIFY = """Convert these memories about {name} into knowledge-graph pieces, following these rules:
- Entities are concrete and identifiable: people, places, organisations, named or specific things
  ("Daejeon Metropolitan City Hall", "mint chocolate ice cream", "civil service exam").
- NEVER entities: pronouns, feelings, abstract concepts, generic nouns ("work", "food", "people"),
  descriptive phrases ("chronically late"), bare kinship words. Qualify unnamed relatives with the
  possessor ("{name}'s mother"); use the real name when given.
- Always refer to the person as "{name}".
- Jobs: the job title is an entity when it is specific ("Freelance Retail Consultant", "administrative
  intern"; not "new role"). With a named employer a job gives two edges: {name} WORKS_AT <employer> and
  {name} WORKS_AS <job title>; with no employer, only WORKS_AS.
- Health conditions are entities: "{name} has mild hypertension" -> edge {name} HAS_CONDITION mild hypertension.
- Hobbies, sports, activities and preferences ARE facts: the activity, food, drink, sport, genre or
  style is the entity, linked to {name} with LIKES, DISLIKES, PREFERS, PRACTICES, PLAYS, ENJOYS or similar:
  "{name} jogs three times a week" -> entities ["{name}", "jogging"], edge {name} PRACTICES jogging;
  "{name} prefers strong black coffee" -> edge {name} PREFERS strong black coffee;
  "{name} reads legal thrillers" -> edge {name} ENJOYS legal thrillers.
- Values live only in the fact sentence: quantities, distances, percentages, frequencies, statuses and
  dates never go in an entity name or a relation. The entity is the stable thing: "running", not
  "5 km morning run"; "Lima & Associados", not "22% increase in profitability".
- One entity per name: never join two with "and" ("Portugal", "Italy", not "Portugal and Italy"). When a
  memory names several, list them all as entities and link the edge to the main one.
- Relations are short verbs, one to three words: PRACTICES, PLAYS, PLANS_TO_OPEN, STOPPED,
  SEPARATED_FROM, PARENT_OF. Never put a value or detail in the relation (POSTPONED_LAUNCH_TO_2028 is wrong:
  POSTPONED, with "to 2028" in the sentence).
- Updates: a memory marked "(replaces mX ...)" changes an earlier fact; keep it linked so the old fact
  can be found and retired. When only a value changed, keep the same target and relation:
  "runs 5 km each morning" then "now runs 3 km" -> both {name} PRACTICES running. When the thing itself
  changed, the new thing is the target and the relation stays: "lives in Bengaluru" then "moved to
  Mumbai" -> {name} LIVES_IN Mumbai.
- A fact links two entities from the memory's entity list: source, relation (SCREAMING_SNAKE_CASE),
  target, a plain sentence, valid_at and invalid_at. The sentence states the fact without date prefixes
  ("As of 2025-10-17, ..." is wrong). If the entity list has two or more entities, "edges" is NEVER empty:
  link the two the memory is about. "edges" is empty only when {name} is the only entity
  (a personality trait, feeling, work style or vague goal: "{name} values privacy", "{name} prefers
  data-driven decisions").
- Dates follow Graphiti's rules. valid_at is when the fact became true or the event happened:
  an explicit date gives that date ("started a new job on 2026-03-02"); a month gives its first day
  ("moved to Austin in March 2026" -> 2026-03-01); a year alone gives January 1st; an ongoing fact stated
  in the present tense with no date ("lives in Daejeon", "likes mint ice cream") gives "session" (the
  chat's own time); otherwise null. invalid_at is set only when the memory says the fact ended or
  changed, with the same date rules ("stopped jogging on 2026-02-10" -> PRACTICES jogging, invalid_at
  2026-02-10); otherwise null.
MEMORIES:
{memories}
Return JSON: {{"items": [{{"id": "m1", "entities": ["..."], "edges": [{{"source": "...", "relation": "...",
  "target": "...", "fact": "...", "valid_at": "YYYY-MM-DD" or "session" or null, "invalid_at": "YYYY-MM-DD" or null}}]}}]}}"""


AS_OF = re.compile(r"^(As of|Since|On) [^,]{4,30}, ", re.I)  # safety net if a date prefix slips through


def valid_at(day: str | None, ref: datetime) -> str | None:
    """Graphiti's ISO 8601 format from YYYY-MM-DD, or the session's time for "session" (an ongoing fact)."""
    if day == "session":
        return ref.strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    try:
        return datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00.000000Z") if day else None
    except ValueError:
        return None


def iso(ts: str) -> datetime:
    return datetime.strptime(ts, "%b %d, %Y, %H:%M:%S").replace(tzinfo=timezone.utc)


def episode_text(name: str, turns: list[dict]) -> str:
    # "Name: text" lines: Graphiti treats the part before the first colon as the speaker, so clock times
    # (which contain colons) stay out of the line; the session's time goes in as Graphiti's reference time.
    return "\n".join(f"{name if t['role'] == 'user' else 'assistant'}: {t['content']}" for t in turns)


async def graphitify(g: gen.Gen, user: dict) -> dict:
    points = [p for s in user["sessions"] for p in s["memory_points"]]
    out = {}

    def replaces(p: dict) -> str:  # batches run in order, so an earlier batch's edge can be shown
        r = p.get("replaces")
        if not r:
            return ""
        e = fix_pass.edges_of(out.get(r) or {})
        return f" (replaces {r}: {e[0]['source']} {e[0]['relation']} {e[0]['target']})" if e else f" (replaces {r})"

    for i in range(0, len(points), BATCH):  # small batches keep answers short
        chunk = points[i:i + BATCH]
        r = await g.json(GRAPHITIFY.format(name=user["persona"]["name"], memories="\n".join(
            f"{p['id']}: {p['fact']} (planned as {p['subject']} | {p['relation']} | {p['object']}){replaces(p)}"
            for p in chunk)), 0.0, 12000)
        out.update({it["id"]: it for it in r["items"]})
    return out


def examples(user: dict, pieces: dict, kept: set) -> list[dict]:
    """Training rows for the sessions in `kept` ({(user_id, session index)}); earlier sessions of any kind
    still serve as previous-episode context, as they would in Graphiti."""
    name, rows = user["persona"]["name"], []
    entity_types = _build_entity_types_context(None)
    sessions = user["sessions"]
    for k, s in enumerate(sessions):
        if (str(user["user_id"]), s["index"]) not in kept:
            continue
        ref = iso(s["dialogue"][0]["timestamp"])
        prev = [{"content": episode_text(name, p["dialogue"]), "timestamp": iso(p["dialogue"][0]["timestamp"]).isoformat()}
                for p in sessions[max(0, k - CTX):k]]
        content = episode_text(name, s["dialogue"])
        entities = [name]  # Graphiti: always extract the speaker first
        edges = []
        for p in s["memory_points"]:
            it = pieces.get(p["id"]) or {}
            for e in it.get("entities", []):
                if e not in entities:
                    entities.append(e)
            for e in fix_pass.edges_of(it):
                if not (e.get("source") and e.get("target")):
                    continue
                for n in (e["source"], e["target"]):
                    if n not in entities:
                        entities.append(n)
                edges.append({"source_entity_name": e["source"], "target_entity_name": e["target"],
                              "relation_type": e["relation"], "fact": AS_OF.sub("", e["fact"]),
                              "valid_at": valid_at(e.get("valid_at"), ref),
                              "invalid_at": valid_at(e.get("invalid_at"), ref), "episode_indices": [0]})
        node_ctx = {"episode_content": content, "episode_timestamp": ref.isoformat(), "previous_episodes": prev,
                    "custom_extraction_instructions": "", "entity_types": entity_types,
                    "source_description": "chat with assistant"}
        edge_ctx = {"episode_content": content, "nodes": [{"name": n, "entity_types": ["Entity"]} for n in entities],
                    "previous_episodes": prev, "reference_time": ref, "edge_types": [],
                    "custom_extraction_instructions": ""}
        for step, msgs, target in (
                ("extract_nodes", prompt_library.extract_nodes.extract_message(node_ctx),
                 {"extracted_entities": [{"name": n, "entity_type_id": 0, "episode_indices": [0]} for n in entities]}),
                ("extract_edges", prompt_library.extract_edges.edge(edge_ctx), {"edges": edges})):
            rows.append({"user_id": user["user_id"], "session": s["index"], "step": step,
                         "messages": [{"role": m.role, "content": m.content} for m in msgs],
                         "target": json.dumps(target, ensure_ascii=False)})
    return rows


def load_users(out) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(out.glob("user*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
            if re.fullmatch(r"user\d+\.json", p.name)]


async def fix(users: list[dict], raw: dict, retried: dict, g_factory) -> tuple[dict, dict, dict]:
    """The fix pass over all users. `retried` caches retry answers per user (filled in place).
    Returns (repaired pieces, fix log, kept-sessions report)."""
    pieces, log = copy.deepcopy(raw), {}
    points = {(str(u["user_id"]), p["id"]): p for u in users for s in u["sessions"] for p in s["memory_points"]}

    def code_round(flags: dict, stage: str) -> None:
        for key in flags:
            uid, mid = key
            it, changes = fix_pass.code_fix(pieces[uid].get(mid) or {"id": mid, "entities": []}, points[key])
            pieces[uid][mid] = it
            if changes:
                log.setdefault(f"{uid}/{mid}", {})[stage] = changes

    flags0 = fix_pass.check_all(users, pieces)
    code_round(flags0, "code")
    flags1 = fix_pass.check_all(users, pieces)
    todo = [u for u in users if any(k[0] == str(u["user_id"]) for k in flags1) and str(u["user_id"]) not in retried]

    async def one(u: dict) -> None:  # one model retry per person with flags left; people run in parallel
        try:
            retried[str(u["user_id"])] = await fix_pass.retry(g_factory(), u, pieces[str(u["user_id"])], flags1,
                                                              GRAPHITIFY.format(name=u["persona"]["name"], memories=""))
        except RuntimeError as e:  # a failed retry fixes nothing: those memories stay flagged and get dropped
            print(f"  retry for user{u['user_id']} failed: {e}")
    await asyncio.gather(*(one(u) for u in todo))
    for u in users:
        uid = str(u["user_id"])
        for mid, it in retried.get(uid, {}).items():
            if (uid, mid) in flags1:
                pieces[uid][mid] = {**it, "id": mid}
                log.setdefault(f"{uid}/{mid}", {})["model"] = True
    flags2 = fix_pass.check_all(users, pieces)
    code_round(flags2, "code_after_model")
    flags3 = fix_pass.check_all(users, pieces)
    for key in set(flags0) | set(flags1) | set(flags3):
        e = log.setdefault(f"{key[0]}/{key[1]}", {})
        e["before"] = [m for _, m in flags0.get(key, [])]
        e["after"] = [m for _, m in flags3.get(key, [])]
    return pieces, log, fix_pass.kept_sessions(users, flags3)


async def main() -> None:
    for line in (gen.HERE.parent / "extraction-bench" / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    out = gen.OUT = gen.HERE / "out" / os.environ["RUN"]
    users = load_users(out)
    g = None

    def model() -> gen.Gen:
        nonlocal g
        if g is None:
            g = gen.Gen(os.environ.get("GEN_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash"),  # same settings as gen.py
                        os.environ.get("GEN_BASE_URL", "https://api.deepinfra.com/v1/openai"),
                        os.environ[os.environ.get("GEN_KEY_ENV", "DEEPINFRA_API_KEY")])
        return g

    raw_path, retry_path = out / "graphitify-raw.json", out / "graphitify-retry.json"
    raw = json.loads(raw_path.read_text()) if raw_path.exists() else {}
    async def one(u: dict) -> None:  # people in parallel; each person's batches stay in order
        raw[str(u["user_id"])] = await graphitify(model(), u)
        raw_path.write_text(json.dumps(raw, indent=1, ensure_ascii=False))
    errors = [e for e in await asyncio.gather(*(one(u) for u in users if str(u["user_id"]) not in raw),
                                              return_exceptions=True) if e]
    if errors:  # finished people are cached; a rerun only redoes the failed ones
        print(f"STOP: graphitify failed for {len(errors)} people ({errors[0]}); "
              f"{len(raw)}/{len(users)} cached in {raw_path.name}, rerun to continue")
        return
    retried = json.loads(retry_path.read_text()) if retry_path.exists() else {}
    try:
        pieces, log, report = await fix(users, raw, retried, model)
    finally:
        retry_path.write_text(json.dumps(retried, indent=1, ensure_ascii=False))
    (out / "graphitify.json").write_text(json.dumps(pieces, indent=1, ensure_ascii=False))
    (out / "fix-log.json").write_text(json.dumps({"report": {k: v for k, v in report.items() if k != "kept_ids"},
                                                  "memories": log}, indent=1, ensure_ascii=False))
    n_points = sum(len(v) for v in pieces.values())
    n_facts = sum(1 for v in pieces.values() for it in v.values() if fix_pass.edges_of(it))
    print(f"{len(users)} users; {n_points} memories -> {n_facts} with facts, {n_points - n_facts} trait-only; "
          f"{sum(1 for e in log.values() if e.get('before'))} flagged before fixes, "
          f"{sum(1 for e in log.values() if e.get('after'))} still flagged; model usage {g.usage if g else 'none'}")
    print(f"sessions kept {report['kept']}/{report['total']} ({report['share']:.1%}); per person: "
          + ", ".join(f"user{u} {v['kept']}/{v['total']}" for u, v in report["per_user"].items()))
    if not report["gate"]:
        print(f"STOP: 95% gate failed (overall {report['share']:.1%}). "
              f"train_graphiti.jsonl not written; see fix-log.json")
        return
    rows = [r for u in users for r in examples(u, pieces[str(u["user_id"])], report["kept_ids"])]
    with open(out / "train_graphiti.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} training examples written")


if __name__ == "__main__":
    asyncio.run(main())
