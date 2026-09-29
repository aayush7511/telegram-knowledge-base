"""Knowledge graph: one Graphiti episode per job, stored in FalkorDB, and fact
search over it for the MCP connector.

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

Episode body: the full cleaned article, not just the summary — confirmed in
spikes/full-article-episode (2026-09-17). Summary-only was cheaper and cleaner
but discarded real facts (e.g. co-founders a summary compresses to one name).
Full text recovers them at ~2.3x the tokens. It also pulls in newsletter-style
extras (sponsor lines, "further reading" link roundups) — tried and reverted a
heuristic to strip those, since they're pointers to related material that may
be worth branching the graph out to later, not pure noise to discard.
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
from graphiti_core.search.search_config_recipes import EDGE_HYBRID_SEARCH_RRF

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


def url_episode(ro: ResponseObject, source: str) -> tuple[str, str]:
    """(episode body, source_description) for a URL job from `source` (url_source).

    Body is title + the full fetched text, not the summary — see the module
    docstring. URL, site, and author go in source_description, which
    Graphiti's text-extraction prompt never sees — in M0 a metadata header in
    the body turned `anthropic.com` and `paulgraham.com` into entities and
    crowded out the real content.
    """
    body = "\n\n".join(part for part in (ro.title, ro.text) if part)
    meta = [f"{source}: {ro.url}"] + [f"{k}: {v}" for k, v in (("site", ro.sitename), ("author", ro.author)) if v]
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


def parse_source(source_description: str) -> tuple[str, str | None]:
    """(kind, url) from an episode's source_description — the inverse of url_episode.

    URL episodes read "<source>: <url> | site: … | author: …"; a Telegram PDF
    file's "url" is "Telegram file", and notes are "telegram text note", so
    only an http(s) value counts as a link.
    """
    head = source_description.split(" | ", 1)[0]
    kind, sep, value = head.partition(": ")
    if not sep:
        return ("note" if head == "telegram text note" else head), None
    return kind, value if value.startswith(("http://", "https://")) else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def search_facts(query: str, limit: int) -> list[dict]:
    """Hybrid search (BM25 + embeddings, RRF-ranked — no LLM call) over facts,
    each with the episodes it came from as sources. Episode bodies (full
    article text) are never returned.

    Uses search_() with a copied config: Graphiti's search() sets `limit` on the
    shared module-level recipe, which concurrent requests would race on.

    No group_ids: the driver's graph already is GRAPH_NAME, and passing it
    breaks BM25 — Graphiti filters the fulltext query on `"second\\-brain"`,
    but FalkorDB's tokenizer splits the stored value at the hyphen, so it
    never matches and every keyword search came back empty (checked live
    2026-09-29).

    No relevance cutoff either: measured on the live graph, relevant facts
    score 0.35–0.46 cosine and unrelated ones 0.25–0.41, so no threshold
    separates them. The calling model judges relevance from the facts.
    """
    graphiti = await get_graphiti()
    config = EDGE_HYBRID_SEARCH_RRF.model_copy(update={"limit": limit})
    edges = (await graphiti.search_(query, config=config, group_ids=None)).edges

    episode_uuids = list(dict.fromkeys(u for edge in edges for u in edge.episodes))
    episodes = await EpisodicNode.get_by_uuids(graphiti.driver, episode_uuids) if episode_uuids else []
    by_uuid = {ep.uuid: ep for ep in episodes}

    results = []
    for edge in edges:
        sources = []
        for uuid in edge.episodes:
            ep = by_uuid.get(uuid)
            if ep is None:
                continue
            kind, url = parse_source(ep.source_description)
            sources.append({"title": ep.name, "kind": kind, "url": url, "saved_at": _iso(ep.valid_at)})
        results.append(
            {
                "fact": edge.fact,
                "valid_at": _iso(edge.valid_at),
                "invalid_at": _iso(edge.invalid_at),
                "sources": sources,
            }
        )
    return results
