"""Extraction spike: run Graphiti over data/items.json with each model into a local FalkorDB,
then score recall of the gold facts with a judge model.

    ../../services/orchestrator/.venv/bin/python bench.py [baseline|teacher ...]

Needs .env (OPENAI_API_KEY, TEACHER_API_KEY, TEACHER_BASE_URL, TEACHER_MODEL) and the
`falkordb-bench` container on 127.0.0.1:6379. Each model × dataset gets its own graph,
dropped at the start of a run so reruns start clean.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType

HERE = Path(__file__).parent
BASELINE_MODEL = "gpt-4.1-mini-2025-04-14"  # same pin as production (graph.py)
JUDGE_MODEL = "gpt-4.1-mini-2025-04-14"
EMBEDDING_MODEL = "text-embedding-3-small"


def load_env() -> None:
    for line in (HERE / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _strict(schema):
    """Copy of a JSON schema in OpenAI strict form: every object closed, every property required."""
    if isinstance(schema, dict):
        out = {k: _strict(v) for k, v in schema.items() if k not in ("default", "title")}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out
    if isinstance(schema, list):
        return [_strict(v) for v in schema]
    return schema


def _bad_answer(content: str | None) -> str | None:
    """Why an answer can't be used: unparseable, or the schema echoed back instead of an instance."""
    try:
        data = json.loads((content or "").strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError:
        return "not valid JSON"
    if isinstance(data, dict) and "properties" in data and data.get("type") == "object":
        return "returned the schema instead of an instance"
    return None


class _CountingCompletions:
    """Wraps chat.completions.create to count calls and tokens (the generic client doesn't),
    enforce strict schemas, and retry answers that echo the schema or don't parse."""

    MAX_TOKENS = 8192  # a real Graphiti answer is far smaller; stops runaway output
    RETRIES = 2

    def __init__(self, inner, usage, extra_body=None, drop=()):
        self._inner, self._usage, self._extra, self._drop = inner, usage, extra_body or {}, drop

    async def create(self, **kw):
        for k in self._drop:  # params some models reject (frontier reasoning models: temperature)
            kw.pop(k, None)
        if self._extra:
            kw["extra_body"] = {**self._extra, **(kw.get("extra_body") or {})}
        rf = kw.get("response_format") or {}
        if rf.get("type") == "json_schema":
            js = rf["json_schema"]
            kw["response_format"] = {"type": "json_schema",
                                     "json_schema": {**js, "strict": True, "schema": _strict(js["schema"])}}
        kw["max_tokens"] = min(kw.get("max_tokens") or self.MAX_TOKENS, self.MAX_TOKENS)
        messages = list(kw["messages"])
        for attempt in range(self.RETRIES + 1):
            r = await self._inner.create(**{**kw, "messages": messages})
            self._usage["calls"] += 1
            if r.usage:
                self._usage["in"] += r.usage.prompt_tokens or 0
                self._usage["out"] += r.usage.completion_tokens or 0
            why = _bad_answer(r.choices[0].message.content) if rf else None
            if not why:
                return r
            self._usage["retries"] = self._usage.get("retries", 0) + 1
            messages = list(kw["messages"]) + [
                {"role": "assistant", "content": (r.choices[0].message.content or "")[:2000]},
                {"role": "user", "content": f"That answer {why}. Reply with only a JSON object that "
                                            "fills in the requested fields (an instance), not the schema."},
            ]
        return r


class _CountingClient:
    def __init__(self, inner: AsyncOpenAI, usage: dict, extra_body=None, drop=()):
        self.chat = type("Chat", (), {})()
        self.chat.completions = _CountingCompletions(inner.chat.completions, usage, extra_body, drop)


def build_llm(name: str):
    """Returns (llm_client, usage_reader). usage_reader() → {'calls','in','out'} so far."""
    if name.startswith("baseline"):  # baseline, baselinenoctx
        llm = OpenAIClient(config=LLMConfig(api_key=os.environ["OPENAI_API_KEY"], model=BASELINE_MODEL,
                                            small_model=BASELINE_MODEL, temperature=0))

        def usage():
            u = llm.token_tracker.get_usage().values()
            return {"calls": sum(x.call_count for x in u), "in": sum(x.total_input_tokens for x in u),
                    "out": sum(x.total_output_tokens for x in u)}
        return llm, usage

    model = os.environ.get("TEACHER_MODEL_" + name.upper(), os.environ["TEACHER_MODEL"])  # per-variant override
    base_url = os.environ.get("TEACHER_BASE_URL_" + name.upper(), os.environ["TEACHER_BASE_URL"])  # per-variant override
    key = os.environ.get(os.environ.get("TEACHER_KEY_ENV_" + name.upper(), os.environ.get("TEACHER_KEY_ENV", "TEACHER_API_KEY")),
                         "local")  # e.g. OPENROUTER_API_KEY; the local Claude adapter needs none
    counts = {"calls": 0, "in": 0, "out": 0}
    inner = AsyncOpenAI(api_key=key, base_url=base_url,
                        timeout=180, max_retries=2)  # free endpoints can hang; fail instead of stalling the run
    llm = OpenAIGenericClient(
        config=LLMConfig(api_key=key, base_url=base_url,
                         model=model, small_model=model, temperature=0),
        # OpenRouter: only route to hosts that honour the requested response format.
        client=_CountingClient(inner, counts, {
            **({"provider": {"require_parameters": True}} if "openrouter.ai" in base_url else {}),
            **({"reasoning": {"enabled": False}} if "nothink" in name else {}),  # e.g. `bench.py teachernothink`
            **({"reasoning": {"effort": "low"}} if "lowthink" in name else {}),  # models that can't disable it (gpt-oss)
        } or None, drop=("temperature",) if "frontier" in name else ()),
        # json_schema = enforced format; json_object = schema only described in the prompt.
        structured_output_mode=os.environ.get("TEACHER_STRUCTURED", "json_schema"),
    )
    return llm, lambda: dict(counts)


def parse_time(item) -> datetime:
    if item.get("time"):
        return datetime.strptime(item["time"], "%b %d, %Y, %H:%M:%S").replace(tzinfo=timezone.utc)
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


async def run_model(name: str, items: list[dict], reset: bool = True) -> list[dict]:
    llm, usage = build_llm(name)
    embedder = OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=os.environ["OPENAI_API_KEY"],
                                                          embedding_model=EMBEDDING_MODEL))
    out = []
    for dataset in ("redocred", "halumem"):
        if not any(i["dataset"] == dataset for i in items):
            continue
        graph = f"bench{name}{dataset}"  # letters only: FalkorDB fulltext (BM25) breaks on "_" (docs/design/v3.md)
        driver = FalkorDriver(host="127.0.0.1", port=6379, database=graph)
        g = Graphiti(graph_driver=driver, llm_client=llm, embedder=embedder)
        if getattr(driver, "_init_task", None):
            await driver._init_task
        if reset:  # a resumed run keeps the graph so later items dedupe against earlier ones
            await driver.execute_query("MATCH (n) DETACH DELETE n")
            await g.build_indices_and_constraints()
        for item in [i for i in items if i["dataset"] == dataset]:
            before, t0 = usage(), time.time()
            err, entities, facts = None, [], []
            try:
                r = await g.add_episode(
                    name=item["id"], episode_body=item["body"], source_description=dataset,
                    reference_time=parse_time(item), group_id=graph,
                    source=EpisodeType.message if dataset == "halumem" else EpisodeType.text,
                    # "noctx" variants: no previous episodes as context ([] = none; None = Graphiti's last 10)
                    previous_episode_uuids=[] if "noctx" in name else None,
                )
                entities, facts = [n.name for n in r.nodes], [e.fact for e in r.edges]
            except Exception as e:  # record and keep going: one bad episode shouldn't sink the run
                err = f"{type(e).__name__}: {e}"[:300]
            after = usage()
            out.append({**{k: item[k] for k in ("dataset", "id")}, "model": name, "error": err,
                        "entities": entities, "facts": facts, "secs": round(time.time() - t0, 1),
                        "calls": after["calls"] - before["calls"], "in": after["in"] - before["in"],
                        "out": after["out"] - before["out"], "content_tokens": len(item["body"]) // 4})
            print(f"[{name}] {dataset} {item['id']}: {len(entities)} entities, {len(facts)} facts, "
                  f"{out[-1]['calls']} calls, {out[-1]['secs']}s{' ERROR ' + err if err else ''}", flush=True)
        await driver.close()
    return out


JUDGE_PROMPT = """You check which GOLD facts are covered by a list of EXTRACTED facts and entities.
A gold fact is covered if the extracted facts (alone or together, with the entity names) state the
same information, even in different words. Ignore wording; do not give credit for guesses.

GOLD (numbered):
{gold}

EXTRACTED FACTS:
{facts}

EXTRACTED ENTITIES: {entities}

Reply with JSON: {{"covered": [numbers of the covered gold facts]}}"""


async def judge(client: AsyncOpenAI, gold: list[str], row: dict) -> list[int]:
    covered: list[int] = []
    for start in range(0, len(gold), 40):
        chunk = gold[start:start + 40]
        prompt = JUDGE_PROMPT.format(
            gold="\n".join(f"{i + 1}. {g}" for i, g in enumerate(chunk)),
            facts="\n".join(f"- {f}" for f in row["facts"]) or "(none)",
            entities=", ".join(row["entities"]) or "(none)",
        )
        r = await client.chat.completions.create(model=JUDGE_MODEL, temperature=0,
                                                 response_format={"type": "json_object"},
                                                 messages=[{"role": "user", "content": prompt}])
        nums = json.loads(r.choices[0].message.content).get("covered", [])
        covered += [start + n - 1 for n in nums if isinstance(n, int) and 1 <= n <= len(chunk)]
    return sorted(set(covered))


async def main(models: list[str]) -> None:
    load_env()
    items = json.loads((HERE / "data" / "items.json").read_text())
    if os.environ.get("DATASETS"):  # e.g. DATASETS=redocred
        items = [i for i in items if i["dataset"] in os.environ["DATASETS"].split(",")]
    gold = {(i["dataset"], i["id"]): i["gold"] for i in items}
    # RESUME=results/run-….json reruns only that run's failed items and keeps its good rows.
    kept: list[dict] = []
    if os.environ.get("RESUME"):
        prev = json.loads((HERE / os.environ["RESUME"]).read_text())
        kept = [r for r in prev if r["model"] in models and not r["error"]]
        failed = {(r["dataset"], r["id"]) for r in prev if r["model"] in models and r["error"]}
        items = [i for i in items if (i["dataset"], i["id"]) in failed]
        print(f"resuming: keeping {len(kept)} rows, rerunning {len(items)} items", flush=True)
    runs = await asyncio.gather(*(run_model(m, items, reset=not kept) for m in models))
    new_rows = [r for run in runs for r in run]

    jc = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    covered = await asyncio.gather(*(judge(jc, gold[(r["dataset"], r["id"])], r) for r in new_rows))
    for r, c in zip(new_rows, covered):
        r["gold_n"], r["covered_n"] = len(gold[(r["dataset"], r["id"])]), len(c)
    order = {(i["dataset"], i["id"]): n for n, i in enumerate(json.loads((HERE / "data" / "items.json").read_text()))}
    rows = sorted(kept + new_rows, key=lambda r: (r["model"], order[(r["dataset"], r["id"])]))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (HERE / "results" / f"run-{stamp}.json").write_text(json.dumps(rows, indent=1))

    print(f"\n{'model':9} {'dataset':9} {'recall':>7} {'facts':>6} {'errors':>6} {'calls':>6} "
          f"{'in_tok':>8} {'out_tok':>8} {'mult':>5} {'mins':>5}")
    for m in models:
        for ds in ("redocred", "halumem"):
            sel = [r for r in rows if r["model"] == m and r["dataset"] == ds]
            if not sel:
                continue
            g_n, c_n = sum(r["gold_n"] for r in sel), sum(r["covered_n"] for r in sel)
            tin, tout = sum(r["in"] for r in sel), sum(r["out"] for r in sel)
            content = sum(r["content_tokens"] for r in sel)
            print(f"{m:9} {ds:9} {c_n / g_n:7.1%} {sum(len(r['facts']) for r in sel):6} "
                  f"{sum(1 for r in sel if r['error']):6} {sum(r['calls'] for r in sel):6} {tin:8} {tout:8} "
                  f"{(tin + tout) / max(content, 1):5.1f} {sum(r['secs'] for r in sel) / 60:5.1f}")
    print(f"\nsaved results/run-{stamp}.json")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["baseline", "teacher"]))
