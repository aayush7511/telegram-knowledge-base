"""Gemini 2.5 Flash summarizer with a client-side rate limit.

The project runs on Gemini's free tier, currently estimated at ~5 requests/
minute, so every call passes through an in-memory sliding-window limiter. This
is sufficient because Cloud Run runs the orchestrator at `--max-instances 1` —
there is never a second process to coordinate with. HTTP 429s (should the
estimate be wrong, or on a burst) get exponential-backoff retries.
"""
from __future__ import annotations

import logging
import threading
import time

from google import genai
from google.genai import errors as genai_errors

log = logging.getLogger("kb-orchestrator.summarize")

# gemini-2.5-flash was the original pick but is closed to new API users
# ("no longer available to new users", 404 at generateContent) — verified live
# 2026-07-27. Pinned to a specific version rather than the `gemini-flash-latest`
# alias so the model can't change under a rate budget tuned to one model.
MODEL = "gemini-3.6-flash"
MAX_RPM = 5
_WINDOW_S = 60.0
_MAX_INPUT_CHARS = 20_000  # keep prompts bounded; blogs rarely exceed this

_PROMPT = (
    "Summarize the following article for a personal knowledge base. Write 3-5 "
    "sentences capturing the key points and takeaways. Return only the summary, "
    "with no preamble.\n\nTitle: {title}\n\nArticle:\n{text}"
)


class RateLimiter:
    """Sliding window: at most `max_calls` acquisitions per `window` seconds.

    `acquire()` blocks until a slot frees up. Thread-safe so it stays correct if
    calls ever arrive off a threadpool (e.g. FastAPI background tasks).
    """

    def __init__(self, max_calls: int, window: float):
        self.max_calls = max_calls
        self.window = window
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t < self.window]
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                sleep_for = self.window - (now - self._calls[0])
            time.sleep(max(sleep_for, 0.01))


class Summarizer:
    """Rate-limited wrapper over the Gemini client.

    `client` is injectable so tests can pass a fake with the same
    `.models.generate_content(model=, contents=)` surface — no network or key.
    """

    def __init__(self, api_key: str | None = None, *, client=None, max_rpm: int = MAX_RPM):
        self._client = client if client is not None else genai.Client(api_key=api_key)
        self._limiter = RateLimiter(max_rpm, _WINDOW_S)

    def summarize(self, text: str, *, title: str | None = None, max_retries: int = 4) -> str:
        prompt = _PROMPT.format(title=title or "(untitled)", text=text[:_MAX_INPUT_CHARS])
        delay = 2.0
        for attempt in range(max_retries + 1):
            self._limiter.acquire()
            try:
                resp = self._client.models.generate_content(model=MODEL, contents=prompt)
                return (resp.text or "").strip()
            except genai_errors.APIError as exc:
                if getattr(exc, "code", None) == 429 and attempt < max_retries:
                    log.warning("gemini 429; backing off %.1fs (attempt %d)", delay, attempt + 1)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
