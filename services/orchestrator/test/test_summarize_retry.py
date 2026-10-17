"""Retry summarizing later when Gemini is overloaded — specs/summarize-retry.md.

Summarizing was dropped by specs/extraction-reply.md, so the Gemini-overload
tests are skipped (removed with the Gemini code later), and a retry now always
re-fetches. The archive tests still apply: the archive is still written.

POST /jobs for a blog link through main, wired as in test_jobs; Worker 2's
/retry is served by an httpx MockTransport so a test sees every call to it.
"""
import asyncio
import functools
import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import articles
import main
import summarize
from extract import ResponseObject
from test_jobs import ARTICLE, BLOG_JOB, HEADERS, _wire

RETRY_URL = "https://kb-forward.test/retry"
NO_SUMMARIZING = pytest.mark.skip(reason="summarizing dropped — specs/extraction-reply.md")
NOON_CHICAGO = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)  # 12:00 CDT
URL = BLOG_JOB["url"]
ARCHIVED = ResponseObject(url=URL, title="Archived T", author="AA", sitename="AS", text=ARTICLE)


def _skip(reason):
    return f"Skipped (not ingestible):\n• {URL} — {reason}"


class _Summarizer:
    """Raises the queued errors in order, then returns a summary."""

    def __init__(self, errors):
        self.errors = list(errors)
        self.titles = []

    def summarize(self, text, title=None):
        self.titles.append(title)
        if self.errors:
            raise self.errors.pop(0)
        return "SUMMARY"


def _overloaded(code=503):
    return summarize.Overloaded(f"gemini {code}")


def _setup(monkeypatch, errors=(), *, archive=None, retry=None):
    """Wire main for a blog job whose summarizer raises `errors` first.
    `archive` is what load_archive returns. Returns (states, sent, seen, calls)."""
    states, sent, seen = _wire(monkeypatch)
    monkeypatch.setenv("WORKER2_RETRY_URL", RETRY_URL)
    monkeypatch.setenv("WORKER2_SHARED_SECRET", "w2-secret")
    monkeypatch.setattr(main, "utcnow", lambda: NOON_CHICAGO)

    summarizer = _Summarizer(errors)
    monkeypatch.setattr(main, "get_summarizer", lambda: summarizer)
    seen["summarizer"] = summarizer

    meta: dict = {}

    async def fake_store_meta(job_id, ro):
        meta[job_id] = ro

    monkeypatch.setattr(main.articles, "store_meta", fake_store_meta)
    seen["meta"] = meta

    loads: list[str] = []

    async def fake_load_archive(job_id):
        loads.append(job_id)
        return archive

    monkeypatch.setattr(main.articles, "load_archive", fake_load_archive)
    seen["loads"] = loads

    renders: list[str] = []

    async def counting_render(url, **kw):
        renders.append(url)
        return "<html>body</html>"

    monkeypatch.setattr(main.sources.fetcher, "render", counting_render)
    seen["renders"] = renders

    calls: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if str(req.url) == RETRY_URL:
            return (retry or (lambda r: httpx.Response(200, json={"ok": True})))(req)
        return httpx.Response(599)

    monkeypatch.setattr(httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handle)))
    return states, sent, seen, calls


def _retry_bodies(calls):
    return [json.loads(c.content) for c in calls if str(c.url) == RETRY_URL]


def _post(job=BLOG_JOB):
    return TestClient(main.app).post("/jobs", headers=HEADERS, json=job)


# --- 1: fetch archives text and metadata -----------------------------------

def test_fetch_archives_text_and_metadata(monkeypatch):
    states, sent, seen, _ = _setup(monkeypatch)
    _post()
    assert seen["archived"] == {BLOG_JOB["job_id"]: ARTICLE}
    ro = seen["meta"][BLOG_JOB["job_id"]]
    assert (ro.url, ro.title, ro.author, ro.sitename) == (URL, "T", "A", "S")


# --- 2, 3: overloaded after the in-request backoff → retrying --------------

@NO_SUMMARIZING
@pytest.mark.parametrize("code", [503, 429])
def test_overload_moves_to_retrying_and_schedules_a_retry(monkeypatch, code):
    states, sent, seen, calls = _setup(monkeypatch, [_overloaded(code)])
    assert _post().status_code == 200
    assert [s for s, _ in states] == ["fetching", "summarizing", "retrying"]
    assert _retry_bodies(calls) == [{"job_id": BLOG_JOB["job_id"], "delay_seconds": 3600}]
    assert [t["text"] for t in seen["texts"]] == [_skip("Unavailable at the moment, I'll try again later")]
    assert sent == {}
    assert seen["episodes"] == []


# --- 4: other summarize errors fail right away -----------------------------

@NO_SUMMARIZING
def test_non_transient_summarize_error_fails_without_retry(monkeypatch):
    states, _, seen, calls = _setup(monkeypatch, [ValueError("400 INVALID_ARGUMENT")])
    _post()
    assert [s for s, _ in states] == ["fetching", "summarizing", "failed"]
    assert _retry_bodies(calls) == []
    assert seen["texts"] == []


# --- 5, 6: later retries ----------------------------------------------------

@NO_SUMMARIZING
@pytest.mark.parametrize("retry_count", [1, 2])
def test_later_overloads_are_silent_and_schedule_the_next(monkeypatch, retry_count):
    states, _, seen, calls = _setup(monkeypatch, [_overloaded()], archive=ARCHIVED)
    _post({**BLOG_JOB, "retry_count": retry_count})
    assert [s for s, _ in states] == ["summarizing", "retrying"]
    assert len(_retry_bodies(calls)) == 1
    assert seen["texts"] == []


@NO_SUMMARIZING
def test_third_retry_still_overloaded_gives_up(monkeypatch):
    states, _, seen, calls = _setup(monkeypatch, [_overloaded()], archive=ARCHIVED)
    _post({**BLOG_JOB, "retry_count": 3})
    assert [s for s, _ in states] == ["summarizing", "failed"]
    assert _retry_bodies(calls) == []
    assert [t["text"] for t in seen["texts"]] == [_skip("Couldn't summarize it, please send it again later")]


# --- 7: /retry itself fails -------------------------------------------------

@NO_SUMMARIZING
def test_retry_endpoint_failing_three_times_fails_the_job(monkeypatch):
    states, _, _, calls = _setup(monkeypatch, [_overloaded()], retry=lambda r: httpx.Response(503))
    _post()
    assert len(_retry_bodies(calls)) == 3
    assert [s for s, _ in states][-1] == "failed"


# --- 8, 9: a retry re-fetches, archive or not (specs/extraction-reply.md) ----

@pytest.mark.parametrize("archive", [ARCHIVED, None])
def test_retry_refetches_even_with_an_archive(monkeypatch, archive):
    states, _, seen, _ = _setup(monkeypatch, archive=archive)
    _post({**BLOG_JOB, "retry_count": 1})
    assert [s for s, _ in states] == ["fetching", "indexing", "saved"]
    assert seen["renders"] == [URL]
    assert seen["loads"] == []
    assert seen["episodes"][0]["name"] == "T"


# --- 10: first delivery never resumes --------------------------------------

def test_first_delivery_fetches_even_if_an_archive_exists(monkeypatch):
    states, _, seen, _ = _setup(monkeypatch, archive=ARCHIVED)
    _post()
    assert [s for s, _ in states][0] == "fetching"
    assert seen["renders"] == [URL]
    assert seen["loads"] == []


# --- archive round trip in R2 (supports 1, 8, 9) ----------------------------

class _FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": type("B", (), {"read": lambda _s, b=self.objects[Key]: b})()}


@pytest.fixture
def s3(monkeypatch):
    fake = _FakeS3()
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setattr(articles, "_client", lambda: fake)
    return fake


def _store(ro):
    asyncio.run(articles.store_article("j1", ro.text))
    asyncio.run(articles.store_meta("j1", ro))


def test_archive_round_trip(s3):
    _store(ResponseObject(url=URL, title="T", author="A", sitename="S", text=ARTICLE, summary="x"))
    assert json.loads(s3.objects["articles/j1.json"]) == {"url": URL, "title": "T", "author": "A", "sitename": "S"}
    loaded = asyncio.run(articles.load_archive("j1"))
    assert (loaded.url, loaded.title, loaded.author, loaded.sitename, loaded.text) == (URL, "T", "A", "S", ARTICLE)


@pytest.mark.parametrize("missing", ["articles/j1.txt", "articles/j1.json"])
def test_load_archive_is_none_when_either_object_is_missing(s3, missing):
    _store(ResponseObject(url=URL, title="T", text=ARTICLE))
    del s3.objects[missing]
    assert asyncio.run(articles.load_archive("j1")) is None


def test_load_archive_is_none_without_r2(monkeypatch):
    monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
    assert asyncio.run(articles.load_archive("j1")) is None
