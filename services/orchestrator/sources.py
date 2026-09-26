"""Per-source fetchers for URL jobs: url → ResponseObject, or NotSupported.

Every URL source runs the same pipeline (main.process_url_job: fetch →
archive → summarize → reply → graph); only fetching differs, picked from
FETCHERS by the job's `url_source`. A fetcher raises NotSupported when the link
has nothing to remember, so the job gets a "not supported" reply instead of
being saved. Sources without a fetcher yet stay on the orchestrator's
placeholder. Decisions per source: ../../docs/design/v3.md.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import extract
import fetcher
from extract import ResponseObject

# Below this much extracted text a blog page has nothing to remember: login
# walls, error and bot-challenge pages, empty shells. Real articles measured
# 6K–67K chars; bot-block pages 41–460 (docs/design/v3.md#no-useful-content).
MIN_ARTICLE_CHARS = 1_000


class NotSupported(Exception):
    """The link has nothing to remember — reply and fail the job, don't save."""


async def fetch_blog(url: str) -> ResponseObject:
    """Render with Playwright, extract with Trafilatura + extruct."""
    try:
        html = await fetcher.render(url)
    except fetcher.PageBlocked as exc:
        raise NotSupported(f"the site returned HTTP {exc.status}") from exc
    ro = extract.extract_content(html, url)
    if len((ro.text or "").strip()) < MIN_ARTICLE_CHARS:
        raise NotSupported("no article text found")
    return ro


FETCHERS: dict[str, Callable[[str], Awaitable[ResponseObject]]] = {
    "blog": fetch_blog,
}
