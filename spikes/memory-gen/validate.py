"""Free, code-only quality checks for generated users (no model calls).

    python validate.py out/pilot-v1 out/pilot2-gptoss-medium ...

Per user: dates, update chains, plan rules, chat format, questions, and a rough word-overlap check that
each memory is actually mentioned. Prints a summary per user and the first few problems of each kind.
Meaning-level contradictions ("co-owner" vs "the only owner") need a model; those aren't checked here.
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
LONG = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
STOP = set("the a an and or of to in on at for with is was are be has have had her his their its as by "
           "from that this it into about after before still now new more most very".split())
TYPES = {"persona", "event", "relationship"}


def dates_in(text: str) -> list[datetime]:
    out = []
    for y, m, d in ISO.findall(text):
        try:
            out.append(datetime(int(y), int(m), int(d)))
        except ValueError:
            pass
    for mon, d, y in LONG.findall(text):
        try:
            out.append(datetime.strptime(f"{mon} {d} {y}", "%B %d %Y"))
        except ValueError:
            pass
    return out


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2 and w not in STOP}


def replaces_list(p: dict) -> list[str]:
    """Ids a memory point replaces. Models write an id, a list of ids, null, "", "null" or "none"."""
    r = p.get("replaces")
    ids = r if isinstance(r, list) else [r]
    return [str(i).strip() for i in ids if i is not None and str(i).strip().lower() not in ("", "null", "none")]


def check_user(u: dict, min_updates: int) -> dict[str, list[str]]:
    probs = defaultdict(list)
    ss = u["sessions"]
    points = {p["id"]: (s, p) for s in ss for p in s["memory_points"]}

    # 1. dates
    prev = None
    for s in ss:
        day = datetime.strptime(s["date"], "%Y-%m-%d")
        if prev and day < prev:
            probs["dates"].append(f"s{s['index']} {s['date']} is before the previous session")
        prev = day
        texts = [("plan", p["fact"]) for p in s["memory_points"]] + \
                [("user", t["content"]) for t in s["dialogue"] if t["role"] == "user"]
        for where, text in texts:
            for d in dates_in(text):
                if d.date() > day.date():
                    probs["dates"].append(f"s{s['index']} ({s['date']}) {where} mentions future date "
                                          f"{d.date()}: {text[:90]!r}")

    # 2. update chains
    replaced = defaultdict(list)
    for s in ss:
        for p in s["memory_points"]:
            rs = replaces_list(p)
            if len(rs) > 1:
                probs["updates"].append(f"{p['id']} replaces {len(rs)} memories {rs} (want one)")
            if not rs:
                continue
            r = rs[0]
            replaced[r].append(p["id"])
            if r not in points:
                probs["updates"].append(f"{p['id']} replaces unknown {r}")
                continue
            old_s, old = points[r]
            if old_s["index"] >= s["index"]:
                probs["updates"].append(f"{p['id']} (s{s['index']}) replaces {r} from a later/same session")
            if old["subject"] != p["subject"] and old["relation"] != p["relation"]:
                probs["updates"].append(f"{p['id']} replaces {r} but shares neither subject nor relation: "
                                        f"{old['relation']} -> {p['relation']}")
    probs["updates"] += [f"{r} replaced more than once by {ids}" for r, ids in replaced.items() if len(ids) > 1]
    n_updates = sum(len(v) for v in replaced.values())
    if n_updates < min_updates:
        probs["plan"].append(f"only {n_updates} updates (want >= {min_updates})")

    # 3. plan rules
    seen = set()
    for s in ss:
        n = len(s["memory_points"])
        if not 2 <= n <= 6:
            probs["plan"].append(f"s{s['index']} has {n} memory points (want 2-6)")
        if not 1 <= len(s.get("distractors", [])) <= 2:
            probs["plan"].append(f"s{s['index']} has {len(s.get('distractors', []))} distractors (want 1-2)")
        for p in s["memory_points"]:
            if p["id"] in seen:
                probs["plan"].append(f"duplicate id {p['id']}")
            seen.add(p["id"])
            if p.get("type") not in TYPES:
                probs["plan"].append(f"{p['id']} has type {p.get('type')!r}")

    # 4. chat format
    emojis = 0
    for s in ss:
        roles = [t["role"] for t in s["dialogue"]]
        if not roles or roles[0] != "user" or any(a == b for a, b in zip(roles, roles[1:])):
            probs["chat"].append(f"s{s['index']} turns don't alternate starting with the user")
        for t in s["dialogue"]:
            emojis += len(EMOJI.findall(t["content"]))
            letters = [c for c in t["content"] if c.isalpha()]
            if letters and sum(not c.isascii() for c in letters) / len(letters) > 0.05:
                probs["chat"].append(f"s{s['index']} non-English text? {t['content'][:80]!r}")
    if emojis > len(ss) * 3:
        probs["chat"].append(f"{emojis} emojis across {len(ss)} sessions")

    # 5. questions
    latest = {}
    for s in ss:
        for p in s["memory_points"]:
            latest[p["id"]] = p
    for q in u.get("questions", []):
        ev = q.get("evidence", [])
        for e in ev:
            if e not in points:
                probs["questions"].append(f"{q['type']} question cites unknown {e}: {q['question'][:70]!r}")
        if q.get("type") == "boundary" and "unknown" not in q.get("answer", "").lower():
            probs["questions"].append(f"boundary answer isn't 'Unknown': {q['answer'][:60]!r}")
        if q.get("type") == "update":
            stale = [e for e in ev if e in replaced]
            if stale and not any(e not in replaced for e in ev):
                probs["questions"].append(f"update question cites only outdated memories {stale}: {q['question'][:70]!r}")

    # 6. memory actually mentioned (rough: share of the object's key words found in the user's turns)
    for s in ss:
        said = words(" ".join(t["content"] for t in s["dialogue"] if t["role"] == "user"))
        for p in s["memory_points"]:
            key = words(str(p.get("object", ""))) or words(p["fact"])
            if key and len(key & said) / len(key) < 0.34:
                probs["mention"].append(f"s{s['index']} {p['id']} key words barely in chat: {p['fact'][:80]!r}")
    return probs


def main(dirs: list[str]) -> None:
    for d in dirs:
        files = sorted(Path(d).glob("user[0-9].json"))
        users = [(f.name, json.loads(f.read_text())) for f in files] or \
            [(f"users.json[{i}]", u) for i, u in enumerate(json.loads((Path(d) / "users.json").read_text()))]
        for fname, u in users:
            n_sessions = len(u["sessions"])
            probs = check_user(u, min_updates=max(3, n_sessions * 2 // 5))
            total = sum(len(v) for v in probs.values())
            counts = ", ".join(f"{k} {len(v)}" for k, v in sorted(probs.items()) if v) or "none"
            print(f"\n{d}/{fname}  {u['persona']['name']}: {total} problems ({counts})")
            for k, v in sorted(probs.items()):
                for line in v[:3]:
                    print(f"   [{k}] {line}")
                if len(v) > 3:
                    print(f"   [{k}] ... {len(v) - 3} more")


if __name__ == "__main__":
    main(sys.argv[1:])
