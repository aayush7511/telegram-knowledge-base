"""graph.py: episode assembly, time parsing, and what write_episode returns (no FalkorDB, no OpenAI)."""
from datetime import timezone

import graph
from extract import ResponseObject


def test_url_episode_body_is_title_and_full_text():
    ro = ResponseObject(url="https://x.test/p", title="Title", author="Ann", sitename="X",
                         text="The full cleaned article body.", summary="Gist.")
    body, source = graph.url_episode(ro, "blog")
    assert body == "Title\n\nThe full cleaned article body."
    assert source == "blog: https://x.test/p | site: X | author: Ann"


def test_url_episode_omits_missing_metadata():
    ro = ResponseObject(url="https://x.test/p", title=None, author=None, sitename=None, text="Body text.")
    body, source = graph.url_episode(ro, "blog")
    assert body == "Body text."
    assert source == "blog: https://x.test/p"


def test_url_episode_with_a_title_but_no_text():
    ro = ResponseObject(url="https://github.com/o/r/issues/1", title="Just a title", text="")
    body, _ = graph.url_episode(ro, "github")
    assert body == "Just a title"


def test_url_episode_labels_provenance_with_the_source():
    ro = ResponseObject(url="https://x.com/a/status/1", author="a", text="A post.")
    _, source = graph.url_episode(ro, "x")
    assert source == "x: https://x.com/a/status/1 | author: a"


def test_parse_time_received_handles_z_suffix():
    t = graph.parse_time_received("2026-09-16T10:00:00.000Z")
    assert t.tzinfo is not None and t.utcoffset().total_seconds() == 0
    assert t.isoformat() == "2026-09-16T10:00:00+00:00"


def test_parse_time_received_falls_back_to_now():
    t = graph.parse_time_received(None)
    assert t.tzinfo == timezone.utc


def test_parse_source_reads_the_kind_and_url_back_from_url_episode():
    assert graph.parse_source("blog: https://x.test/p | site: X | author: Ann") == ("blog", "https://x.test/p")
    assert graph.parse_source("x: https://x.com/a/status/1") == ("x", "https://x.com/a/status/1")


def test_parse_source_telegram_note_has_no_url():
    assert graph.parse_source("telegram text note") == ("note", None)


def test_parse_source_telegram_pdf_file_has_no_url():
    assert graph.parse_source("pdf: Telegram file | site: Telegram") == ("pdf", None)


def test_write_episode_returns_entities_and_facts(monkeypatch):
    """specs/extraction-reply.md: the names and facts Graphiti extracted, in its order."""
    import asyncio
    from datetime import datetime
    from types import SimpleNamespace

    class FakeGraphiti:
        driver = object()

        async def add_episode(self, **kw):
            return SimpleNamespace(
                nodes=[SimpleNamespace(name="Zep"), SimpleNamespace(name="Graphiti")],
                edges=[SimpleNamespace(fact="Zep built Graphiti."), SimpleNamespace(fact="Graphiti uses FalkorDB.")],
            )

    async def fake_get_graphiti():
        return FakeGraphiti()

    async def fake_save(self, driver):
        pass

    monkeypatch.setattr(graph, "get_graphiti", fake_get_graphiti)
    monkeypatch.setattr(graph.EpisodicNode, "save", fake_save)

    extracted = asyncio.run(graph.write_episode(
        "j1", name="T", body="body", source_description="blog: u",
        reference_time=datetime(2026, 10, 17, tzinfo=timezone.utc),
    ))

    assert extracted.entities == ["Zep", "Graphiti"]
    assert extracted.facts == ["Zep built Graphiti.", "Graphiti uses FalkorDB."]
