"""Experiment: full cleaned article text vs. title+summary as the Graphiti
episode body, for the SAME real article, using the SAME model/settings v2
runs in production (gpt-4.1-mini-2025-04-14, temperature 0,
text-embedding-3-small).

Writes into two throwaway FalkorDB graphs on the production VM —
`experiment_summary` and `experiment_fulltext` — NEVER the real `second-brain`
graph, so this can't corrupt production data. Delete them when done (see
README.md).

Usage (from this directory, with an SSH tunnel to FalkorDB's 6379 already
open — see README.md):

    python3 spike.py --url https://example.com/post
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent.parent / "services" / "orchestrator"
RESULTS = HERE / "results"


def load_dev_vars() -> None:
    path = ORCH / ".dev.vars"
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


async def build_variants(url: str) -> tuple[dict, dict]:
    """Render + extract + summarize the real article once; return the two episode
    variants (same source_description, different body) so this is a fair A/B."""
    sys.path.insert(0, str(ORCH))
    import fetcher
    from extract import extract_content
    from openai import AsyncOpenAI
    from summarize import _MAX_INPUT_CHARS, _PROMPT

    ro = extract_content(await fetcher.render(url), url)
    client = AsyncOpenAI()
    resp = await client.responses.create(
        model="gpt-4.1-mini-2025-04-14",
        input=_PROMPT.format(title=ro.title or "(untitled)", text=ro.text[:_MAX_INPUT_CHARS]),
    )
    summary = resp.output_text.strip()

    meta = [f"blog: {url}"] + [f"{k}: {v}" for k, v in (("site", ro.sitename), ("author", ro.author)) if v]
    source_description = " | ".join(meta)
    title = ro.title or url

    summary_variant = {
        "label": "summary",
        "graph": "experiment_summary",
        "name": title,
        "body": f"{title}\n\n{summary}",
        "source_description": source_description,
    }
    fulltext_variant = {
        "label": "fulltext",
        "graph": "experiment_fulltext",
        "name": title,
        "body": f"{title}\n\n{ro.text}",
        "source_description": source_description,
    }
    print(f"article: {title!r} — {len(ro.text)} chars full text, {len(summary)} chars summary")
    return summary_variant, fulltext_variant


async def ingest_variant(variant: dict, *, host: str, port: int) -> dict:
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_client import OpenAIClient
    from graphiti_core.nodes import EpisodeType, EpisodicNode

    graph = variant["graph"]
    driver = FalkorDriver(host=host, port=port, password=os.environ["FALKORDB_PASSWORD"], database=graph)
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=OpenAIClient(config=LLMConfig(
            api_key=os.environ["OPENAI_API_KEY"], model="gpt-4.1-mini-2025-04-14",
            small_model="gpt-4.1-mini-2025-04-14", temperature=0,
        )),
        embedder=OpenAIEmbedder(config=OpenAIEmbedderConfig(
            api_key=os.environ["OPENAI_API_KEY"], embedding_model="text-embedding-3-small",
        )),
    )
    init_task = getattr(driver, "_init_task", None)
    if init_task is not None:
        await init_task
    await driver.execute_query("MATCH (n) DETACH DELETE n")  # fresh graph each run

    key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"experiment/{variant['label']}"))
    now = datetime.now(timezone.utc)
    tracker = graphiti.token_tracker
    t0 = time.monotonic()
    await EpisodicNode(
        uuid=key, name=variant["name"], group_id=graph, labels=[], source=EpisodeType.text,
        content=variant["body"], source_description=variant["source_description"],
        created_at=now, valid_at=now,
    ).save(driver)
    result = await graphiti.add_episode(
        name=variant["name"], episode_body=variant["body"],
        source_description=variant["source_description"], reference_time=now,
        source=EpisodeType.text, group_id=graph, uuid=key,
    )
    elapsed = time.monotonic() - t0
    usage = tracker.get_total_usage()
    await graphiti.close()

    return {
        "label": variant["label"],
        "graph": graph,
        "body_chars": len(variant["body"]),
        "seconds": round(elapsed, 1),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "llm_calls": sum(p.call_count for p in tracker.get_usage().values()),
        "entities": [f"{n.name} — {n.summary}" for n in result.nodes],
        "facts": [f"{e.name}: {e.fact}" for e in result.edges],
    }


def render_report(url: str, results: list[dict]) -> str:
    out = [f"# Full article vs. summary episode — {url}", ""]
    cols = ["label", "body_chars", "seconds", "input_tokens", "output_tokens", "llm_calls",
            "entities", "facts"]
    out.append("| " + " | ".join(cols) + " |")
    out.append("|" + "---|" * len(cols))
    for r in results:
        out.append("| " + " | ".join(str(len(r[c]) if c in ("entities", "facts") else r[c]) for c in cols) + " |")
    out.append("")
    for r in results:
        out += [f"## {r['label']} (graph: `{r['graph']}`)", "", "**Entities**",
                *[f"- {e}" for e in r["entities"]], "", "**Facts**",
                *[f"- {f}" for f in r["facts"]], ""]
    return "\n".join(out)


async def main(url: str, host: str, port: int) -> None:
    load_dev_vars()
    summary_variant, fulltext_variant = await build_variants(url)
    results = []
    for variant in (summary_variant, fulltext_variant):
        print(f"ingesting variant={variant['label']} into graph={variant['graph']} ...")
        r = await ingest_variant(variant, host=host, port=port)
        print(f"  -> {r['seconds']}s, in={r['input_tokens']} out={r['output_tokens']}, "
              f"entities={len(r['entities'])}, facts={len(r['facts'])}")
        results.append(r)

    RESULTS.mkdir(exist_ok=True)
    report = render_report(url, results)
    (RESULTS / "report.md").write_text(report)
    (RESULTS / "report.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {RESULTS / 'report.md'}")
    print("\n" + report)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", required=True)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=6379)
    args = p.parse_args()
    asyncio.run(main(args.url, args.host, args.port))
