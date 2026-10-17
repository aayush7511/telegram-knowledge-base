"""Replay one Re-DocRED doc through Graphiti with the teacher and log every model call
(schema name, finish reason, answer/reasoning length, tokens) to find why output is empty.

    ../../services/orchestrator/.venv/bin/python debug_empty.py "Ecuadorian Constituent Assembly"
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType

from bench import load_env

HERE = Path(__file__).parent
CALLS: list[dict] = []


class LoggingCompletions:
    def __init__(self, inner):
        self._inner = inner

    async def create(self, **kw):
        kw["extra_body"] = {"provider": {"require_parameters": True}, **(kw.get("extra_body") or {})}
        r = await self._inner.create(**kw)
        m = r.choices[0].message
        rf = kw.get("response_format") or {}
        CALLS.append({
            "schema": (rf.get("json_schema") or {}).get("name", rf.get("type")),
            "finish": r.choices[0].finish_reason,
            "answer_chars": len(m.content or ""),
            "reasoning_chars": len(getattr(m, "reasoning", None) or (m.model_extra or {}).get("reasoning") or ""),
            "in": r.usage.prompt_tokens, "out": r.usage.completion_tokens,
            "provider": (r.model_extra or {}).get("provider"),
            "answer": (m.content or "")[:300],
            "reasoning": getattr(m, "reasoning", None) or (m.model_extra or {}).get("reasoning") or "",
        })
        return r


class LoggingClient:
    def __init__(self, inner):
        self.chat = type("Chat", (), {})()
        self.chat.completions = LoggingCompletions(inner.chat.completions)


async def main(title: str) -> None:
    load_env()
    item = next(i for i in json.loads((HERE / "data" / "items.json").read_text()) if i["id"] == title)
    key = os.environ[os.environ.get("TEACHER_KEY_ENV", "TEACHER_API_KEY")]
    inner = AsyncOpenAI(api_key=key, base_url=os.environ["TEACHER_BASE_URL"], timeout=180, max_retries=1)
    model = os.environ["TEACHER_MODEL"]
    llm = OpenAIGenericClient(config=LLMConfig(api_key=key, base_url=os.environ["TEACHER_BASE_URL"], model=model,
                                               small_model=model, temperature=0),
                              client=LoggingClient(inner), structured_output_mode="json_schema")
    driver = FalkorDriver(host="127.0.0.1", port=6379, database="debugteacher")
    g = Graphiti(graph_driver=driver, llm_client=llm, embedder=OpenAIEmbedder(
        config=OpenAIEmbedderConfig(api_key=os.environ["OPENAI_API_KEY"], embedding_model="text-embedding-3-small")))
    if getattr(driver, "_init_task", None):
        await driver._init_task
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    await g.build_indices_and_constraints()
    err = None
    try:
        r = await g.add_episode(name=title, episode_body=item["body"], source_description="redocred",
                                reference_time=datetime(2026, 1, 1, tzinfo=timezone.utc), group_id="debugteacher",
                                source=EpisodeType.text)
        print(f"result: {len(r.nodes)} entities, {len(r.edges)} facts")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
        print("ERROR", err)
    await driver.close()
    for i, c in enumerate(CALLS):
        print(f"\n#{i} {c['schema']}  finish={c['finish']}  answer={c['answer_chars']}ch  "
              f"reasoning={c['reasoning_chars']}ch  tokens {c['in']}/{c['out']}  via {c['provider']}")
        print("   ", c["answer"].replace("\n", " ")[:300])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Ecuadorian Constituent Assembly"))
