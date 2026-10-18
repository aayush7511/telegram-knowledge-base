"""Offline tests for the graphitify fix pass (specs/graphitify-fix-pass.md). No model calls.

    ../../services/orchestrator/.venv/bin/python -m pytest test_fix_pass.py -q
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import fix_pass
import to_graphiti

NAME = "Rohan Mahesh Patel"
REF = datetime(2026, 3, 20, 9, 30, tzinfo=timezone.utc)


def mem(mid="m1", fact="Rohan Mahesh Patel plays cricket.", obj="cricket", replaces=None):
    return {"id": mid, "fact": fact, "subject": NAME, "relation": "PLAYS", "object": obj, "replaces": replaces}


def edge(target="cricket", relation="PLAYS", valid_at=None, invalid_at=None, source=NAME):
    return {"source": source, "relation": relation, "target": target, "fact": "x", "valid_at": valid_at,
            "invalid_at": invalid_at}


def kinds(flags):
    return {k for k, _ in flags}


# --- data model ---

def test_edges_of_reads_old_and_new_caches():
    assert fix_pass.edges_of({"edge": edge()}) == [edge()]
    assert fix_pass.edges_of({"edge": None}) == []
    assert fix_pass.edges_of({"edges": [edge(), edge("tennis")]}) == [edge(), edge("tennis")]


def test_valid_at_session_becomes_the_session_time():
    assert to_graphiti.valid_at("session", REF) == "2026-03-20T09:30:00.000000Z"
    assert to_graphiti.valid_at("2026-02-01", REF) == "2026-02-01T00:00:00.000000Z"
    assert to_graphiti.valid_at(None, REF) is None


# --- checks ---

def test_hidden_miss_flags_a_real_entity_left_out():
    p = mem(fact="Rohan Mahesh Patel still dislikes crowded places.", obj="crowded places")
    assert kinds(fix_pass.check_item(NAME, p, {"entities": [NAME], "edges": []}, {})) == {"hidden_miss"}


@pytest.mark.parametrize("obj", ["Active", "positive", "50% of target", "2026-07-05", "22% increase in 2025"])
def test_hidden_miss_skips_obvious_non_entities(obj):
    assert fix_pass.check_item(NAME, mem(obj=obj), {"entities": [NAME], "edges": []}, {}) == []


def test_hidden_miss_cleared_once_the_model_judged_it_a_trait():
    it = {"entities": [NAME], "edges": [], "judged_trait": True}
    assert fix_pass.check_item(NAME, mem(obj="high level of privacy"), it, {}) == []


def test_gold_plan_settles_value_false_positives():
    p = mem(fact="Rohan Mahesh Patel hosted the webinar Retail Efficiency 101.", obj="Retail Efficiency 101")
    assert fix_pass.check_item(NAME, p, {"entities": [NAME], "edges": [edge("Retail Efficiency 101", "HOSTED")]}, {}) == []
    p = mem(fact="Rohan Mahesh Patel runs 5 km each morning.", obj="running")
    flags = fix_pass.check_item(NAME, p, {"entities": [NAME], "edges": [edge("5 km morning run", "PRACTICES")]}, {})
    assert kinds(flags) == {"value_in_name"}


def test_two_entities_and_no_edge_is_flagged():
    flags = fix_pass.check_item(NAME, mem(), {"entities": [NAME, "cricket"], "edges": []}, {})
    assert "no_edge" in kinds(flags)


def test_update_drift_flags_only_when_target_and_relation_both_change():
    old = {"edges": [edge("Bengaluru", "LIVES_IN")]}
    p = mem("m2", "Rohan Mahesh Patel moved to Mumbai.", "Mumbai", replaces="m1")
    keeps_rel = {"edges": [edge("Mumbai", "LIVES_IN")]}
    drifts = {"edges": [edge("Mumbai", "MOVED_TO")]}
    assert fix_pass.check_item(NAME, p, keeps_rel, {"m1": old}) == []
    assert kinds(fix_pass.check_item(NAME, p, drifts, {"m1": old})) == {"update_drift"}


# --- code fixes ---

def test_code_fix_reformats_relations():
    it, changes = fix_pass.code_fix({"entities": [NAME, "Portugal"], "edges": [edge("Portugal", "plans to travel")]}, mem())
    assert it["edges"][0]["relation"] == "PLANS_TO_TRAVEL" and changes


def test_code_fix_splits_proper_names_but_not_descriptions():
    it, _ = fix_pass.code_fix({"entities": [NAME, "Portugal and Italy"], "edges": [edge("Portugal and Italy", "VISITED")]}, mem())
    assert it["edges"][0]["target"] == "Portugal" and {"Portugal", "Italy"} <= set(it["entities"])
    it, changes = fix_pass.code_fix({"entities": [NAME, "red and purple lighting"],
                                     "edges": [edge("red and purple lighting", "OWNS")]}, mem())
    assert it["edges"][0]["target"] == "red and purple lighting" and not changes


@pytest.mark.parametrize("fact,day", [
    ("Rohan Mahesh Patel started swimming in August 2026.", "2026-08-01"),
    ("Rohan Mahesh Patel moved to Mumbai on 2026-03-15.", "2026-03-15"),
    ("Rohan Mahesh Patel stopped jogging on February 10, 2026.", "2026-02-10"),
])
def test_code_fix_fills_dates_from_the_memory_text(fact, day):
    it, _ = fix_pass.code_fix({"entities": [NAME, "x"], "edges": [edge("x", valid_at="session")]}, mem(fact=fact))
    assert it["edges"][0]["valid_at"] == day


def test_code_fix_keeps_a_date_the_model_already_gave():
    it, changes = fix_pass.code_fix({"entities": [NAME, "x"], "edges": [edge("x", valid_at="2026-08-03")]},
                                    mem(fact="Rohan Mahesh Patel started swimming in August 2026."))
    assert it["edges"][0]["valid_at"] == "2026-08-03" and not changes


# --- drop + gate ---

def users_with(n_sessions=20, excluded=()):
    return [{"user_id": 0, "persona": {"name": NAME}, "sessions": [
        {"index": i, "excluded": i in excluded, "memory_points": [mem(f"m{i}")]} for i in range(1, n_sessions + 1)]}]


def test_kept_sessions_drops_sessions_with_flags_and_skips_excluded():
    r = fix_pass.kept_sessions(users_with(excluded={3}), {("0", "m5"): [("hidden_miss", "x")]})
    assert (r["kept"], r["total"]) == (18, 19) and r["dropped"] == [{"user": "0", "session": 5, "memories": ["m5"]}]
    assert ("0", 3) not in r["kept_ids"] and ("0", 5) not in r["kept_ids"]


def test_gate_needs_more_than_95_percent_overall():
    assert fix_pass.kept_sessions(users_with(), {})["gate"]
    assert not fix_pass.kept_sessions(users_with(), {("0", "m1"): [("x", "y")]})["gate"]  # 19/20 is exactly 95%
    assert fix_pass.kept_sessions(users_with(40), {("0", "m1"): [("x", "y")]})["gate"]  # 39/40 = 97.5%


# --- wiring ---

def test_load_users_reads_two_digit_ids(tmp_path):
    for n in (0, 2, 10, 29):
        (tmp_path / f"user{n}.json").write_text(json.dumps({"user_id": n}))
    (tmp_path / "user10-sessions.json").write_text("{}")
    assert [u["user_id"] for u in to_graphiti.load_users(tmp_path)] == [0, 2, 10, 29]


class FakeModel:
    """Answers a retry like a model would: drops values from names, marks hidden misses as traits."""
    def __init__(self):
        self.calls = 0

    async def json(self, prompt, temperature, max_tokens):
        self.calls += 1
        fix = prompt.split("FIX:")[1].split("OTHER PIECES:")[0]
        items = []
        for block in fix.strip().split("\n")[0:]:
            if block[:1] == "m" and ": " in block:
                mid = block.split(":")[0]
                items.append({"id": mid, "entities": [NAME], "edges": [], "trait": True})
        return {"items": items}


TEST3 = Path(__file__).parent / "out" / "test3-gptoss"


@pytest.mark.skipif(not (TEST3 / "graphitify.json").exists(), reason="needs the cached test3 run")
def test_fix_pass_end_to_end_on_test3_with_a_fake_model():
    users = to_graphiti.load_users(TEST3)
    raw = json.loads((TEST3 / "graphitify.json").read_text())  # GRAPHITIFY v3 output, old `edge` format
    fake, retried = FakeModel(), {}
    pieces, log, report = asyncio.run(to_graphiti.fix(users, raw, retried, lambda: fake))
    assert fake.calls == len(retried) <= len(users)  # at most one retry per person
    assert all(e["before"] for e in log.values() if "model" in e)  # only flagged memories went to the model
    assert report["total"] == sum(1 for u in users for s in u["sessions"] if not s.get("excluded"))
    calls = fake.calls  # a rerun uses the cached retries: no new calls
    asyncio.run(to_graphiti.fix(users, raw, retried, lambda: fake))
    assert fake.calls == calls
    rows = [r for u in users for r in to_graphiti.examples(u, pieces[str(u["user_id"])], report["kept_ids"])]
    assert len(rows) == 2 * report["kept"]


class FailingModel:
    calls = 0

    async def json(self, prompt, temperature, max_tokens):
        self.calls += 1
        raise RuntimeError("answer hit max_tokens=12000 (truncated)")


def test_a_failed_retry_keeps_memories_flagged_instead_of_crashing():
    users = [{"user_id": 0, "persona": {"name": NAME}, "sessions": [
        {"index": 1, "memory_points": [mem("m1", "Rohan Mahesh Patel still dislikes crowded places.", "crowded places")]},
        {"index": 2, "memory_points": [mem("m2")]}]}]
    raw = {"0": {"m1": {"id": "m1", "entities": [NAME], "edges": []},
                 "m2": {"id": "m2", "entities": [NAME, "cricket"], "edges": [edge()]}}}
    fake, retried = FailingModel(), {}
    pieces, log, report = asyncio.run(to_graphiti.fix(users, raw, retried, lambda: fake))
    assert fake.calls == 1 and retried == {}  # not cached, so a rerun tries again
    assert report["kept_ids"] == {("0", 2)} and report["dropped"][0]["memories"] == ["m1"]
