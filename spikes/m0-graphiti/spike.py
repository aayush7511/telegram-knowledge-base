"""M0 spike: compare Graphiti LLMs on identical episodes.

Throwaway, not production code — see docs/design/v2.md (M0). Three steps:

  prepare  Build episodes.json from real blog URLs (the orchestrator's own
           render → extract code, summarized by gpt-4.1-mini with the
           orchestrator's prompt) plus plain-text notes, so every model run
           ingests exactly the same input.
  run      Ingest an episodes file into a fresh FalkorDB graph with one model in
           both Graphiti slots, then re-add the first episode under the same
           uuid (stand-in for job_id keying). Writes results/<model>[+label].json
           + .md; --label keeps variants (e.g. another episode format) apart.
  compare  Side-by-side totals for every results/*.json.

The key is read from services/orchestrator/.dev.vars (OPENAI_API_KEY).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent.parent / "services" / "orchestrator"
RESULTS = HERE / "results"
EPISODES = HERE / "episodes.json"
EMBEDDING_MODEL = "text-embedding-3-small"


def load_dev_vars() -> None:
    path = ORCH / ".dev.vars"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def read_lines(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]


def read_notes(path: Path) -> list[str]:
    """Notes are separated by blank lines, so a note can span several lines."""
    return [b.strip() for b in path.read_text().split("\n\n") if b.strip()]


# Spike summaries come from gpt-4.1-mini (Gemini was shedding load with 503s),
# using the orchestrator's own prompt and input cap so they stay production-like.
SUMMARY_MODEL = "gpt-4.1-mini-2025-04-14"


async def prepare(urls_file: Path, notes_file: Path | None) -> None:
    sys.path.insert(0, str(ORCH))
    import fetcher
    from extract import extract_content
    from openai import AsyncOpenAI
    from summarize import _MAX_INPUT_CHARS, _PROMPT

    client = AsyncOpenAI()  # retries 429/5xx itself
    episodes = []
    for url in read_lines(urls_file):
        try:
            ro = extract_content(await fetcher.render(url), url)
            resp = await client.responses.create(
                model=SUMMARY_MODEL,
                input=_PROMPT.format(title=ro.title or "(untitled)", text=ro.text[:_MAX_INPUT_CHARS]),
            )
            ro.summary = resp.output_text.strip()
        except Exception as exc:
            print(f"skipped {url}: {exc!r}"[:300])
            continue
        # Title + summary only: Graphiti's text-extraction prompt never sees
        # source_description, so URL/site/author stay provenance, not entities (M0).
        meta = [f"blog: {url}"] + [f"{k}: {v}" for k, v in (("site", ro.sitename), ("author", ro.author)) if v]
        episodes.append({
            "kind": "blog",
            "name": ro.title or url,
            "body": f"{ro.title}\n\n{ro.summary}" if ro.title else ro.summary,
            "source_description": " | ".join(meta),
        })
        print(f"summarized {url}")
    for note in read_notes(notes_file) if notes_file else []:
        episodes.append({"kind": "note", "name": note[:60], "body": note, "source_description": "telegram text note"})
    EPISODES.write_text(json.dumps(episodes, indent=2))
    print(f"wrote {len(episodes)} episodes to {EPISODES.name}")


class LogCounter(logging.Handler):
    """Counts Graphiti's retry warnings (schema/validation or rate-limit) and errors."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.reset()

    def reset(self) -> None:
        self.retries = 0
        self.errors = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "Retrying" in record.getMessage():
            self.retries += 1
        elif record.levelno >= logging.ERROR:
            self.errors += 1


async def count(driver, cypher: str, **params) -> int:
    records = (await driver.execute_query(cypher, **params))[0]
    return records[0]["n"]


async def run(
    model: str, host: str, port: int, episodes_file: Path, label: str, temperature: float | None, readd: bool
) -> None:
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import DEFAULT_TEMPERATURE, LLMConfig
    from graphiti_core.llm_client.openai_client import OpenAIClient
    from graphiti_core.nodes import EpisodeType, EpisodicNode

    episodes = json.loads(episodes_file.read_text())
    run_name = f"{model}+{label}" if label else model
    temperature = DEFAULT_TEMPERATURE if temperature is None else temperature
    counter = LogCounter()
    logging.getLogger("graphiti_core").addHandler(counter)

    # On FalkorDB, Graphiti's group_id *is* the graph name: add_episode clones the
    # driver onto graph <group_id> whenever it differs from the driver's database.
    graph = "m0_" + "".join(c if c.isalnum() else "_" for c in run_name)
    driver = FalkorDriver(host=host, port=port, database=graph)
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=OpenAIClient(config=LLMConfig(
            api_key=os.environ["OPENAI_API_KEY"], model=model, small_model=model, temperature=temperature,
        )),
        embedder=OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=os.environ["OPENAI_API_KEY"], embedding_model=EMBEDDING_MODEL)),
    )
    # FalkorDriver starts its own index build as a background task when created
    # inside a running loop; a second build_indices_and_constraints() races it.
    if getattr(driver, "_init_task", None):
        await driver._init_task
    await driver.execute_query("MATCH (n) DETACH DELETE n")

    tracker = graphiti.token_tracker
    start = datetime.now(timezone.utc) - timedelta(days=len(episodes))

    async def ingest(i: int, ep: dict) -> dict:
        tracker.reset()
        counter.reset()
        row = {"name": ep["name"], "kind": ep["kind"], "ok": False, "entities": [], "facts": []}
        key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"m0/{i}"))  # stands in for job_id
        reference_time = start + timedelta(days=i)
        t0 = time.monotonic()
        try:
            # add_episode(uuid=...) reprocesses an *existing* episode (NodeNotFoundError
            # otherwise), so job_id keying = upsert the Episodic node first (save is a MERGE).
            await EpisodicNode(
                uuid=key,
                name=ep["name"],
                group_id=graph,
                labels=[],
                source=EpisodeType.text,
                content=ep["body"],
                source_description=ep["source_description"],
                created_at=datetime.now(timezone.utc),
                valid_at=reference_time,
            ).save(driver)
            res = await graphiti.add_episode(
                name=ep["name"],
                episode_body=ep["body"],
                source_description=ep["source_description"],
                reference_time=reference_time,
                source=EpisodeType.text,
                group_id=graph,
                uuid=key,
            )
            row.update(ok=True, entities=[f"{n.name} — {n.summary}" for n in res.nodes], facts=[e.fact for e in res.edges])
        except Exception as exc:
            row["error"] = repr(exc)[:500]
        usage = tracker.get_total_usage()
        row.update(
            seconds=round(time.monotonic() - t0, 1),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            llm_calls=sum(p.call_count for p in tracker.get_usage().values()),
            retries=counter.retries,
            errors=counter.errors,
        )
        print(f"[{run_name}] {i + 1}/{len(episodes)} ok={row['ok']} {row['seconds']}s "
              f"in={row['input_tokens']} out={row['output_tokens']} retries={row['retries']}")
        return row

    rows = [await ingest(i, ep) for i, ep in enumerate(episodes)]

    # Keying check: re-add episode 0 under the same uuid. Ideal: still one
    # Episodic node for that uuid and ~no new entities/facts (dedup holds).
    keying = None
    if readd:
        key0 = str(uuid.uuid5(uuid.NAMESPACE_URL, "m0/0"))
        entities_before = await count(driver, "MATCH (n:Entity) RETURN count(n) AS n")
        facts_before = await count(driver, "MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS n")
        readd_row = await ingest(0, episodes[0])
        keying = {
            "readd_ok": readd_row["ok"],
            "episodic_nodes_for_uuid": await count(driver, "MATCH (e:Episodic {uuid: $uuid}) RETURN count(e) AS n", uuid=key0),
            "new_entities": await count(driver, "MATCH (n:Entity) RETURN count(n) AS n") - entities_before,
            "new_facts": await count(driver, "MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS n") - facts_before,
        }
    await graphiti.close()

    result = {
        "model": run_name,
        "graphiti_core": version("graphiti-core"),
        "embedding_model": EMBEDDING_MODEL,
        "temperature": temperature,
        "episodes_file": episodes_file.name,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "episodes": rows,
        "keying": keying,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{run_name}.json").write_text(json.dumps(result, indent=2))
    (RESULTS / f"{run_name}.md").write_text(render_md(result))
    print(f"wrote results/{run_name}.json and .md — keying: {keying}")


def totals(result: dict) -> dict:
    rows = result["episodes"]
    n = len(rows)
    keying = result["keying"]
    return {
        "ok": f"{sum(r['ok'] for r in rows)}/{n}",
        "s/ep": round(sum(r["seconds"] for r in rows) / n, 1),
        "in tok/ep": round(sum(r["input_tokens"] for r in rows) / n),
        "out tok/ep": round(sum(r["output_tokens"] for r in rows) / n),
        "calls/ep": round(sum(r["llm_calls"] for r in rows) / n, 1),
        "retries": sum(r["retries"] for r in rows),
        "errors": sum(r["errors"] for r in rows),
        "entities": sum(len(r["entities"]) for r in rows),
        "facts": sum(len(r["facts"]) for r in rows),
        "re-add new entities/facts": f"{keying['new_entities']}/{keying['new_facts']}" if keying else "skipped",
    }


def table(rows: list[dict]) -> str:
    cols = list(rows[0])
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(lines)


def render_md(result: dict) -> str:
    out = [f"# {result['model']}", "",
           f"graphiti-core {result['graphiti_core']}, embeddings {result['embedding_model']}, "
           f"temperature {result.get('temperature', 'default')}, "
           f"episodes {result.get('episodes_file', EPISODES.name)}, run {result['run_at']}", "",
           table([{"model": result["model"], **totals(result)}]), "",
           f"Keying check: {result['keying']}", ""]
    for i, r in enumerate(result["episodes"], 1):
        out += [f"## {i}. [{r['kind']}] {r['name']}", "",
                f"ok={r['ok']} · {r['seconds']}s · in={r['input_tokens']} out={r['output_tokens']} · "
                f"calls={r['llm_calls']} retries={r['retries']} errors={r['errors']}", ""]
        if r.get("error"):
            out += [f"**Error:** `{r['error']}`", ""]
        out += ["**Entities**", *[f"- {e}" for e in r["entities"]], "", "**Facts**", *[f"- {f}" for f in r["facts"]], ""]
    return "\n".join(out)


def compare() -> None:
    results = [json.loads(p.read_text()) for p in sorted(RESULTS.glob("*.json"))]
    if not results:
        sys.exit("no results yet — run `spike.py run --model ...` first")
    print(table([{"model": r["model"], **totals(r)} for r in results]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prepare")
    pp.add_argument("--urls", type=Path, default=HERE / "urls.txt")
    pp.add_argument("--notes", type=Path, default=None)
    pr = sub.add_parser("run")
    pr.add_argument("--model", required=True, help="pinned snapshot, e.g. gpt-4.1-mini-2025-04-14")
    pr.add_argument("--episodes", type=Path, default=EPISODES)
    pr.add_argument("--label", default="", help="variant tag appended to the results and graph names")
    pr.add_argument("--temperature", type=float, default=None, help="default: Graphiti's own (1)")
    pr.add_argument("--no-readd", action="store_true", help="skip the keying re-add check (saves tokens)")
    pr.add_argument("--host", default="localhost")
    pr.add_argument("--port", type=int, default=6379)
    sub.add_parser("compare")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dev_vars()
    if args.cmd == "prepare":
        asyncio.run(prepare(args.urls, args.notes))
    elif args.cmd == "run":
        asyncio.run(run(args.model, args.host, args.port, args.episodes, args.label, args.temperature, not args.no_readd))
    else:
        compare()


if __name__ == "__main__":
    main()
