"""Render a page with headless Chromium and return its HTML.

v1 decision: every blog page goes through Playwright so client-rendered content
is present before extraction. Raises on navigation failure so the orchestrator
can mark the job `failed`; a `networkidle` timeout is tolerated (we return
whatever rendered) since analytics/long-poll connections often never go idle.
"""
from __future__ import annotations

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

DEFAULT_TIMEOUT_MS = 20_000


async def render(url: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """Load `url` in headless Chromium and return the rendered HTML."""
    async with async_playwright() as p:
        # --no-sandbox: required to run Chromium as root inside the container.
        browser = await p.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeout:
                # Never settled — take what's rendered so far rather than fail.
                await page.wait_for_load_state("domcontentloaded")
            return await page.content()
        finally:
            await browser.close()
