"""Score a ~10% session sample of our Graphiti runs with HaluMem's official extraction judge (unchanged code).

    OPENAI_MODEL=gpt-4o python run_sample.py out-gpt4o.json
Extracted memories = Graphiti facts for that session. Update and QA tasks are not run (no inputs given).
"""
import json
import os
import random
import sys
from pathlib import Path

BENCH = Path("/Users/aayus/Desktop/knowledge-base/telegram-knowledge-base/spikes/extraction-bench")
RUNS = {0: "results/run-20261018T014452Z.json", 1: "results/run-20261018T015721Z.json",
        2: "results/run-20261018T014709Z.json"}


STYLED = json.loads(Path("styled.json").read_text()) if Path("styled.json").exists() else {}


def build_users():
    lines = (BENCH / "data/halumem_medium.jsonl").read_text().splitlines()
    users = []
    for u, run in RUNS.items():
        user = json.loads(lines[u])
        facts = {r["id"]: r["facts"] for r in json.loads((BENCH / run).read_text())}
        n = len(user["sessions"])
        picked = sorted(random.Random(7 + u).sample(range(n), round(n * 0.1)))
        sessions = []
        for i in picked:
            s = user["sessions"][i]
            mode = os.environ.get("MODE", "graphiti")  # graphiti | gold | goldstyled
            if mode == "gold":  # simulate perfect extraction: the gold memories themselves (no distractors)
                extracted = [m["memory_content"] for m in s["memory_points"] if m["memory_source"] != "interference"]
            elif mode == "goldstyled":  # gold rewritten in Graphiti's fact style (see restyle.py)
                extracted = STYLED[f"{u}-{i}"]
            else:
                extracted = facts[f"session-{i:02d}"]
            sessions.append({"memory_points": s["memory_points"], "dialogue": s["dialogue"],
                             "extracted_memories": extracted})
        users.append({"uuid": user["uuid"], "user_name": f"user{u}", "sessions": sessions, "picked": picked})
    return users


def metrics(recs):
    integ = [m for r in recs for m in r["memory_integrity_records"]]
    acc = [m for r in recs for m in r["memory_accuracy_records"]]
    real = [m for m in integ if m["memory_source"] != "interference"]
    interf = [m for m in integ if m["memory_source"] == "interference"]
    target = [m for m in acc if m["is_included_in_golden_memories"] in ("true", "True")]
    return {
        "recall": sum(m["memory_integrity_score"] == 2 for m in real) / len(real),
        "weighted_recall": sum(0.5 * (m["memory_integrity_score"] or 0) * m["importance"] for m in real)
                           / sum(m["importance"] for m in real),
        "target_precision": sum(0.5 * (m["memory_accuracy_score"] or 0) for m in target) / max(len(target), 1),
        "weighted_accuracy": sum(0.5 * (m["memory_accuracy_score"] or 0) for m in acc) / max(len(acc), 1),
        "false_memory_resistance": sum(m["memory_integrity_score"] == 0 for m in interf) / max(len(interf), 1),
        "n_gold": len(real), "n_interference": len(interf), "n_extracted": len(acc), "n_target": len(target),
        "invalid": sum(m["memory_integrity_score"] is None for m in integ) + sum(m["memory_accuracy_score"] is None for m in acc),
    }


if __name__ == "__main__":
    from evaluation import process_user  # HaluMem's scorer, unchanged
    users = build_users()
    if sys.argv[1] == "--dry":
        for u in users:
            print(u["user_name"], "sessions", u["picked"], "gold", sum(len(s["memory_points"]) for s in u["sessions"]),
                  "facts", sum(len(s["extracted_memories"]) for s in u["sessions"]))
        sys.exit()
    recs = [process_user(i, u) for i, u in enumerate(users)]
    out = {"metrics": metrics(recs), "records": recs}
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["metrics"], indent=1))
