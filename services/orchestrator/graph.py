"""Knowledge-graph write: one Graphiti episode per job, stored in FalkorDB.

Graphiti runs in-process: it calls OpenAI to extract entities and relationships
from the episode text, embeds them, and writes nodes/edges to FalkorDB over the
VPC. Everything here follows what the M0 spike established (docs/design/v2.md):

- `FalkorDriver` connects in its constructor and, inside a running event loop,
  kicks off its own index build as a background task. So the client is built
  lazily on first use (never at import), and that task is awaited once instead
  of calling `build_indices_and_constraints()` a second time, which races it.
- On FalkorDB, Graphiti's `group_id` *is* the graph name — it must equal the
  driver's `database`, or every write lands in a different graph.
- `add_episode(uuid=...)` reprocesses an *existing* episode (NodeNotFoundError
  otherwise), so keying by job_id means upserting the Episodic node first.
  Re-running a job then reuses the same episode instead of duplicating it.
- Same model in both Graphiti slots (an unset `small_model` silently falls
  back to gpt-4.1-nano) at temperature 0, so reprocessing is reproducible.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EpisodeType, EpisodicNode

from extract import ResponseObject

log = logging.getLogger("kb-orchestrator.graph")

GRAPH_NAME = "second-brain"  # FalkorDB graph key and Graphiti group_id, one value
LLM_MODEL = "gpt-4.1-mini-2025-04-14"
EMBEDDING_MODEL = "text-embedding-3-small"

_graphiti: Graphiti | None = None


async def get_graphiti() -> Graphiti:
    """Lazily build the Graphiti client (needs FALKORDB_* and OPENAI_API_KEY at first use)."""
    global _graphiti
    if _graphiti is None:
        driver = FalkorDriver(
            host=os.environ["FALKORDB_HOST"],
            port=int(os.environ.get("FALKORDB_PORT", "6379")),
            password=os.environ.get("FALKORDB_PASSWORD"),
            database=GRAPH_NAME,
        )
        api_key = os.environ["OPENAI_API_KEY"]
        client = Graphiti(
            graph_driver=driver,
            llm_client=OpenAIClient(
                config=LLMConfig(api_key=api_key, model=LLM_MODEL, small_model=LLM_MODEL, temperature=0)
            ),
            embedder=OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=api_key, embedding_model=EMBEDDING_MODEL)),
        )
        init_task = getattr(driver, "_init_task", None)
        if init_task is not None:
            await init_task
        _graphiti = client
    return _graphiti


def blog_episode(ro: ResponseObject) -> tuple[str, str]:
    """(episode body, source_description) for a blog job.

    Body is title + summary only. URL, site, and author go in source_description,
    which Graphiti's text-extraction prompt never sees — in M0 a metadata header
    in the body turned `anthropic.com` and `paulgraham.com` into entities and
    crowded out the real content.
    """
    body = f"{ro.title}\n\n{ro.summary}" if ro.title else (ro.summary or "")
    meta = [f"blog: {ro.url}"] + [f"{k}: {v}" for k, v in (("site", ro.sitename), ("author", ro.author)) if v]
    return body, " | ".join(meta)


def parse_time_received(value: str | None) -> datetime:
    """Job descriptor `time_received` (ISO 8601, Z-suffixed) → aware datetime; now if absent."""
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def write_episode(
    job_id: str,
    *,
    name: str,
    body: str,
    source_description: str,
    reference_time: datetime,
) -> None:
    """Upsert the Episodic node keyed by job_id, then let Graphiti extract from it."""
    graphiti = await get_graphiti()
    await EpisodicNode(
        uuid=job_id,
        name=name,
        group_id=GRAPH_NAME,
        labels=[],
        source=EpisodeType.text,
        content=body,
        source_description=source_description,
        created_at=datetime.now(timezone.utc),
        valid_at=reference_time,
    ).save(graphiti.driver)
    result = await graphiti.add_episode(
        name=name,
        episode_body=body,
        source_description=source_description,
        reference_time=reference_time,
        source=EpisodeType.text,
        group_id=GRAPH_NAME,
        uuid=job_id,
    )
    log.info(
        "graph write: job_id=%s entities=%d facts=%d", job_id, len(result.nodes), len(result.edges)
    )
