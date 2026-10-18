"""Precision judge: what share of a run's extracted facts the source actually supports.

Rescores existing results/run-*.json files (no re-extraction). The source for an item is its own text
plus the earlier items of the same dataset, since Graphiti sees previous episodes as context and may
restate facts from them. Judge: DeepSeek V4.1 Flash, thinking off, on DeepInfra (distillable, and not
one of the small contestants).

    python precision.py results/run-A.json [results/run-B.json …]
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI

from bench import HERE, load_env

JUDGE_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"
BASE_URL = "https://api.deepinfra.com/v1/openai"

PROMPT = """You check whether facts extracted by a memory system are supported by the SOURCE text.
A fact is supported if the source states it or directly implies it (paraphrase and entity aliases are
fine). It is unsupported if it adds details the source doesn't give, contradicts it, or is invented.
Earlier context is part of the source.

SOURCE:
{source}

FACTS (numbered):
{facts}

Reply with JSON: {{"unsupported": [numbers of the unsupported facts]}}"""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["unsupported"],
          "properties": {"unsupported": {"type": "array", "items": {"type": "integer"}}}}


async def judge(client: AsyncOpenAI, sem: asyncio.Semaphore, source: str, facts: list[str]) -> int:
    """Number of unsupported facts."""
    bad = 0
    for start in range(0, len(facts), 40):
        chunk = facts[start:start + 40]
        async with sem:
            r = await client.chat.completions.create(
                model=JUDGE_MODEL, temperature=0, max_tokens=1000,
                messages=[{"role": "user", "content": PROMPT.format(
                    source=source, facts="\n".join(f"{i + 1}. {f}" for i, f in enumerate(chunk)))}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "Unsupported", "strict": True, "schema": SCHEMA}},
                extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        nums = set(json.loads(r.choices[0].message.content)["unsupported"])
        bad += len([n for n in nums if 1 <= n <= len(chunk)])
    return bad


async def main(paths: list[str]) -> None:
    load_env()
    items = json.loads((HERE / os.environ.get("ITEMS", "data/items.json")).read_text())
    sources, seen = {}, {}
    for i in items:  # source = earlier items of the dataset (oldest first) + this one
        prev = seen.setdefault(i["dataset"], [])
        k = int(os.environ.get("PRECISION_CTX", "10"))  # earlier items given as context; 3 is cheaper on long users
        sources[(i["dataset"], i["id"])] = "\n\n---\n\n".join(prev[max(len(prev) - k, 0):] + [i["body"]])
        prev.append(i["body"])

    client = AsyncOpenAI(api_key=os.environ["DEEPINFRA_API_KEY"], base_url=BASE_URL, timeout=180, max_retries=3)
    sem = asyncio.Semaphore(8)
    print(f"{'file':26} {'model':24} {'dataset':9} {'recall':>7} {'precision':>9} {'facts':>6}")
    for path in paths:
        rows = json.loads(Path(path).read_text())
        todo = [r for r in rows if r["facts"] and "unsupported_n" not in r]
        bad = await asyncio.gather(*(judge(client, sem, sources[(r["dataset"], r["id"])], r["facts"]) for r in todo))
        for r, b in zip(todo, bad):
            r["unsupported_n"] = b
        Path(path).write_text(json.dumps(rows, indent=1))  # keep scores next to the run
        for m in dict.fromkeys(r["model"] for r in rows):
            for ds in ("redocred", "halumem"):
                sel = [r for r in rows if r["model"] == m and r["dataset"] == ds]
                if not sel:
                    continue
                n = sum(len(r["facts"]) for r in sel)
                rec = sum(r.get("covered_n", 0) for r in sel) / max(sum(r.get("gold_n", 0) for r in sel), 1)
                prec = 1 - sum(r.get("unsupported_n", 0) for r in sel) / n if n else float("nan")
                print(f"{Path(path).name:26} {m:24} {ds:9} {rec:7.1%} {prec:9.1%} {n:6}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
