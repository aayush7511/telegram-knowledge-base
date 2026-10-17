"""YouTube via the home worker — specs/youtube-home-worker.md, Cloud Run side.

POST /jobs for a YouTube link, end to end through main: the home worker,
Supadata, oEmbed and Worker 2's /retry are all served by one httpx
MockTransport (offline), so a test sees every outbound call. Graph, archive,
summarizer, Telegram and post_status are mocked as in test_jobs.
"""
import functools
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import main
import sources
from test_jobs import HEADERS, _wire

CAPTIONS = "caption " * 300  # long enough to be summarized
YT_URL = "https://youtu.be/zjkBMFhNj_g"
YT_JOB = {
    "job_id": "y1",
    "content_type": "url",
    "url_source": "youtube",
    "url": YT_URL,
    "chat_id": 42,
    "message_id": 9,
    "time_received": "2026-10-10T15:00:00.000Z",
}
WORKER = "https://yt-worker.test"
RETRY_URL = "https://kb-forward.test/retry"
NOON_CHICAGO = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)  # 12:00 CDT


def _skip(reason):
    return f"Skipped (not ingestible):\n• {YT_URL} — {reason}"


def _youtube(monkeypatch, worker=None, *, retry=None, worker_url=WORKER, now=NOON_CHICAGO):
    """Wire main for a YouTube job. `worker(request)` answers the home worker;
    `retry(request)` answers Worker 2's /retry. Returns (states, seen, calls)."""
    states, sent, seen = _wire(monkeypatch)
    seen["sent"] = sent
    if worker_url:
        monkeypatch.setenv("YT_WORKER_URL", worker_url)
    else:
        monkeypatch.delenv("YT_WORKER_URL", raising=False)
    monkeypatch.setenv("YT_WORKER_SECRET", "yt-secret")
    monkeypatch.setenv("SUPADATA_API_KEY", "sd-key")
    monkeypatch.setenv("WORKER2_RETRY_URL", RETRY_URL)
    monkeypatch.setenv("WORKER2_SHARED_SECRET", "w2-secret")
    monkeypatch.setattr(main, "utcnow", lambda: now)

    calls: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.host == "yt-worker.test":
            return worker(req)
        if req.url.host == "api.supadata.ai":
            return httpx.Response(200, json={"content": "supadata " * 300, "lang": "en"})
        if req.url.path == "/oembed":
            return httpx.Response(200, json={"title": "LLM intro", "author_name": "Andrej"})
        if str(req.url) == RETRY_URL:
            return (retry or (lambda r: httpx.Response(200, json={"ok": True})))(req)
        return httpx.Response(599)

    monkeypatch.setattr(httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handle)))
    return states, seen, calls


def _hosts(calls):
    return [c.url.host for c in calls]


def _retry_calls(calls):
    return [c for c in calls if str(c.url) == RETRY_URL]


def _ok(is_generated=False):
    return lambda req: httpx.Response(200, json={
        "status": "ok", "text": CAPTIONS, "language": "en", "is_generated": is_generated,
    })


def _status(value):
    return lambda req: httpx.Response(200, json={"status": value})


def _post(job=YT_JOB):
    return TestClient(main.app).post("/jobs", headers=HEADERS, json=job)


# --- 1, 2: captions from the worker, no Supadata ---------------------------

@pytest.mark.parametrize("is_generated", [False, True])
def test_worker_captions_are_used_without_supadata(monkeypatch, is_generated):
    states, seen, calls = _youtube(monkeypatch, _ok(is_generated))
    assert _post().status_code == 200
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]
    assert "api.supadata.ai" not in _hosts(calls)
    assert seen["archived"] == {"y1": CAPTIONS}
    assert seen["replies"][0]["ro"].title == "LLM intro"


def test_worker_request_carries_video_id_and_its_own_secret(monkeypatch):
    _, _, calls = _youtube(monkeypatch, _ok())
    _post()
    [req] = [c for c in calls if c.url.host == "yt-worker.test"]
    assert req.method == "POST" and req.url.path == "/transcript"
    assert req.headers["X-KB-Secret"] == "yt-secret"
    assert httpx.Response(200, content=req.content).json() == {"video_id": "zjkBMFhNj_g"}


def test_worker_timeout_is_30_seconds():
    assert sources.YT_WORKER_TIMEOUT_S == 30


# --- 3, 4: no captions (incl. other languages only) -------------------------

def test_no_captions_replies_right_away_without_supadata(monkeypatch):
    states, seen, calls = _youtube(monkeypatch, _status("no_captions"))
    _post()
    assert [s for s, _ in states] == ["fetching", "failed"]
    assert [t["text"] for t in seen["texts"]] == [_skip("No captions")]
    assert "api.supadata.ai" not in _hosts(calls)
    assert _retry_calls(calls) == []


# --- 5: blocked → Supadata --------------------------------------------------

def test_blocked_falls_back_to_supadata(monkeypatch):
    states, seen, calls = _youtube(monkeypatch, _status("blocked"))
    _post()
    assert "api.supadata.ai" in _hosts(calls)
    assert [s for s, _ in states][-1] == "saved"


# --- 6: private / deleted ---------------------------------------------------

def test_unavailable_video_fails_without_retry(monkeypatch):
    states, seen, calls = _youtube(monkeypatch, _status("unavailable"))
    _post()
    assert [s for s, _ in states] == ["fetching", "failed"]
    assert [t["text"] for t in seen["texts"]] == [_skip("Unavailable at the moment")]
    assert "api.supadata.ai" not in _hosts(calls)
    assert _retry_calls(calls) == []


# --- 7: worker rejects the secret -------------------------------------------

def test_rejected_secret_is_some_error(monkeypatch):
    states, seen, calls = _youtube(monkeypatch, lambda req: httpx.Response(401))
    _post()
    assert [s for s, _ in states] == ["fetching", "failed"]
    assert [t["text"] for t in seen["texts"]] == [_skip("There was some error")]
    assert "api.supadata.ai" not in _hosts(calls)
    assert _retry_calls(calls) == []


# --- 8: worker unreachable → retrying ---------------------------------------

def _connect_error(req):
    raise httpx.ConnectError("connection refused", request=req)


def _timeout(req):
    raise httpx.ReadTimeout("no answer", request=req)


@pytest.mark.parametrize("worker", [
    _connect_error,
    _timeout,
    lambda req: httpx.Response(502, text="tailscale: no backend"),
    lambda req: httpx.Response(500),
], ids=["connect-error", "timeout", "502", "500"])
def test_unreachable_worker_starts_the_retry_flow(monkeypatch, worker):
    states, seen, calls = _youtube(monkeypatch, worker)
    _post()
    assert [s for s, _ in states] == ["fetching", "retrying"]
    assert [t["text"] for t in seen["texts"]] == [_skip("Unavailable at the moment, I'll try again later")]
    assert "api.supadata.ai" not in _hosts(calls)
    [req] = _retry_calls(calls)
    assert req.headers["X-KB-Secret"] == "w2-secret"
    assert httpx.Response(200, content=req.content).json() == {"job_id": "y1", "delay_seconds": 3600}


# --- 9, 10: the 6 a.m.–midnight Chicago window -------------------------------

@pytest.mark.parametrize("now, delay", [
    (datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc), 3600),    # 12:00 CDT → 13:00
    (datetime(2026, 10, 11, 3, 59, tzinfo=timezone.utc), 3600),    # 22:59 CDT → 23:59
    (datetime(2026, 10, 11, 4, 30, tzinfo=timezone.utc), 23400),   # 23:30 CDT → 06:00, not 00:30
    (datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc), 14400),    # 02:00 CDT → 06:00 (03:00 is out)
    (datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc), 3600),    # 05:00 CDT → 06:00 exactly
    (datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc), 27000),    # 23:30 CDT Oct 31 → 06:00 CST Nov 1
    (datetime(2026, 11, 2, 5, 30, tzinfo=timezone.utc), 23400),    # 23:30 CST → 06:00 CST
])
def test_retry_delay_stays_inside_the_chicago_window(now, delay):
    assert main.retry_delay_seconds(now) == delay


def test_late_night_failure_schedules_the_retry_for_6am(monkeypatch):
    late = datetime(2026, 10, 11, 4, 30, tzinfo=timezone.utc)  # 23:30 CDT
    _, _, calls = _youtube(monkeypatch, _connect_error, now=late)
    _post()
    [req] = _retry_calls(calls)
    assert httpx.Response(200, content=req.content).json()["delay_seconds"] == 23400


# --- 13, 14: later retries --------------------------------------------------

@pytest.mark.parametrize("retry_count", [1, 2])
def test_failed_retries_send_no_message_and_schedule_the_next(monkeypatch, retry_count):
    states, seen, calls = _youtube(monkeypatch, _connect_error)
    _post({**YT_JOB, "retry_count": retry_count})
    assert [s for s, _ in states] == ["fetching", "retrying"]
    assert seen["texts"] == []
    assert len(_retry_calls(calls)) == 1


def test_third_failed_retry_gives_up(monkeypatch):
    states, seen, calls = _youtube(monkeypatch, _connect_error)
    _post({**YT_JOB, "retry_count": 3})
    assert [s for s, _ in states] == ["fetching", "failed"]
    assert [t["text"] for t in seen["texts"]] == [_skip("Unable to get captions")]
    assert _retry_calls(calls) == []


def test_a_retried_job_that_reaches_the_worker_is_saved(monkeypatch):
    states, seen, calls = _youtube(monkeypatch, _ok())
    _post({**YT_JOB, "retry_count": 2})
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]
    assert seen["texts"] == []


# --- 15: /retry itself fails ------------------------------------------------

@pytest.mark.parametrize("retry", [
    lambda req: httpx.Response(503),
    _connect_error,
], ids=["503", "connect-error"])
def test_retry_endpoint_is_tried_three_times_then_the_job_fails(monkeypatch, retry):
    states, seen, calls = _youtube(monkeypatch, _connect_error, retry=retry)
    _post()
    assert len(_retry_calls(calls)) == 3
    assert [s for s, _ in states][-1] == "failed"


def test_retry_endpoint_succeeding_on_the_second_try(monkeypatch):
    replies = iter([httpx.Response(503), httpx.Response(200, json={"ok": True})])
    states, seen, calls = _youtube(monkeypatch, _connect_error, retry=lambda req: next(replies))
    _post()
    assert len(_retry_calls(calls)) == 2
    assert [s for s, _ in states] == ["fetching", "retrying"]


# --- 17: worker not set up --------------------------------------------------

def test_no_worker_url_is_a_setup_mistake(monkeypatch):
    states, seen, calls = _youtube(monkeypatch, _ok(), worker_url=None)
    _post()
    assert [s for s, _ in states] == ["fetching", "failed"]
    assert [t["text"] for t in seen["texts"]] == [_skip("There was some error")]
    assert "yt-worker.test" not in _hosts(calls)
    assert "api.supadata.ai" not in _hosts(calls)
    assert _retry_calls(calls) == []
