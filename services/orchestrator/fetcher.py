"""Render a page with headless Chromium and return its HTML.

v1 decision: every blog page goes through Playwright so client-rendered content
is present before extraction. Raises on navigation failure so the orchestrator
can mark the job `failed`, and `PageBlocked` when the page answers with an HTTP
error (bot protection, 404) so the orchestrator can reply "not supported"
instead of summarizing an error page. A `networkidle` timeout is tolerated (we
return whatever rendered) since analytics/long-poll connections often never go
idle — the status is unknown then, and the article-text check catches junk.

Private addresses: Cloud Run reaches the VPC (FalkorDB, its browser UI) through
Direct VPC egress, and link targets can come from strangers' posts, so no page
may read a non-public address. Every request the browser routes (the first
navigation, every subresource) is resolved and aborted if it points at one.
Redirect hops bypass Playwright's routing (verified: page.route never sees
them), so every request is also recorded, and if any went to a non-public
address the page is discarded with `PrivateAddress` — a redirect can still
cause one blind GET, but nothing it returns is kept. Worker 1 already rejects
literal private addresses by URL shape; this catches hostnames that resolve to
one and redirects to one.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

DEFAULT_TIMEOUT_MS = 20_000


class PageBlocked(Exception):
    """The page answered with an HTTP error status (after redirects)."""

    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


class PrivateAddress(Exception):
    """The page, a redirect, or a subresource pointed at a non-public address."""


class IsDownload(Exception):
    """The link serves a file (e.g. a PDF without a .pdf path), not a page."""


async def is_public_host(host: str | None) -> bool:
    """False if `host` resolves to any non-global address (private, loopback,
    link-local, metadata, reserved). An unresolvable host counts as public —
    the fetch then fails on its own."""
    if not host:
        return False
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror:
        return True
    return all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos)


async def render(url: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """Load `url` in headless Chromium and return the rendered HTML."""
    verdicts: dict[str, bool] = {}  # host → is_public_host, per render

    async def public(host: str | None) -> bool:
        if host not in verdicts:
            verdicts[host] = await is_public_host(host)
        return verdicts[host]

    async def guard(route):
        target = urlparse(route.request.url)
        if target.scheme in ("http", "https", "ws", "wss") and not await public(target.hostname):
            await route.abort("blockedbyclient")
        else:
            await route.continue_()

    async with async_playwright() as p:
        # --no-sandbox: required to run Chromium as root inside the container.
        browser = await p.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            requested: set[str] = set()
            page.on("request", lambda req: requested.add(req.url))
            await page.route("**/*", guard)
            response = None
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeout:
                # Never settled — take what's rendered so far rather than fail.
                await page.wait_for_load_state("domcontentloaded")
            except PlaywrightError as exc:
                if not await public(urlparse(url).hostname):
                    raise PrivateAddress(url) from None
                if "Download is starting" in str(exc):  # Playwright's error for a file response
                    raise IsDownload(url) from None
                raise
            for seen in requested:
                target = urlparse(seen)
                if target.scheme in ("http", "https", "ws", "wss") and not await public(target.hostname):
                    raise PrivateAddress(seen)
            if response is not None and response.status >= 400:
                raise PageBlocked(response.status)
            return await page.content()
        finally:
            await browser.close()
