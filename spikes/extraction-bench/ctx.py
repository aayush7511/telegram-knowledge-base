"""Context spike: which previous episodes should Graphiti see when saving a personal item?

Timeline: HaluMem-Medium user 0, sessions 0-29, with the 5 Re-DocRED articles interleaved and
5 hand-written update pairs (early note → much later update). Strategies, for personal items:
  A  Graphiti default: last 10 episodes of any kind
  B  no previous episodes
  C  last 10 personal episodes
  D  10 personal episodes most similar to the new one (embedding cosine)
Articles get Graphiti's default under A and no context under B/C/D.

    MODEL=teachernothink ../../services/orchestrator/.venv/bin/python ctx.py A B C D
"""
import asyncio
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.nodes import EpisodeType

from bench import EMBEDDING_MODEL, build_llm, judge, load_env

HERE = Path(__file__).parent
N_SESSIONS = 30
K = int(os.environ.get("K", "10"))  # context episodes for C and D

PROBES = [  # (early note, later update, what the update should change)
    ("I signed a 12-month lease on my apartment in Capitol Hill, Seattle.",
     "I moved to Austin last week for a new job.", "lives in Seattle → Austin"),
    ("I'm working on the OS assignment, it's due Friday.",
     "I submitted the operating systems homework.", "assignment in progress → submitted"),
    ("I'm training for the half marathon in March.",
     "I gave up running after hurting my knee.", "marathon training → dropped"),
    ("I use VS Code for everything.", "I switched my editor to Zed.", "VS Code → Zed"),
    ("I'm planning a trip to Japan in December.", "I booked flights to Tokyo for Dec 12.",
     "Japan trip planned → booked"),
]


def timeline() -> list[dict]:
    user = json.loads((HERE / "data" / "halumem_medium.jsonl").open().readline())
    articles = [i for i in json.loads((HERE / "data" / "items.json").read_text()) if i["dataset"] == "redocred"]
    out: list[dict] = []
    for n, s in enumerate(user["sessions"][:N_SESSIONS]):
        t = datetime.strptime(s["start_time"], "%b %d, %Y, %H:%M:%S").replace(tzinfo=timezone.utc)
        out.append({"kind": "personal", "id": f"session-{n:02d}", "time": t,
                    "body": "\n".join(f"{x['role']}: {x['content']}" for x in s["dialogue"]),
                    "gold": [m["memory_content"] for m in s["memory_points"]],
                    "gold_update": [m["memory_content"] for m in s["memory_points"] if str(m.get("is_update")) == "True"]})
        if n % 6 == 5 and articles:
            a = articles.pop(0)
            out.append({"kind": "article", "id": a["id"], "time": t + timedelta(minutes=30), "body": a["body"],
                        "gold": a["gold"], "gold_update": []})
        if n < len(PROBES) * 2 and n % 2 == 0:  # early notes in sessions 0..8
            p = n // 2
            out.append({"kind": "personal", "id": f"probe-{p}-early", "time": t + timedelta(minutes=45),
                        "body": f"user: {PROBES[p][0]}", "gold": [], "gold_update": []})
        if n >= N_SESSIONS - len(PROBES) * 2 and n % 2 == 1:  # updates near the end
            p = (n - (N_SESSIONS - len(PROBES) * 2)) // 2
            out.append({"kind": "personal", "id": f"probe-{p}-late", "time": t + timedelta(minutes=45),
                        "body": f"user: {PROBES[p][1]}", "gold": [], "gold_update": []})
    return out


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


async def run(strategy: str, model: str, items: list[dict], emb: AsyncOpenAI) -> dict:
    llm, usage = build_llm(model)
    graph = f"ctx{strategy}k{K}{model}"
    driver = FalkorDriver(host="127.0.0.1", port=6379, database=graph)
    g = Graphiti(graph_driver=driver, llm_client=llm, embedder=OpenAIEmbedder(
        config=OpenAIEmbedderConfig(api_key=os.environ["OPENAI_API_KEY"], embedding_model=EMBEDDING_MODEL)))
    if getattr(driver, "_init_task", None):
        await driver._init_task
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await g.build_indices_and_constraints()

    personal: list[tuple[str, list[float]]] = []  # (episode uuid, embedding) in save order
    rows = []
    for it in items:
        if strategy == "A":
            prev = None
        elif it["kind"] == "article" or strategy == "B":
            prev = []
        elif strategy == "C":
            prev = [u for u, _ in personal[-K:]]
        else:  # D
            v = (await emb.embeddings.create(model=EMBEDDING_MODEL, input=it["body"][:8000])).data[0].embedding
            prev = [u for u, e in sorted(personal, key=lambda p: -cos(v, p[1]))[:K]]
        before, t0, err, facts, ents = usage(), time.time(), None, [], []
        try:
            r = await g.add_episode(name=it["id"], episode_body=it["body"], source_description=it["kind"],
                                    reference_time=it["time"], group_id=graph, previous_episode_uuids=prev,
                                    source=EpisodeType.message if it["kind"] == "personal" else EpisodeType.text)
            facts, ents = [e.fact for e in r.edges], [n.name for n in r.nodes]
            if it["kind"] == "personal":
                vec = (await emb.embeddings.create(model=EMBEDDING_MODEL, input=it["body"][:8000])).data[0].embedding \
                    if strategy == "D" else []
                personal.append((r.episode.uuid, vec))
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
        after = usage()
        rows.append({"id": it["id"], "kind": it["kind"], "error": err, "facts": facts, "entities": ents,
                     "in": after["in"] - before["in"], "out": after["out"] - before["out"],
                     "secs": round(time.time() - t0, 1)})
        print(f"[{strategy}] {it['id']}: {len(facts)} facts{' ERROR ' + err if err else ''}", flush=True)

    # Probes: did the later note invalidate (or confirm) the earlier fact? Read the graph directly.
    res = await driver.execute_query(
        "MATCH ()-[r:RELATES_TO]->() RETURN r.fact AS fact, r.invalid_at AS invalid_at, r.expired_at AS expired_at")
    edges = res[0] if isinstance(res, tuple) else res
    await driver.close()
    return {"strategy": strategy, "rows": rows, "edges": [dict(e) for e in edges],
            "retries": usage().get("retries", 0)}


PROBE_JUDGE = """Below are facts stored in a memory graph, each marked CURRENT or OUTDATED.
For each numbered update, answer whether the graph reflects it: the new state is stored as CURRENT
and the old state is either OUTDATED or absent as a current fact.

UPDATES:
{updates}

FACTS:
{facts}

Reply with JSON: {{"reflected": [numbers of the updates the graph reflects]}}"""


async def score_probes(jc: AsyncOpenAI, edges: list[dict]) -> list[int]:
    facts = "\n".join(f"- [{'OUTDATED' if e.get('invalid_at') or e.get('expired_at') else 'CURRENT'}] {e['fact']}"
                      for e in edges)
    r = await jc.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14", temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "user", "content": PROBE_JUDGE.format(
            updates="\n".join(f"{i + 1}. {p[2]}" for i, p in enumerate(PROBES)), facts=facts)}])
    return sorted(set(json.loads(r.choices[0].message.content).get("reflected", [])))


async def main(strategies: list[str]) -> None:
    load_env()
    model = os.environ.get("MODEL", "teachernothink")
    items = timeline()
    emb = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    print(f"timeline: {len(items)} items ({sum(i['kind'] == 'article' for i in items)} articles), model {model}")
    runs = await asyncio.gather(*(run(s, model, items, emb) for s in strategies))

    gold = {i["id"]: i for i in items}
    out = []
    for run_ in runs:
        scored = [r for r in run_["rows"] if gold[r["id"]]["gold"]]
        cov = await asyncio.gather(*(judge(emb, gold[r["id"]]["gold"], r) for r in scored))
        upd = await asyncio.gather(*(judge(emb, gold[r["id"]]["gold_update"], r) if gold[r["id"]]["gold_update"]
                                     else asyncio.sleep(0, result=[]) for r in scored))
        probes = await score_probes(emb, run_["edges"])
        g_all = sum(len(gold[r["id"]]["gold"]) for r in scored)
        g_upd = sum(len(gold[r["id"]]["gold_update"]) for r in scored)
        per = {k: [r for r in run_["rows"] if r["kind"] == k] for k in ("personal", "article")}
        out.append({"strategy": f'{run_["strategy"]}{K if run_["strategy"] in "CD" else ""}', "recall": sum(map(len, cov)) / g_all,
                    "update_recall": sum(map(len, upd)) / max(g_upd, 1), "probes": probes,
                    "errors": sum(1 for r in run_["rows"] if r["error"]), "retries": run_["retries"],
                    "in_personal": sum(r["in"] for r in per["personal"]), "in_article": sum(r["in"] for r in per["article"]),
                    "out": sum(r["out"] for r in run_["rows"]), "mins": sum(r["secs"] for r in run_["rows"]) / 60,
                    "rows": run_["rows"]})

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (HERE / "results" / f"ctx-{model}-k{K}-{stamp}.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"\n{'strat':5} {'recall':>7} {'update_recall':>13} {'probes':>10} {'errs':>4} {'retries':>7} "
          f"{'in_personal':>11} {'in_article':>10} {'out':>7} {'mins':>5}")
    for o in out:
        print(f"{o['strategy']:5} {o['recall']:7.1%} {o['update_recall']:13.1%} {str(len(o['probes'])) + '/5 ' + str(o['probes']):>10} "
              f"{o['errors']:4} {o['retries']:7} {o['in_personal']:11} {o['in_article']:10} {o['out']:7} {o['mins']:5.1f}")
    print(f"saved results/ctx-{model}-k{K}-{stamp}.json")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["A", "B", "C", "D"]))
