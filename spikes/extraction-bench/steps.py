"""Per-step token breakdown: run the baseline over data/items.json and report Graphiti's
token tracker per prompt (extraction vs dedup/contradiction vs summaries ...).

    ../../services/orchestrator/.venv/bin/python steps.py
"""
import asyncio
import json
import os
from pathlib import Path

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.nodes import EpisodeType

from bench import EMBEDDING_MODEL, build_llm, load_env, parse_time

HERE = Path(__file__).parent
PRICE_IN, PRICE_OUT = 0.40, 1.60  # gpt-4.1-mini list, $/1M

# Which kind of work each Graphiti prompt does.
KIND = {
    "extract_nodes": "extract entities",
    "extract_edges.edge": "extract facts",
    "extract_nodes_and_edges": "extract entities",
    "dedupe_nodes": "DECISION: entity dedup",
    "dedupe_edges": "DECISION: fact dedup + contradiction",
    "extract_edges.extract_timestamps": "fact dates",
    "extract_edges.extract_attributes": "attributes",
    "extract_nodes.extract_attributes": "attributes",
    "extract_nodes.extract_summaries": "entity summaries",
    "extract_nodes.extract_entity_summaries": "entity summaries",
    "summarize_nodes": "entity summaries",
}


def kind(prompt: str) -> str:
    for prefix, k in sorted(KIND.items(), key=lambda kv: -len(kv[0])):
        if prompt.startswith(prefix):
            return k
    return prompt


async def main() -> None:
    load_env()
    items = json.loads((HERE / "data" / "items.json").read_text())
    llm, _ = build_llm("baseline")
    embedder = OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=os.environ["OPENAI_API_KEY"],
                                                          embedding_model=EMBEDDING_MODEL))
    by_ds = {}
    for dataset in ("redocred", "halumem"):
        graph = f"steps{dataset}"
        driver = FalkorDriver(host="127.0.0.1", port=6379, database=graph)
        g = Graphiti(graph_driver=driver, llm_client=llm, embedder=embedder)
        if getattr(driver, "_init_task", None):
            await driver._init_task
        await driver.execute_query("MATCH (n) DETACH DELETE n")
        await g.build_indices_and_constraints()
        llm.token_tracker.reset()
        for item in [i for i in items if i["dataset"] == dataset]:
            await g.add_episode(name=item["id"], episode_body=item["body"], source_description=dataset,
                                reference_time=parse_time(item), group_id=graph,
                                source=EpisodeType.message if dataset == "halumem" else EpisodeType.text)
            print(f"{dataset} {item['id']} done", flush=True)
        by_ds[dataset] = {p: (u.call_count, u.total_input_tokens, u.total_output_tokens)
                          for p, u in llm.token_tracker.get_usage().items()}
        await driver.close()

    (HERE / "results" / "steps.json").write_text(json.dumps(by_ds, indent=1))
    for dataset, usage in by_ds.items():
        agg: dict[str, list[float]] = {}
        for p, (calls, tin, tout) in usage.items():
            a = agg.setdefault(kind(p), [0, 0, 0, 0.0])
            a[0] += calls; a[1] += tin; a[2] += tout; a[3] += tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
        total = sum(a[3] for a in agg.values())
        print(f"\n== {dataset}: ${total:.4f} total")
        print(f"{'step':38} {'calls':>5} {'in_tok':>8} {'out_tok':>7} {'cost':>8} {'share':>6}")
        for k, (calls, tin, tout, cost) in sorted(agg.items(), key=lambda kv: -kv[1][3]):
            print(f"{k:38} {calls:5} {tin:8} {tout:7} ${cost:7.4f} {cost / total:6.1%}")
        print("  raw prompts:", ", ".join(f"{p}={c}" for p, (c, _, _) in sorted(usage.items())))


if __name__ == "__main__":
    asyncio.run(main())
