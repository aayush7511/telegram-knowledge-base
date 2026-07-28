"""POST /jobs blog branch: state machine, Telegram reply, failure handling.

fetcher.render / summarizer / telegram.send_summary are mocked so the test is
offline; post_status is captured to assert the state progression.
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
}


def _wire(monkeypatch, *, render=None):
    monkeypatch.setenv("KB_SHARED_SECRET", "s")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")

    states: list[tuple[str, str | None]] = []

    async def fake_status(job_id, state, r2_key=None, error=None):
        states.append((state, error))

    monkeypatch.setattr(main, "post_status", fake_status)

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
    return states, sent


def test_blog_happy_path(monkeypatch):
    states, sent = _wire(monkeypatch)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=BLOG_JOB)

    assert resp.status_code == 200
    assert resp.json() == {"accepted": True, "job_id": "j1"}
    assert [s for s, _ in states] == ["fetching", "summarizing", "saved"]
    assert sent["chat_id"] == 42 and sent["message_id"] == 7
    assert sent["ro"].summary == "SUMMARY"


def test_blog_failure_marks_failed_and_skips_reply(monkeypatch):
    async def boom(url, **kw):
        raise RuntimeError("dead url")

    states, sent = _wire(monkeypatch, render=boom)
    client = TestClient(main.app)

    resp = client.post("/jobs", headers=HEADERS, json=BLOG_JOB)

    # 2xx even on failure: outcome is terminal in D1, so Worker 2 should ack
    # rather than replay an identical, expensive failure.
    assert resp.status_code == 200
    assert [s for s, _ in states] == ["fetching", "failed"]
    assert "dead url" in states[-1][1]
    assert sent == {}  # no Telegram reply on failure


def test_non_blog_job_uses_stub(monkeypatch):
    states, sent = _wire(monkeypatch)
    client = TestClient(main.app)

    resp = client.post(
        "/jobs", headers=HEADERS,
        json={"job_id": "j2", "content_type": "text", "text": "hi"},
    )

    assert resp.status_code == 200
    assert [s for s, _ in states] == ["summarizing"]
    assert sent == {}


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
