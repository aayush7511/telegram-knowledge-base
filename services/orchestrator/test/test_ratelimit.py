"""RateLimiter enforces at most N acquisitions per window."""
import time

import pytest

from summarize import RateLimiter


def test_first_n_acquire_immediately_then_sixth_blocks():
    rl = RateLimiter(max_calls=5, window=0.5)

    start = time.monotonic()
    for _ in range(5):
        rl.acquire()
    assert time.monotonic() - start < 0.3  # first 5 are ~instant

    rl.acquire()  # 6th must wait for the window to roll over
    assert time.monotonic() - start >= 0.5


class _FlakyModels:
    """Raises the queued errors in order, then returns a canned summary."""

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def generate_content(self, model, contents):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return type("Resp", (), {"text": " summary "})()


def _summarizer(errors, monkeypatch):
    import summarize
    from summarize import Summarizer

    monkeypatch.setattr(summarize.time, "sleep", lambda _s: None)
    models = _FlakyModels(errors)
    client = type("Client", (), {"models": models})()
    return Summarizer(client=client, max_rpm=100), models


def test_summarize_retries_gemini_503_high_demand(monkeypatch):
    from google.genai import errors

    overloaded = errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})
    s, models = _summarizer([overloaded, overloaded], monkeypatch)

    assert s.summarize("article text") == "summary"
    assert models.calls == 3


def test_summarize_does_not_retry_non_transient_errors(monkeypatch):
    import pytest
    from google.genai import errors

    bad_request = errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}})
    s, models = _summarizer([bad_request], monkeypatch)

    with pytest.raises(errors.ClientError):
        s.summarize("article text")
    assert models.calls == 1


@pytest.mark.parametrize("code", [503, 429])
def test_summarize_raises_overloaded_once_backoff_runs_out(monkeypatch, code):
    from google.genai import errors
    from summarize import Overloaded

    cls = errors.ServerError if code >= 500 else errors.ClientError
    err = cls(code, {"error": {"code": code, "status": "UNAVAILABLE"}})
    s, models = _summarizer([err] * 5, monkeypatch)

    with pytest.raises(Overloaded):
        s.summarize("article text")
    assert models.calls == 5
