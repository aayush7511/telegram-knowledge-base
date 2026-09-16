"""POST /jobs: blog and text branches — state machine, Telegram reply, graph
write, failure handling.

fetcher.render / summarizer / telegram.send_summary / graph.write_episode /
articles.store_article are mocked so the test is offline; post_status is
captured to assert the state progression.
"""
from fastapi.testclient import TestClient

import main
from extract import ResponseObject

HEADERS = {"X-KB-Secret": "s"}
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


def _wire(monkeypatch, *, render=None, write_episode=None):
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

    async def default_write_episode(job_id, **kw):
        episodes.append({"job_id": job_id, **kw})

    monkeypatch.setattr(main.graph, "write_episode", write_episode or default_write_episode)

    archived: dict = {}

    async def fake_store_article(job_id, text):
        archived[job_id] = text

    monkeypatch.setattr(main.articles, "store_article", fake_store_article)

    async def default_render(url, **kw):
        return "<html>body</html>"

    monkeypatch.setattr(main.fetcher, "render", render or default_render)
    monkeypatch.setattr(
        main, "extract_content",
        lambda html, url: ResponseObject(url=url, title="T", author="A", sitename="S", text="body"),
    )

    class FakeSummarizer:
        def summarize(self, text, title=None):
            return "SUMMARY"

    monkeypatch.setattr(main, "get_summarizer", lambda: FakeSummarizer())

    sent: dict = {}

    async def fake_send(chat_id, message_id, ro, token):
        sent.update(chat_id=chat_id, message_id=message_id, ro=ro, token=token)

    monkeypatch.setattr(main.telegram, "send_summary", fake_send)
    return states, sent, {"episodes": episodes, "summaries": summaries, "archived": archived}


def test_blog_happy_path(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    assert resp.json() == {"accepted": True, "job_id": "j1"}
    assert [s for s, _ in states] == ["fetching", "summarizing", "indexing", "saved"]
    assert sent["chat_id"] == 42 and sent["message_id"] == 7
    assert sent["ro"].summary == "SUMMARY"

    # graph episode: title + summary in the body, provenance in source_description
    [ep] = seen["episodes"]
    assert ep["job_id"] == "j1"
    assert ep["name"] == "T"
    assert ep["body"] == "T\n\nSUMMARY"
    assert ep["source_description"] == "blog: https://example.com/post | site: S | author: A"
    assert ep["reference_time"].isoformat() == "2026-09-16T10:00:00+00:00"
    # D1 gets the same text with the indexing status, so the graph is rebuildable
    assert seen["summaries"] == {"indexing": "T\n\nSUMMARY"}
    # the cleaned article text is archived before summarization
    assert seen["archived"] == {"j1": "body"}


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
    assert sent == {}  # no Telegram reply on failure
    assert seen["episodes"] == []


def test_blog_graph_failure_after_reply(monkeypatch):
    async def boom(job_id, **kw):
        raise RuntimeError("FalkorDB unreachable")

    states, sent, seen = _wire(monkeypatch, write_episode=boom)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    # the summary was already delivered; only the graph step is recorded as failed
    assert [s for s, _ in states] == ["fetching", "summarizing", "indexing", "failed"]
    assert "FalkorDB unreachable" in states[-1][1]
    assert sent["ro"].summary == "SUMMARY"
    assert seen["summaries"] == {"indexing": "T\n\nSUMMARY"}


def test_text_note_goes_straight_to_the_graph(monkeypatch):
    states, sent, seen = _wire(monkeypatch)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=TEXT_JOB)

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["indexing", "saved"]
    assert sent == {}  # no reply: the 👌 reaction is the acknowledgement
    [ep] = seen["episodes"]
    assert ep["job_id"] == "j2"
    assert ep["name"] == "Remember: FalkorDB runs on the e2-micro."
    assert ep["body"] == TEXT_JOB["text"]
    assert ep["source_description"] == "telegram text note"
    assert seen["summaries"] == {}  # the note is already in D1's text column


def test_text_note_graph_failure(monkeypatch):
    async def boom(job_id, **kw):
        raise RuntimeError("FalkorDB unreachable")

    states, _, _ = _wire(monkeypatch, write_episode=boom)
    resp = TestClient(main.app).post("/jobs", headers=HEADERS, json=TEXT_JOB)

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["indexing", "failed"]


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


def test_summarize_runs_off_the_event_loop(monkeypatch):
    """summarize() blocks (limiter sleeps + sync SDK); it must not stall the loop.

    Now that the pipeline runs inline in the request, a blocking call on the
    event-loop thread would freeze /health and every other in-flight request.
    """
    import threading

    _wire(monkeypatch)
    loop_thread = {}
    call_thread = {}

    class ThreadRecordingSummarizer:
        def summarize(self, text, title=None):
            call_thread["name"] = threading.current_thread().name
            return "SUMMARY"

    monkeypatch.setattr(main, "get_summarizer", lambda: ThreadRecordingSummarizer())

    async def record_render(url, **kw):
        loop_thread["name"] = threading.current_thread().name
        return "<html>body</html>"

    monkeypatch.setattr(main.fetcher, "render", record_render)

    TestClient(main.app).post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert call_thread["name"] != loop_thread["name"]


def test_bad_secret_rejected(monkeypatch):
    _wire(monkeypatch)
    client = TestClient(main.app)
    resp = client.post("/jobs", headers={"X-KB-Secret": "wrong"}, json=BLOG_JOB)
    assert resp.status_code == 401
