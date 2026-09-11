"""Summarizer retry policy: 429 + transient 5xx back off, other errors don't."""
import pytest
from google.genai import errors as genai_errors

import summarize
from summarize import Summarizer


class FakeResp:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """Raises `errors` (one per call) before returning `text`.

    Mirrors the real client's `.models.generate_content(model=, contents=)`.
    """

    def __init__(self, errors, text="A summary."):
        self._errors = list(errors)
        self._text = text
        self.calls = 0
        self.models = self

    def generate_content(self, *, model, contents):
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return FakeResp(self._text)


def _server_error(code=503):
    return genai_errors.ServerError(
        code, {"error": {"code": code, "status": "UNAVAILABLE", "message": "high demand"}}
    )


def _client_error(code=400):
    return genai_errors.ClientError(
        code, {"error": {"code": code, "status": "INVALID_ARGUMENT", "message": "bad request"}}
    )


@pytest.fixture
def no_sleep(monkeypatch):
    """Record backoff delays instead of waiting them out."""
    slept = []
    monkeypatch.setattr(summarize.time, "sleep", slept.append)
    return slept


def test_retries_once_on_503_then_succeeds(no_sleep):
    client = FakeClient([_server_error(503)])
    s = Summarizer(client=client)

    assert s.summarize("body", title="T") == "A summary."
    assert client.calls == 2
    assert no_sleep == [2.0]


def test_persistent_503_reraises_after_max_retries(no_sleep):
    client = FakeClient([_server_error(503) for _ in range(10)])
    s = Summarizer(client=client)

    with pytest.raises(genai_errors.ServerError):
        s.summarize("body", max_retries=3)
    assert client.calls == 4  # initial attempt + 3 retries
    assert no_sleep == [2.0, 4.0, 8.0]  # bounded: no sleep after the last attempt


def test_retries_every_5xx_code(no_sleep):
    for code in (500, 502, 503, 504):
        client = FakeClient([_server_error(code)])
        assert Summarizer(client=client).summarize("body") == "A summary."
        assert client.calls == 2


def test_429_still_retries(no_sleep):
    client = FakeClient([_client_error(429)])
    s = Summarizer(client=client)

    assert s.summarize("body") == "A summary."
    assert client.calls == 2


def test_400_raises_immediately(no_sleep):
    client = FakeClient([_client_error(400)])
    s = Summarizer(client=client)

    with pytest.raises(genai_errors.ClientError):
        s.summarize("body")
    assert client.calls == 1
    assert no_sleep == []


def test_each_attempt_passes_the_rate_limiter(no_sleep):
    client = FakeClient([_server_error(503), _server_error(503)])
    s = Summarizer(client=client)
    original = s._limiter.acquire
    acquires = []

    def counting_acquire():
        acquires.append(1)
        original()

    s._limiter.acquire = counting_acquire

    s.summarize("body")
    assert len(acquires) == client.calls == 3
