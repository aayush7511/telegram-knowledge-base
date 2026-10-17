"""POST /jobs: URL and text branches — state machine, Telegram reply, graph
write, failure handling.

fetcher.render / extract_content / summarizer / telegram / graph.write_episode
/ articles.store_article are mocked so the test is offline; post_status is
captured to assert the state progression. telegram.format_extraction_reply is
replaced by a recorder, so these tests cover the wiring around the reply, not
its text (that's test_extraction_reply.py).
"""
from fastapi.testclient import TestClient

import main
from extract import ResponseObject

HEADERS = {"X-KB-Secret": "s"}
# Long enough to pass the article-text minimum (sources.MIN_ARTICLE_CHARS).
ARTICLE = "body " * 400
EXTRACTED = main.graph.Extracted(entities=["Zep", "Graphiti"], facts=["Zep built Graphiti."])
BLOG_JOB = {
    "job_id": "j1",
    "content_type": "url",
    "url_source": "blog",
    "url": "https://example.com/post",
    "chat_id": 42,
    "message_id": 7,
    "time_received": "2026-09-16T10:00:00.000Z",
}
TEXT_JOB = {
    "job_id": "j2",
    "content_type": "text",
    "text": "Remember: FalkorDB runs on the e2-micro.\nSecond line.",
    "chat_id": 42,
    "message_id": 8,
    "time_received": "2026-09-16T10:00:00.000Z",
}


def _wire(monkeypatch, *, render=None, write_episode=None, text=ARTICLE):
    monkeypatch.setenv("KB_SHARED_SECRET", "s")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")

    states: list[tuple[str, str | None]] = []
    summaries: dict[str, str] = {}

    async def fake_status(job_id, state, r2_key=None, error=None, summary=None):
        states.append((state, error))
        if summary is not None:
            summaries[state] = summary

    monkeypatch.setattr(main, "post_status", fake_status)

    episodes: list[dict] = []
    events: list[str] = []  # graph writes and replies, in order

    async def default_write_episode(job_id, **kw):
        episodes.append({"job_id": job_id, **kw})
        events.append("graph")
        return EXTRACTED

    monkeypatch.setattr(main.graph, "write_episode", write_episode or default_write_episode)

    archived: dict = {}

    async def fake_store_article(job_id, text):
        archived[job_id] = text

    monkeypatch.setattr(main.articles, "store_article", fake_store_article)

    async def default_render(url, **kw):
        return "<html>body</html>"

    monkeypatch.setattr(main.sources.fetcher, "render", render or default_render)
    monkeypatch.setattr(
        main.sources.extract, "extract_content",
        lambda html, url: ResponseObject(url=url, title="T", author="A", sitename="S", text=text),
    )

    summarize_calls: list[str] = []

    class FakeSummarizer:
        def summarize(self, text, title=None):
            summarize_calls.append(text)
            return "SUMMARY"

    monkeypatch.setattr(main, "get_summarizer", lambda: FakeSummarizer())

    replies: list[dict] = []

    def fake_format(ro, entities, facts):
        replies.append({"ro": ro, "entities": entities, "facts": facts})
        return "REPLY"

    monkeypatch.setattr(main.telegram, "format_extraction_reply", fake_format)

    htmls: list[dict] = []

    async def fake_send_html(chat_id, message_id, text, token):
        htmls.append({"chat_id": chat_id, "message_id": message_id, "text": text})
        events.append("reply")

    monkeypatch.setattr(main.telegram, "send_html", fake_send_html)

    sent: dict = {}

    async def fake_send(chat_id, message_id, ro, token):
        sent.update(chat_id=chat_id, message_id=message_id, ro=ro, token=token)

    monkeypatch.setattr(main.telegram, "send_summary", fake_send)

    texts: list[dict] = []

    async def fake_send_text(chat_id, message_id, text, token):
        texts.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    monkeypatch.setattr(main.telegram, "send_text", fake_send_text)
    return states, sent, {
        "episodes": episodes, "summaries": summaries, "archived": archived, "texts": texts,
        "replies": replies, "htmls": htmls, "events": events, "summarize_calls": summarize_calls,
    }


def test_blog_happy_path(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    assert resp.json() == {"accepted": True, "job_id": "j1"}
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]
    # the reply lists what the graph write extracted, with the item as header
    [reply] = seen["replies"]
    assert reply["ro"].title == "T"
    assert (reply["entities"], reply["facts"]) == (EXTRACTED.entities, EXTRACTED.facts)
    assert seen["htmls"] == [{"chat_id": 42, "message_id": 7, "text": "REPLY"}]
    assert sent == {}  # the old summary reply is gone

    # graph episode: title + full cleaned article text in the body, provenance
    # in source_description
    [ep] = seen["episodes"]
    assert ep["job_id"] == "j1"
    assert ep["name"] == "T"
    assert ep["body"] == f"T\n\n{ARTICLE}"
    assert ep["source_description"] == "blog: https://example.com/post | site: S | author: A"
    assert ep["reference_time"].isoformat() == "2026-09-16T10:00:00+00:00"
    # D1 gets the same text with the indexing status, so the graph is rebuildable
    assert seen["summaries"] == {"indexing": f"T\n\n{ARTICLE}"}
    # the cleaned article text is still archived
    assert seen["archived"] == {"j1": ARTICLE}


def test_blog_failure_marks_failed_and_skips_reply(monkeypatch):
    async def boom(url, **kw):
        raise RuntimeError("dead url")

    states, sent, seen = _wire(monkeypatch, render=boom)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=BLOG_JOB)

    # 2xx even on failure: outcome is terminal in D1, so Worker 2 should ack
    # rather than replay an identical, expensive failure.
    assert resp.status_code == 200
    assert [s for s, _ in states] == ["fetching", "failed"]
    assert "dead url" in states[-1][1]
    assert sent == {} and seen["htmls"] == []  # no Telegram reply on failure
    assert seen["texts"] == []  # a broken fetch isn't "not supported"
    assert seen["episodes"] == []


def test_blog_page_with_too_little_text_is_not_supported(monkeypatch):
    states, sent, seen = _wire(monkeypatch, text="Please log in to continue.")
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    assert states == [("fetching", None), ("failed", "not supported: no article text found")]
    [reply] = seen["texts"]
    assert reply["chat_id"] == 42 and reply["message_id"] == 7
    assert reply["text"] == "Skipped (not ingestible):\n• https://example.com/post — no article text found"
    # nothing kept: no archive, no summary reply, no graph write
    assert seen["archived"] == {}
    assert sent == {}
    assert seen["episodes"] == []


def test_blog_http_error_is_not_supported(monkeypatch):
    async def blocked(url, **kw):
        raise main.sources.fetcher.PageBlocked(403)

    states, sent, seen = _wire(monkeypatch, render=blocked)
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    assert states == [("fetching", None), ("failed", "not supported: the site returned HTTP 403")]
    [reply] = seen["texts"]
    assert reply["text"].endswith("— the site returned HTTP 403")
    assert seen["archived"] == {} and sent == {} and seen["episodes"] == []


def test_graph_failure_replies_couldnt_save(monkeypatch):
    async def boom(job_id, **kw):
        raise RuntimeError("FalkorDB unreachable")

    states, sent, seen = _wire(monkeypatch, write_episode=boom)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["fetching", "indexing", "failed"]
    assert "FalkorDB unreachable" in states[-1][1]
    assert [t["text"] for t in seen["texts"]] == ["Couldn't save this to memory"]
    assert seen["htmls"] == []
    # D1 still has the episode text, so the job can be re-driven
    assert seen["summaries"] == {"indexing": f"T\n\n{ARTICLE}"}


def test_short_item_gets_the_reply_too(monkeypatch):
    """A short item (a post, a one-paragraph answer) gets the same reply as an article."""
    states, sent, seen = _wire(monkeypatch)

    async def fetch_post(url):
        return ResponseObject(url=url, title=None, author="karpathy", text="A short post.")

    monkeypatch.setitem(main.sources.FETCHERS, "x", fetch_post)
    job = {**BLOG_JOB, "url_source": "x", "url": "https://x.com/karpathy/status/1"}
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=job)

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]
    assert len(seen["htmls"]) == 1 and seen["texts"] == []
    [ep] = seen["episodes"]
    assert ep["name"] == "https://x.com/karpathy/status/1"  # no title → the url
    assert ep["body"] == "A short post."
    assert ep["source_description"] == "x: https://x.com/karpathy/status/1 | author: karpathy"
    assert seen["archived"] == {"j1": "A short post."}


def test_url_source_without_a_fetcher_is_not_supported_yet(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    job = {**BLOG_JOB, "url_source": "reddit", "url": "https://redd.it/1abc2de"}
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=job)

    assert resp.status_code == 200
    assert states == [("failed", "not supported: reddit links aren't supported yet")]
    [reply] = seen["texts"]
    assert reply["text"] == "Skipped (not ingestible):\n• https://redd.it/1abc2de — reddit links aren't supported yet"
    assert seen["episodes"] == []


PDF_FILE_JOB = {
    "job_id": "j4",
    "content_type": "document",
    "media": {"r2_key": "raw-media/j4.pdf", "mime_type": "application/pdf"},
    "chat_id": 42,
    "message_id": 9,
    "time_received": "2026-09-16T10:00:00.000Z",
}


def test_pdf_file_runs_the_shared_pipeline(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    keys = []

    async def fake_pdf_file(r2_key):
        keys.append(r2_key)
        return ResponseObject(url="Telegram file", title=None, sitename="Telegram", text=ARTICLE)

    monkeypatch.setattr(main.sources, "fetch_pdf_file", fake_pdf_file)
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=PDF_FILE_JOB)

    assert resp.status_code == 200
    assert keys == ["raw-media/j4.pdf"]
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]
    assert len(seen["htmls"]) == 1
    [ep] = seen["episodes"]
    assert ep["name"] == "your PDF"  # no title → the reply target
    assert ep["source_description"] == "pdf: Telegram file | site: Telegram"


def test_scanned_pdf_file_is_not_supported(monkeypatch):
    states, sent, seen = _wire(monkeypatch)

    async def scanned(r2_key):
        raise main.sources.NotSupported("the PDF has no text layer (scanned?) — OCR isn't supported")

    monkeypatch.setattr(main.sources, "fetch_pdf_file", scanned)
    TestClient(main.app).post("/jobs", headers=HEADERS, json=PDF_FILE_JOB)

    assert [s for s, _ in states] == ["fetching", "failed"]
    [reply] = seen["texts"]
    assert reply["text"].startswith("Skipped (not ingestible):\n• your PDF — the PDF has no text layer")


def test_other_documents_are_not_supported(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    job = {**PDF_FILE_JOB, "media": {"r2_key": "raw-media/j4.docx", "mime_type": "application/msword"}}
    TestClient(main.app).post("/jobs", headers=HEADERS, json=job)

    assert states == [("failed", "not supported: only PDF files are supported")]
    assert seen["texts"][0]["text"] == "Skipped (not ingestible):\n• your file — only PDF files are supported"


def test_text_job_replies(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=TEXT_JOB)

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["indexing", "saved"]
    # a text note gets the reply too, with no header
    [reply] = seen["replies"]
    assert reply["ro"] is None and reply["entities"] == EXTRACTED.entities
    assert seen["htmls"] == [{"chat_id": 42, "message_id": 8, "text": "REPLY"}]
    assert seen["events"] == ["graph", "reply"]
    [ep] = seen["episodes"]
    assert ep["job_id"] == "j2"
    assert ep["name"] == "Remember: FalkorDB runs on the e2-micro."
    assert ep["body"] == TEXT_JOB["text"]
    assert ep["source_description"] == "telegram text note"
    assert seen["summaries"] == {}  # the note is already in D1's text column


def test_text_note_graph_failure(monkeypatch):
    async def boom(job_id, **kw):
        raise RuntimeError("FalkorDB unreachable")

    states, _, seen = _wire(monkeypatch, write_episode=boom)
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=TEXT_JOB)

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["indexing", "failed"]
    assert [t["text"] for t in seen["texts"]] == ["Couldn't save this to memory"]


def test_other_content_types_use_stub(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    client = TestClient(main.app)

    resp = client.post(
        "/jobs", headers=HEADERS,
        json={"job_id": "j3", "content_type": "voice", "media": {"r2_key": "raw-media/j3.ogg"}},
    )

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["summarizing"]
    assert sent == {}
    assert seen["episodes"] == []


def test_url_job_skips_summarizing_and_replies_after_indexing(monkeypatch):
    states, _, seen = _wire(monkeypatch)

    TestClient(main.app).post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert seen["summarize_calls"] == []  # no Gemini call
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]
    assert seen["events"] == ["graph", "reply"]


def test_reply_send_failure_still_saved(monkeypatch):
    states, _, seen = _wire(monkeypatch)

    async def broken_send(chat_id, message_id, text, token):
        raise main.httpx.ConnectError("telegram down")

    monkeypatch.setattr(main.telegram, "send_html", broken_send)
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]


def test_bad_secret_rejected(monkeypatch):
    _wire(monkeypatch)
    client = TestClient(main.app)
    resp = client.post("/jobs", headers={"X-KB-Secret": "wrong"}, json=BLOG_JOB)
    assert resp.status_code == 401
