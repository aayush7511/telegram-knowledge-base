"""Deliver the assembled summary back to the user on Telegram.

`format_message` is a pure function (the diagram's "Telegram Message Format":
Title / Author / Summary / URL / Comments) so it unit-tests without a network.
`send_summary` posts it via the Bot API, threaded to the original message.
"""
from __future__ import annotations

import html as _html
import logging

import httpx

from extract import ResponseObject

log = logging.getLogger("kb-orchestrator.telegram")

_API = "https://api.telegram.org/bot{token}/sendMessage"
_COMMENT_CAP = 300


def format_message(ro: ResponseObject) -> str:
    """Render the Response Object as Telegram HTML (Title/Author/Summary/URL/Comments)."""
    lines: list[str] = []
    if ro.title:
        lines.append(f"<b>{_esc(ro.title)}</b>")

    meta = []
    if ro.author:
        meta.append(f"✍️ {_esc(ro.author)}")
    if ro.sitename:
        meta.append(f"🌐 {_esc(ro.sitename)}")
    if meta:
        lines.append("  ·  ".join(meta))

    if ro.summary:
        lines.append("")
        lines.append(_esc(ro.summary))

    if ro.url:
        lines.append("")
        lines.append(f'<a href="{_esc(ro.url)}">{_esc(ro.url)}</a>')

    if ro.comments:
        lines.append("")
        lines.append(f"<i>{_esc(_truncate(ro.comments, _COMMENT_CAP))}</i>")

    return "\n".join(lines)


async def send_summary(chat_id, message_id, ro: ResponseObject, *, token: str, client=None):
    """POST the formatted summary to Telegram, replying to the source message."""
    payload = {
        "chat_id": chat_id,
        "text": format_message(ro),
        "parse_mode": "HTML",
        "reply_to_message_id": message_id,
        "link_preview_options": {"is_disabled": True},
    }
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        resp = await client.post(_API.format(token=token), json=payload)
        resp.raise_for_status()
        return resp.json()
    finally:
        if owns_client:
            await client.aclose()


async def send_text(chat_id, message_id, text: str, *, token: str, client=None):
    """POST a plain-text message to Telegram, replying to the source message."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": message_id,
        "link_preview_options": {"is_disabled": True},
    }
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        resp = await client.post(_API.format(token=token), json=payload)
        resp.raise_for_status()
        return resp.json()
    finally:
        if owns_client:
            await client.aclose()


def _esc(s: str | None) -> str:
    return _html.escape(s or "", quote=True)


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"
