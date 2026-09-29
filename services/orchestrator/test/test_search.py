"""POST /search and graph.search_facts: auth, validation, and how facts are
joined to their source episodes. Graphiti and FalkorDB are faked — offline."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import graph
import main

HEADERS = {"X-KB-Secret": "s"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KB_SHARED_SECRET", "s")
    calls = []

    async def fake_search_facts(query, limit):
        calls.append((query, limit))
        return [{"fact": "f", "valid_at": None, "invalid_at": None, "sources": []}]

    monkeypatch.setattr(main.graph, "search_facts", fake_search_facts)
    c = TestClient(main.app)
    c.calls = calls
    return c


def test_search_requires_the_shared_secret(client):
    assert client.post("/search", json={"query": "q"}).status_code == 401
    assert client.post("/search", json={"query": "q"}, headers={"X-KB-Secret": "wrong"}).status_code == 401
    assert client.calls == []


def test_search_returns_results_with_default_limit(client):
    resp = client.post("/search", json={"query": "  agent memory  "}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"results": [{"fact": "f", "valid_at": None, "invalid_at": None, "sources": []}]}
    assert client.calls == [("agent memory", 10)]


@pytest.mark.parametrize("body", [{}, {"query": "   "}, {"query": "q", "limit": 0},
                                  {"query": "q", "limit": 31}, {"query": "q", "limit": "5"},
                                  {"query": "q", "limit": True}, {"query": "q", "limit": 2.5}])
def test_search_rejects_bad_input(client, body):
    assert client.post("/search", json=body, headers=HEADERS).status_code == 400
    assert client.calls == []


T1 = datetime(2026, 9, 16, 10, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)


def _edge(fact, episodes, valid_at=None, invalid_at=None):
    return SimpleNamespace(fact=fact, episodes=episodes, valid_at=valid_at, invalid_at=invalid_at)


def _episode(uuid, name, source_description, valid_at):
    return SimpleNamespace(uuid=uuid, name=name, source_description=source_description,
                           valid_at=valid_at, content="FULL ARTICLE TEXT")


def test_search_facts_joins_each_fact_to_its_source_episodes(monkeypatch):
    edges = [
        _edge("Weng describes agent memory", ["e1"], valid_at=T1),
        _edge("FalkorDB runs on the e2-micro", ["e2", "e1", "gone"], valid_at=T1, invalid_at=T2),
    ]
    seen = {}

    class FakeGraphiti:
        driver = object()

        async def search_(self, query, config, group_ids):
            seen.update(query=query, limit=config.limit, group_ids=group_ids)
            return SimpleNamespace(edges=edges)

    async def fake_get_graphiti():
        return FakeGraphiti()

    async def fake_get_by_uuids(driver, uuids):
        seen["uuids"] = uuids
        return [_episode("e1", "LLM Powered Autonomous Agents",
                         "blog: https://lilianweng.github.io/posts/2023-06-23-agent/ | site: Lil'Log", T1),
                _episode("e2", "Remember: FalkorDB runs", "telegram text note", T2)]

    monkeypatch.setattr(graph, "get_graphiti", fake_get_graphiti)
    monkeypatch.setattr(graph.EpisodicNode, "get_by_uuids", fake_get_by_uuids)

    results = asyncio.run(graph.search_facts("agent memory", 5))

    # group_ids=None: a group filter on "second-brain" breaks FalkorDB's BM25 (see search_facts)
    assert seen == {"query": "agent memory", "limit": 5, "group_ids": None,
                    "uuids": ["e1", "e2", "gone"]}
    assert results == [
        {"fact": "Weng describes agent memory", "valid_at": T1.isoformat(), "invalid_at": None,
         "sources": [{"title": "LLM Powered Autonomous Agents", "kind": "blog",
                      "url": "https://lilianweng.github.io/posts/2023-06-23-agent/", "saved_at": T1.isoformat()}]},
        {"fact": "FalkorDB runs on the e2-micro", "valid_at": T1.isoformat(), "invalid_at": T2.isoformat(),
         "sources": [{"title": "Remember: FalkorDB runs", "kind": "note", "url": None, "saved_at": T2.isoformat()},
                     {"title": "LLM Powered Autonomous Agents", "kind": "blog",
                      "url": "https://lilianweng.github.io/posts/2023-06-23-agent/", "saved_at": T1.isoformat()}]},
    ]
    assert "FULL ARTICLE TEXT" not in repr(results)


def test_search_facts_does_not_mutate_the_shared_recipe(monkeypatch):
    class FakeGraphiti:
        driver = object()

        async def search_(self, query, config, group_ids):
            return SimpleNamespace(edges=[])

    async def fake_get_graphiti():
        return FakeGraphiti()

    monkeypatch.setattr(graph, "get_graphiti", fake_get_graphiti)
    before = graph.EDGE_HYBRID_SEARCH_RRF.limit
    assert asyncio.run(graph.search_facts("q", 27)) == []
    assert graph.EDGE_HYBRID_SEARCH_RRF.limit == before
