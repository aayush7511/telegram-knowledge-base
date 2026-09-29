"""Per-source fetchers: URL parsing, payload → ResponseObject, NotSupported cases.

Network calls (captions, oEmbed, FxTwitter) are monkeypatched — offline.
"""
import asyncio

import functools

import httpx
import pytest

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
    async def fake_transcript(video_id):
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


def test_fetch_youtube_empty_captions_is_not_supported(monkeypatch):
    _wire_youtube(monkeypatch, "  ")
    with pytest.raises(sources.NotSupported, match="no captions"):
        run(sources.fetch_youtube("https://youtu.be/zjkBMFhNj_g"))


# Supadata, over a mock transport: status codes per its docs.

def _supadata(monkeypatch, handler, key="test-key"):
    if key:
        monkeypatch.setenv("SUPADATA_API_KEY", key)
    else:
        monkeypatch.delenv("SUPADATA_API_KEY", raising=False)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(sources.asyncio, "sleep", lambda seconds: real_sleep(0))
    requests = []

    def record(req):
        requests.append(req)
        return handler(req)

    monkeypatch.setattr(sources.httpx, "AsyncClient",
                        functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(record)))
    return requests


def test_supadata_native_captions(monkeypatch):
    reqs = _supadata(monkeypatch, lambda req: httpx.Response(200, json={"content": "hi everyone", "lang": "en"}))
    assert run(sources._youtube_transcript("zjkBMFhNj_g")) == "hi everyone"
    [req] = reqs
    assert req.headers["x-api-key"] == "test-key"
    # native only — auto/generate would bill 2 credits per minute of audio
    assert req.url.params["mode"] == "native" and req.url.params["text"] == "true"
    assert req.url.params["url"] == "https://www.youtube.com/watch?v=zjkBMFhNj_g"


def test_supadata_long_video_polls_the_job(monkeypatch):
    replies = iter([
        httpx.Response(202, json={"jobId": "job-1"}),
        httpx.Response(200, json={"status": "active"}),
        httpx.Response(200, json={"status": "completed", "content": [{"text": "part one"}, {"text": "part two"}]}),
    ])
    reqs = _supadata(monkeypatch, lambda req: next(replies))
    assert run(sources._youtube_transcript("zjkBMFhNj_g")) == "part one part two"
    assert [r.url.path for r in reqs] == ["/v1/transcript", "/v1/transcript/job-1", "/v1/transcript/job-1"]


@pytest.mark.parametrize("status, reason", [
    (206, "no captions"),
    (404, "unavailable, private, or age-restricted"),
    (429, "quota is used up"),
])
def test_supadata_not_supported_cases(monkeypatch, status, reason):
    _supadata(monkeypatch, lambda req: httpx.Response(status, json={"error": "x"}))
    with pytest.raises(sources.NotSupported, match=reason):
        run(sources._youtube_transcript("zjkBMFhNj_g"))


def test_supadata_bad_key_is_an_ordinary_failure(monkeypatch):
    _supadata(monkeypatch, lambda req: httpx.Response(401, json={"error": "unauthorized"}))
    with pytest.raises(httpx.HTTPStatusError):
        run(sources._youtube_transcript("zjkBMFhNj_g"))


def test_supadata_failed_job_and_timeout(monkeypatch):
    replies = iter([httpx.Response(202, json={"jobId": "j"}), httpx.Response(200, json={"status": "failed", "error": "boom"})])
    _supadata(monkeypatch, lambda req: next(replies))
    with pytest.raises(RuntimeError, match="boom"):
        run(sources._youtube_transcript("zjkBMFhNj_g"))

    monkeypatch.setattr(sources, "YOUTUBE_TIMEOUT_S", 9)  # 3 polls at SUPADATA_POLL_S=3
    _supadata(monkeypatch, lambda req: httpx.Response(202, json={"jobId": "j"}) if req.url.path.endswith("transcript")
              else httpx.Response(200, json={"status": "queued"}))
    with pytest.raises(TimeoutError):
        run(sources._youtube_transcript("zjkBMFhNj_g"))


def test_youtube_without_a_supadata_key_is_not_supported(monkeypatch):
    _supadata(monkeypatch, lambda req: httpx.Response(500), key=None)
    with pytest.raises(sources.NotSupported, match="aren't set up yet"):
        run(sources._youtube_transcript("zjkBMFhNj_g"))


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


# --- Stack Exchange --------------------------------------------------------

@pytest.mark.parametrize("url, ref", [
    ("https://stackoverflow.com/questions/11227809/why-is-it-faster", ("stackoverflow.com", "question", "11227809")),
    ("https://stackoverflow.com/q/11227809", ("stackoverflow.com", "question", "11227809")),
    ("https://stackoverflow.com/a/11227902", ("stackoverflow.com", "answer", "11227902")),
    ("https://stackoverflow.com/questions/11227809/why/11227902#11227902", ("stackoverflow.com", "answer", "11227902")),
    ("https://unix.stackexchange.com/questions/1/dd", ("unix.stackexchange.com", "question", "1")),
])
def test_stackexchange_ref(url, ref):
    assert sources.stackexchange_ref(url) == ref


QUESTION = {"question_id": 7, "title": "Why &quot;x&quot;?", "body": "<p>Why is <code>x</code> slow?</p>",
            "owner": {"display_name": "Asker"}}


def _wire_se(monkeypatch, routes):
    calls = []

    async def fake_get(path, site, **params):
        calls.append(path)
        return routes.get(path, [])

    monkeypatch.setattr(sources, "_se_get", fake_get)
    return calls


def _answer(answer_id, body, name="Answerer"):
    return {"answer_id": answer_id, "question_id": 7, "body": f"<p>{body}</p>", "owner": {"display_name": name}}


def test_fetch_stackexchange_uses_the_accepted_answer(monkeypatch):
    _wire_se(monkeypatch, {"questions/7": [{**QUESTION, "accepted_answer_id": 70, "answer_count": 3}],
                           "answers/70": [_answer(70, "Branch prediction.")]})
    ro = run(sources.fetch_stackexchange("https://stackoverflow.com/questions/7/why"))
    assert ro.title == 'Why "x"?' and ro.author == "Asker" and ro.sitename == "stackoverflow.com"
    assert ro.text == "Why is x slow?\n\nAccepted answer by Answerer:\n\nBranch prediction."


def test_fetch_stackexchange_falls_back_to_top_voted(monkeypatch):
    calls = _wire_se(monkeypatch, {"questions/7": [{**QUESTION, "answer_count": 2}],
                                   "questions/7/answers": [_answer(71, "Caching.")]})
    ro = run(sources.fetch_stackexchange("https://stackoverflow.com/q/7"))
    assert ro.text.endswith("Top-voted answer by Answerer:\n\nCaching.")
    assert calls == ["questions/7", "questions/7/answers"]


def test_fetch_stackexchange_question_alone_when_unanswered(monkeypatch):
    calls = _wire_se(monkeypatch, {"questions/7": [{**QUESTION, "answer_count": 0}]})
    ro = run(sources.fetch_stackexchange("https://stackoverflow.com/q/7"))
    assert ro.text == "Why is x slow?"
    assert calls == ["questions/7"]


def test_fetch_stackexchange_answer_link_saves_that_answer(monkeypatch):
    calls = _wire_se(monkeypatch, {"answers/72": [_answer(72, "A linked one.")],
                                   "questions/7": [{**QUESTION, "accepted_answer_id": 70, "answer_count": 3}]})
    ro = run(sources.fetch_stackexchange("https://stackoverflow.com/a/72"))
    assert ro.text.endswith("Linked answer by Answerer:\n\nA linked one.")
    assert "answers/70" not in calls  # the accepted answer isn't fetched


def test_fetch_stackexchange_deleted_question_is_not_supported(monkeypatch):
    _wire_se(monkeypatch, {})
    with pytest.raises(sources.NotSupported, match="doesn't exist"):
        run(sources.fetch_stackexchange("https://stackoverflow.com/q/1"))


# --- GitHub ----------------------------------------------------------------


def _wire_github(monkeypatch, routes):
    """routes: api path → (status, body); body is text (raw) or a dict (json)."""
    calls = []

    async def fake_get(path, *, raw=False):
        calls.append(path)
        status, body = routes.get(path, (404, {"message": "Not Found"}))
        kw = {"text": body} if isinstance(body, str) else {"json": body}
        return httpx.Response(status, **kw)

    monkeypatch.setattr(sources, "_github_get", fake_get)
    return calls


def test_fetch_github_repo_is_its_readme(monkeypatch):
    _wire_github(monkeypatch, {"repos/getzep/graphiti/readme": (200, "# Graphiti\n\nTemporal knowledge graphs.")})
    ro = run(sources.fetch_github("https://github.com/getzep/graphiti.git"))
    assert ro.title == "getzep/graphiti" and ro.author == "getzep" and ro.sitename == "GitHub"
    assert ro.text == "# Graphiti\n\nTemporal knowledge graphs."


def test_fetch_github_repo_without_readme_vs_missing_repo(monkeypatch):
    _wire_github(monkeypatch, {"repos/a/has-no-readme": (200, {"full_name": "a/has-no-readme"})})
    with pytest.raises(sources.NotSupported, match="no README"):
        run(sources.fetch_github("https://github.com/a/has-no-readme"))
    with pytest.raises(sources.NotSupported, match="doesn't exist or is private"):
        run(sources.fetch_github("https://github.com/a/missing"))


@pytest.mark.parametrize("kind", ["issues", "pull"])
def test_fetch_github_issue_or_pr_is_title_and_description(monkeypatch, kind):
    calls = _wire_github(monkeypatch, {"repos/getzep/graphiti/issues/12": (
        200, {"title": "Support FalkorDB", "body": "  Add a FalkorDB driver.  ", "user": {"login": "someone"}})})
    ro = run(sources.fetch_github(f"https://github.com/getzep/graphiti/{kind}/12"))
    assert (ro.title, ro.text, ro.author) == ("Support FalkorDB", "Add a FalkorDB driver.", "someone")
    assert ro.sitename == "GitHub · getzep/graphiti"
    assert calls == ["repos/getzep/graphiti/issues/12"]  # no comments fetched


def test_fetch_github_issue_without_description(monkeypatch):
    _wire_github(monkeypatch, {"repos/o/r/issues/1": (200, {"title": "Just a title", "body": None, "user": {}})})
    ro = run(sources.fetch_github("https://github.com/o/r/issues/1"))
    assert ro.title == "Just a title" and ro.text == ""


def test_fetch_github_gist_is_its_files(monkeypatch):
    _wire_github(monkeypatch, {"gists/abc123": (200, {
        "description": "Notes", "owner": {"login": "karpathy"},
        "files": {"a.md": {"filename": "a.md", "content": "Alpha"}, "b.py": {"filename": "b.py", "content": "print(1)"}},
    })})
    ro = run(sources.fetch_github("https://gist.github.com/karpathy/abc123"))
    assert ro.title == "Notes" and ro.author == "karpathy"
    assert ro.text == "a.md:\n\nAlpha\n\nb.py:\n\nprint(1)"


# --- PDF -------------------------------------------------------------------

SENTENCE = "Attention is all you need for sequence transduction models. "


def make_pdf(text: str | None) -> bytes:
    """A one-page PDF; `text=None` makes a page with no text layer (like a scan)."""
    content = f"BT /F1 10 Tf 20 700 Td ({text}) Tj ET".encode() if text else b""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def test_pdf_to_response_extracts_text():
    ro = sources.pdf_to_response(make_pdf(SENTENCE * 5), "https://arxiv.org/pdf/1706.03762", "arxiv.org")
    assert "Attention is all you need" in ro.text and len(ro.text) >= sources.MIN_PDF_CHARS
    assert ro.url == "https://arxiv.org/pdf/1706.03762" and ro.sitename == "arxiv.org"


@pytest.mark.parametrize("data, reason", [
    (make_pdf(None), "no text layer"),
    (make_pdf("too short"), "no text layer"),
    (b"<html>not a pdf</html>", "not a page or a PDF"),
    (b"%PDF-1.4\ngarbage that is not a pdf", "damaged or unreadable"),
])
def test_pdf_to_response_not_supported(data, reason):
    with pytest.raises(sources.NotSupported, match=reason):
        sources.pdf_to_response(data, "u", None)


def _mock_http(monkeypatch, handler):
    monkeypatch.setattr(sources.httpx, "AsyncClient",
                        functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)))


def test_download_pdf_follows_public_redirects(monkeypatch):
    async def public(host):
        return True

    monkeypatch.setattr(fetcher, "is_public_host", public)
    pdf = make_pdf(SENTENCE * 5)
    _mock_http(monkeypatch, lambda req: (
        httpx.Response(302, headers={"location": "/files/paper.pdf"}) if req.url.path == "/pdf/1"
        else httpx.Response(200, content=pdf)))
    assert run(sources._download_pdf("https://example.org/pdf/1")) == pdf


def test_download_pdf_refuses_a_redirect_to_a_private_address(monkeypatch):
    async def public(host):
        return host != "internal.example"

    monkeypatch.setattr(fetcher, "is_public_host", public)
    _mock_http(monkeypatch, lambda req: httpx.Response(302, headers={"location": "http://internal.example/x.pdf"}))
    with pytest.raises(sources.NotSupported, match="private network address"):
        run(sources._download_pdf("https://example.org/paper.pdf"))


def test_download_pdf_caps_size(monkeypatch):
    async def public(host):
        return True

    monkeypatch.setattr(fetcher, "is_public_host", public)
    monkeypatch.setattr(sources, "PDF_MAX_BYTES", 1000)
    _mock_http(monkeypatch, lambda req: httpx.Response(200, content=b"%PDF-" + b"x" * 2000))
    with pytest.raises(sources.NotSupported, match="over 20MB"):
        run(sources._download_pdf("https://example.org/big.pdf"))


def test_fetch_blog_hands_a_file_download_to_the_pdf_fetcher(monkeypatch):
    async def download(url, **kw):
        raise fetcher.IsDownload(url)

    async def fake_fetch_pdf(url):
        return sources.ResponseObject(url=url, text="pdf text")

    monkeypatch.setattr(fetcher, "render", download)
    monkeypatch.setattr(sources, "fetch_pdf", fake_fetch_pdf)
    ro = run(sources.fetch_blog("https://arxiv.org/pdf/1706.03762"))
    assert ro.text == "pdf text"
