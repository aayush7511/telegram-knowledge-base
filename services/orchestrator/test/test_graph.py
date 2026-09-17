"""graph.py pure helpers: episode assembly and time parsing (no FalkorDB, no OpenAI)."""
from datetime import timezone

import graph
from extract import ResponseObject


def test_blog_episode_body_is_title_and_summary_only():
    ro = ResponseObject(url="https://x.test/p", title="Title", author="Ann", sitename="X", text="...", summary="Gist.")
    body, source = graph.blog_episode(ro)
    assert body == "Title\n\nGist."
    assert source == "blog: https://x.test/p | site: X | author: Ann"


def test_blog_episode_omits_missing_metadata():
    ro = ResponseObject(url="https://x.test/p", title=None, author=None, sitename=None, summary="Gist.")
    body, source = graph.blog_episode(ro)
    assert body == "Gist."
    assert source == "blog: https://x.test/p"


def test_parse_time_received_handles_z_suffix():
    t = graph.parse_time_received("2026-09-16T10:00:00.000Z")
    assert t.tzinfo is not None and t.utcoffset().total_seconds() == 0
    assert t.isoformat() == "2026-09-16T10:00:00+00:00"


def test_parse_time_received_falls_back_to_now():
    t = graph.parse_time_received(None)
    assert t.tzinfo == timezone.utc
