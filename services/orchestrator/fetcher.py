"""Render a page with headless Chromium and return its HTML.

v1 decision: every blog page goes through Playwright so client-rendered content
is present before extraction. Raises on navigation failure so the orchestrator
can mark the job `failed`, and `PageBlocked` when the page answers with an HTTP
error (bot protection, 404) so the orchestrator can reply "not supported"
instead of summarizing an error page. A `networkidle` timeout is tolerated (we
return whatever rendered) since analytics/long-poll connections often never go
idle — the status is unknown then, and the article-text check catches junk.
"""
from __future__ import annotations

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

DEFAULT_TIMEOUT_MS = 20_000


class PageBlocked(Exception):
    """The page answered with an HTTP error status (after redirects)."""

    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


async def render(url: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """Load `url` in headless Chromium and return the rendered HTML."""
    async with async_playwright() as p:
        # --no-sandbox: required to run Chromium as root inside the container.
        browser = await p.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            response = None
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeout:
                # Never settled — take what's rendered so far rather than fail.
                await page.wait_for_load_state("domcontentloaded")
            if response is not None and response.status >= 400:
                raise PageBlocked(response.status)
            return await page.content()
        finally:
            await browser.close()
