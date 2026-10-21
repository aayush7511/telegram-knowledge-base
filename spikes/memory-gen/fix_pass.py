"""Graphitify fix pass (specs/graphitify-fix-pass.md): check -> code fixes -> one model retry per person
-> code fixes again -> drop sessions that still have a flagged memory.

No I/O here except the model call in `retry`; to_graphiti.py wires it up and writes the files.
"""
import json
import re

import validate

MONTH_YEAR = re.compile(rf"\b(?:in|during|since|from) ({validate.MONTHS}) (20\d\d)\b", re.I)
MONTH_NUM = {m: i + 1 for i, m in enumerate(validate.MONTHS.split("|"))}
STATUS = {"active", "inactive", "positive", "negative", "ongoing", "completed", "complete", "resolved",
          "pending", "done", "yes", "no", "true", "false", "high", "low", "none", "unknown"}
GATE = 0.95


def edges_of(it: dict) -> list[dict]:
    """A memory's edges; caches from before the `edges` list have a single `edge` (or null)."""
    if "edges" in it:
        return [e for e in it["edges"] or [] if e]
    return [it["edge"]] if it.get("edge") else []


def snake(rel: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", rel.strip()).strip("_").upper()


def not_an_entity(obj: str) -> bool:
    """Plan objects that can never be Graphiti entities: dates, numbers, bare status words."""
    return bool(re.search(r"\d", obj)) or obj.strip().lower() in STATUS


def explicit_date(text: str) -> str | None:
    """First explicit date in a memory's text as YYYY-MM-DD: a full date, else a month (its 1st)."""
    full = [d for d in validate.dates_in(text)]
    if full:
        return full[0].strftime("%Y-%m-%d")
    m = MONTH_YEAR.search(text)
    return f"{m.group(2)}-{MONTH_NUM[m.group(1).lower()]:02d}-01" if m else None


def is_date(v) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"\d{4}-\d\d-\d\d", v))


def check_item(name: str, p: dict, it: dict, items: dict) -> list[tuple[str, str]]:
    """(kind, message) flags for one memory's pieces."""
    flags, ents, edges = [], it.get("entities", []), edges_of(it)
    plan = f"{p['fact']} {p.get('object', '')}"
    if not edges:
        if len(set(ents)) > 1:
            flags.append(("no_edge", f"no edge but entities {ents}"))
        obj = str(p.get("object", "")).strip()
        if obj and obj != name and obj not in ents and not it.get("judged_trait") and not not_an_entity(obj):
            flags.append(("hidden_miss", f"plan object {obj!r} is not in the entity list"))
        return flags
    for e in edges:
        rel = e.get("relation", "")
        if re.search(r"\d", rel) or len(rel.split("_")) > 3:
            flags.append(("long_relation", f"relation not a short verb: {rel}"))
        elif rel != snake(rel):
            flags.append(("relation_format", f"relation not SCREAMING_SNAKE_CASE: {rel!r}"))
        for n in (e.get("source", ""), e.get("target", "")):
            if re.search(r"\d|%", n) and n not in plan:  # a name found word for word in the gold plan is real
                flags.append(("value_in_name", f"value in entity name: {n!r}"))
            if " and " in n:
                flags.append(("joined", f"two entities joined: {n!r}"))
    old = edges_of(items.get(p.get("replaces") or "") or {})
    if old and all(o["target"] != e["target"] and o["relation"] != e["relation"] for o in old for e in edges):
        flags.append(("update_drift", f"update keeps neither target nor relation of {p['replaces']}: "
                                      f"{old[0]['relation']} {old[0]['target']!r} -> "
                                      f"{edges[0]['relation']} {edges[0]['target']!r}"))
    if MONTH_YEAR.search(p["fact"]) and not any(is_date(e.get("valid_at")) or is_date(e.get("invalid_at"))
                                                for e in edges):
        flags.append(("missing_date", f"month date but no valid_at/invalid_at: {p['fact'][:80]!r}"))
    return flags


def check_all(users: list[dict], pieces: dict) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """{(user_id, memory_id): flags} for every flagged memory."""
    out = {}
    for u in users:
        uid, items = str(u["user_id"]), pieces.get(str(u["user_id"]), {})
        for s in u["sessions"]:
            for p in s["memory_points"]:
                f = check_item(u["persona"]["name"], p, items.get(p["id"]) or {}, items)
                if f:
                    out[(uid, p["id"])] = f
    return out


def code_fix(it: dict, p: dict) -> tuple[dict, list[str]]:
    """Code repairs for one memory (spec step 1). Returns the repaired item and what changed."""
    it, changes = json.loads(json.dumps(it)), []
    edges = edges_of(it)
    it["edges"] = edges
    it.pop("edge", None)
    for e in edges:  # relation format
        if e.get("relation") and e["relation"] != snake(e["relation"]) and not re.search(r"\d", e["relation"]):
            changes.append(f"relation {e['relation']!r} -> {snake(e['relation'])}")
            e["relation"] = snake(e["relation"])
    for e in edges:  # split "X and Y" when every part is a proper name ("red and purple lighting" stays)
        for side in ("source", "target"):
            parts = [x.strip() for x in re.split(r",\s*|\s+and\s+", e.get(side, "")) if x.strip()]
            if " and " in e.get(side, "") and len(parts) > 1 and all(x[0].isupper() for x in parts):
                changes.append(f"split {e[side]!r} -> {parts}")
                ents = [x for x in it.get("entities", []) if x != e[side]]
                it["entities"] = ents + [x for x in parts if x not in ents]
                e[side] = parts[0]
    day = explicit_date(p["fact"])
    if day and edges and not any(is_date(e.get("valid_at")) or is_date(e.get("invalid_at")) for e in edges):
        for e in edges:  # the memory states when it happened: that beats null or "session"
            changes.append(f"valid_at {e.get('valid_at')!r} -> {day} (from the memory text)")
            e["valid_at"] = day
    return it, changes


RETRY = """{rules}

Some of the pieces you made for {name} break these rules. Fix ONLY the memories listed under FIX, using
the problem noted for each. Keep the rest consistent with OTHER PIECES (same entity names, and for an
update the same target or relation as the memory it replaces).

A "plan object is not in the entity list" problem means: decide whether that object is a Graphiti entity,
something specific enough to have its own Wikipedia or database entry, and not an abstract concept,
feeling, descriptive phrase, sentence fragment, job description in vague words, status or date. If it is,
add it (in its most specific short form) and the edge to it. If it is not, return "edges": [] and
"trait": true.

FIX:
{fix}

OTHER PIECES:
{other}

Return JSON: {{"items": [{{"id": "m1", "entities": ["..."], "edges": [...], "trait": false}}]}}
with one item per memory under FIX, in the same edge format as above."""


async def retry(g, user: dict, items: dict, flags: dict, rules: str) -> dict:
    """One model call for one person: new pieces for each flagged memory (spec step 2)."""
    uid, name = str(user["user_id"]), user["persona"]["name"]
    points = {p["id"]: p for s in user["sessions"] for p in s["memory_points"]}
    mine = {mid: f for (u, mid), f in flags.items() if u == uid}
    fix = "\n".join(f"{mid}: {points[mid]['fact']}"
                    + (f" (replaces {points[mid]['replaces']})" if points[mid].get("replaces") else "")
                    + f"\n   current: {json.dumps({'entities': items.get(mid, {}).get('entities', []), 'edges': edges_of(items.get(mid, {}))}, ensure_ascii=False)}"
                    + "".join(f"\n   problem: {m}" for _, m in mine[mid]) for mid in mine)
    other = "\n".join(f"{mid}: " + "; ".join(f"{e['source']} {e['relation']} {e['target']}" for e in edges_of(it))
                      for mid, it in items.items() if mid not in mine and edges_of(it))
    r = await g.json(RETRY.format(rules=rules.split("MEMORIES:")[0].strip(), name=name, fix=fix, other=other),
                     0.0, 12000)
    out = {}
    for it in r.get("items", []):
        if it.get("id") in mine:
            if it.pop("trait", False) and not edges_of(it):
                it["judged_trait"] = True
            out[it["id"]] = it
    return out


def kept_sessions(users: list[dict], flags: dict) -> dict:
    """Which sessions survive (spec step 3): a session with any still-flagged memory is dropped.
    Sessions gen.py already excluded (chat contradicts the plan) are left out of training and of the %."""
    per_user, dropped, kept_ids = {}, [], set()
    for u in users:
        uid, kept, total = str(u["user_id"]), 0, 0
        for s in u["sessions"]:
            if s.get("excluded"):
                continue
            total += 1
            bad = [p["id"] for p in s["memory_points"] if (uid, p["id"]) in flags]
            if bad:
                dropped.append({"user": uid, "session": s["index"], "memories": bad})
            else:
                kept += 1
                kept_ids.add((uid, s["index"]))
        per_user[uid] = {"kept": kept, "total": total, "share": kept / total if total else 1.0}
    k, t = sum(v["kept"] for v in per_user.values()), sum(v["total"] for v in per_user.values())
    share = k / t if t else 1.0
    return {"kept": k, "total": t, "share": share, "per_user": per_user, "dropped": dropped,
            "kept_ids": kept_ids, "gate": share > GATE}  # overall only (Aayush, 2026-10-18); per person is reported
