"""Per-source fetchers: URL parsing, payload → ResponseObject, NotSupported cases.

Network calls (captions, oEmbed, FxTwitter) are monkeypatched — offline.
"""
import asyncio

import pytest
import youtube_transcript_api as yta

import sources


def run(coro):
    return asyncio.run(coro)


# --- YouTube ---------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=zjkBMFhNj_g",
    "https://m.youtube.com/watch?v=zjkBMFhNj_g&t=42s",
    "https://youtu.be/zjkBMFhNj_g?si=abc",
    "https://www.youtube.com/shorts/zjkBMFhNj_g",
    "https://www.youtube.com/live/zjkBMFhNj_g",
])
def test_youtube_video_id(url):
    assert sources.youtube_video_id(url) == "zjkBMFhNj_g"


def test_youtube_video_id_rejects_garbage():
    with pytest.raises(ValueError):
        sources.youtube_video_id("https://www.youtube.com/watch?v=short")


def _wire_youtube(monkeypatch, transcript, oembed=None):
    def fake_transcript(video_id):
        if isinstance(transcript, Exception):
            raise transcript
        return transcript

    async def fake_oembed(video_id):
        return oembed or {}

    monkeypatch.setattr(sources, "_youtube_transcript", fake_transcript)
    monkeypatch.setattr(sources, "_youtube_oembed", fake_oembed)


def test_fetch_youtube_assembles_captions_and_metadata(monkeypatch):
    _wire_youtube(monkeypatch, "hi everyone so recently",
                  {"title": "[1hr Talk] Intro to Large Language Models", "author_name": "Andrej Karpathy"})
    ro = run(sources.fetch_youtube("https://youtu.be/zjkBMFhNj_g"))
    assert ro.text == "hi everyone so recently"
    assert ro.title == "[1hr Talk] Intro to Large Language Models"
    assert ro.author == "Andrej Karpathy"
    assert ro.sitename == "YouTube"
    assert ro.url == "https://youtu.be/zjkBMFhNj_g"


def test_fetch_youtube_without_metadata_still_works(monkeypatch):
    _wire_youtube(monkeypatch, "captions")
    ro = run(sources.fetch_youtube("https://youtu.be/zjkBMFhNj_g"))
    assert ro.text == "captions" and ro.title is None


@pytest.mark.parametrize("transcript", ["", yta.TranscriptsDisabled("zjkBMFhNj_g")])
def test_fetch_youtube_no_captions_is_not_supported(monkeypatch, transcript):
    _wire_youtube(monkeypatch, transcript)
    with pytest.raises(sources.NotSupported, match="no captions"):
        run(sources.fetch_youtube("https://youtu.be/zjkBMFhNj_g"))


def test_fetch_youtube_unavailable_is_not_supported(monkeypatch):
    _wire_youtube(monkeypatch, yta.VideoUnavailable("zjkBMFhNj_g"))
    with pytest.raises(sources.NotSupported, match="unavailable"):
        run(sources.fetch_youtube("https://youtu.be/zjkBMFhNj_g"))


def test_fetch_youtube_ip_block_is_an_ordinary_failure(monkeypatch):
    """Blocks aren't "not supported" — the job just fails (retryable from D1)."""
    _wire_youtube(monkeypatch, yta.RequestBlocked("zjkBMFhNj_g"))
    with pytest.raises(yta.RequestBlocked):
        run(sources.fetch_youtube("https://youtu.be/zjkBMFhNj_g"))


def test_fetch_youtube_times_out(monkeypatch):
    import time

    _wire_youtube(monkeypatch, "never")
    monkeypatch.setattr(sources, "_youtube_transcript", lambda vid: time.sleep(0.5) or "late")
    monkeypatch.setattr(sources, "YOUTUBE_TIMEOUT_S", 0.05)
    with pytest.raises(asyncio.TimeoutError):
        run(sources.fetch_youtube("https://youtu.be/zjkBMFhNj_g"))


# --- X ---------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://x.com/karpathy/status/1977755427569111362",
    "https://twitter.com/karpathy/status/1977755427569111362/photo/1",
    "https://x.com/i/web/status/1977755427569111362",
])
def test_x_status_id(url):
    assert sources.x_status_id(url) == "1977755427569111362"


def _post(text, screen_name="karpathy", **extra):
    return {"text": text, "author": {"screen_name": screen_name}, **extra}


def _wire_x(monkeypatch, payload):
    async def fake_thread(status_id):
        return payload

    monkeypatch.setattr(sources, "_x_thread", fake_thread)


def test_fetch_x_joins_the_authors_thread_in_order(monkeypatch):
    first, second = _post("Excited to release nanochat"), _post("It's ~8K lines of code")
    _wire_x(monkeypatch, {"status": second, "thread": [first, second]})
    ro = run(sources.fetch_x("https://x.com/karpathy/status/2"))
    assert ro.text == "Excited to release nanochat\n\nIt's ~8K lines of code"
    assert ro.author == "@karpathy" and ro.sitename == "X" and ro.title is None


def test_fetch_x_appends_quoted_post(monkeypatch):
    post = _post("Nice article discussing our research!", "james_y_zou",
                 quote={"text": "Our AI scientist agents paper is out", "author": {"screen_name": "stanford"}})
    _wire_x(monkeypatch, {"status": post, "thread": [post]})
    ro = run(sources.fetch_x("https://x.com/james_y_zou/status/1"))
    assert ro.text == "Nice article discussing our research!\n\nQuoting @stanford: Our AI scientist agents paper is out"


def test_fetch_x_flattens_an_article(monkeypatch):
    article = {
        "title": "2025 LLM Year in Review",
        "content": {"blocks": [
            {"type": "unstyled", "text": "2025 has been a strong year."},
            {"type": "ordered-list-item", "text": "RLVR"},
            {"type": "ordered-list-item", "text": "Vibe coding"},
            {"type": "atomic", "text": " "},
            {"type": "unordered-list-item", "text": "a bullet"},
            {"type": "unstyled", "text": "The end."},
        ]},
    }
    post = _post("", article=article)
    _wire_x(monkeypatch, {"status": post, "thread": [post]})
    ro = run(sources.fetch_x("https://x.com/karpathy/status/2002118205729562949"))
    assert ro.title == "2025 LLM Year in Review"
    assert ro.text == "2025 has been a strong year.\n\n1. RLVR\n\n2. Vibe coding\n\n- a bullet\n\nThe end."


def test_fetch_x_missing_post_is_not_supported(monkeypatch):
    _wire_x(monkeypatch, None)
    with pytest.raises(sources.NotSupported, match="doesn't exist"):
        run(sources.fetch_x("https://x.com/a/status/1000000000000000001"))


def test_fetch_x_media_only_post_is_not_supported(monkeypatch):
    post = _post("")
    _wire_x(monkeypatch, {"status": post, "thread": [post]})
    with pytest.raises(sources.NotSupported, match="no text"):
        run(sources.fetch_x("https://x.com/a/status/1"))


# --- Private addresses -----------------------------------------------------

import socket

import fetcher


@pytest.mark.parametrize("addr, public", [
    ("93.184.215.14", True),
    ("2606:2800:21f:cb07:6820:80da:af6b:8b2c", True),
    ("127.0.0.1", False),
    ("10.128.0.2", False),       # the FalkorDB VM
    ("169.254.169.254", False),  # GCP metadata
    ("100.64.0.1", False),       # carrier-grade NAT
    ("::1", False),
    ("fe80::1%eth0", False),     # link-local with a zone id
])
def test_is_public_host(monkeypatch, addr, public):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [(None, None, None, "", (addr, 0))])
    assert run(fetcher.is_public_host("some.host")) is public


def test_is_public_host_rejects_if_any_address_is_private(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [
        (None, None, None, "", ("93.184.215.14", 0)), (None, None, None, "", ("10.0.0.5", 0)),
    ])
    assert run(fetcher.is_public_host("rebind.example")) is False


def test_is_public_host_lets_unresolvable_hosts_fail_on_their_own(monkeypatch):
    def nxdomain(host, port):
        raise socket.gaierror("nodename nor servname provided")

    monkeypatch.setattr(socket, "getaddrinfo", nxdomain)
    assert run(fetcher.is_public_host("no-such-host.invalid")) is True


def test_fetch_blog_private_address_is_not_supported(monkeypatch):
    async def private(url, **kw):
        raise fetcher.PrivateAddress("http://10.128.0.2:3000/")

    monkeypatch.setattr(fetcher, "render", private)
    with pytest.raises(sources.NotSupported, match="private network address"):
        run(sources.fetch_blog("https://example.com/redirects-inward"))
