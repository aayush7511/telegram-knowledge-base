"""graph.py pure helpers: episode assembly and time parsing (no FalkorDB, no OpenAI)."""
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
