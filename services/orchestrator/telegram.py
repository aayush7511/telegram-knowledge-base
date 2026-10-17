"""Replies to the user on Telegram.

`format_extraction_reply` builds the reply to a save: what went into memory
(entities + facts, specs/extraction-reply.md). `send_html` posts it via the Bot
API, threaded to the original message. `format_message` / `send_summary` are
the older summary reply, unused since summarizing was dropped.
"""
from __future__ import annotations

import html as _html
import logging
import re

import httpx

from extract import ResponseObject

log = logging.getLogger("kb-orchestrator.telegram")

_API = "https://api.telegram.org/bot{token}/sendMessage"
_COMMENT_CAP = 300

# specs/extraction-reply.md
_MAX_ENTITIES = 15
_MAX_FACTS = 10
_MAX_OUTDATED = 3
_ENTITY_CHARS = 60
_FACT_CHARS = 200
_TITLE_CHARS = 200
_META_CHARS = 100  # author / site each; the spec leaves them uncapped, this keeps the budget
_TELEGRAM_LIMIT = 4096
_NOTHING_EXTRACTED = "Saved — nothing extracted"


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


def format_extraction_reply(
    ro: ResponseObject | None, entities: list[str], facts: list[str], outdated: list[str] = ()
) -> str:
    """Telegram HTML reply listing what a save put into memory (specs/extraction-reply.md).

    Inputs:
      ro        — the item's ResponseObject for a URL/PDF save (header source), or
                  None for a text note (no header).
      entities  — entity names from the graph write, in Graphiti's order.
      facts     — fact sentences from the graph write, in Graphiti's order.
      outdated  — older facts this save invalidated, in Graphiti's order.

    Output, in this order:
      1. Header (only when `ro` is given): bold title, then the
         "✍️ author  ·  🌐 site" line, then the link — the same header
         `format_message` produces. Title truncated to 200 chars. A link too
         long for the remaining budget has its visible text cut with "…";
         its href stays whole.
      2. "<b>Entities</b>", then the names comma-separated on one line.
      3. "<b>Facts</b>", then one "• <fact>" line per fact.
      4. "<b>No longer true</b>", then one "• <fact>" line per outdated fact
         (at most 3, same truncation and "+N more" as facts).

    Rules:
      - Duplicates removed before capping: two items are the same when they
        match ignoring case and surrounding whitespace; the first one's
        spelling is kept.
      - At most 15 entities and 10 facts. A list that was cut is followed by
        "+N more", N = unique items left out. No "+N more" when nothing was cut.
      - Each entity truncated to 60 chars, each fact to 200: an item over its
        limit becomes its first (limit − 1) chars + "…". Lengths count text
        before HTML escaping.
      - A section with no items is omitted entirely (no heading). When both
        are empty, the body is "Saved — nothing extracted".
      - All user and extracted text is HTML-escaped.
      - The whole message stays under Telegram's 4,096-character limit.
    """
    entities, facts, outdated = _unique(entities), _unique(facts), _unique(list(outdated))

    body: list[str] = []
    if entities:
        body.append("<b>Entities</b>")
        body.append(", ".join(_esc(_truncate(e, _ENTITY_CHARS)) for e in entities[:_MAX_ENTITIES]))
        body += _more(entities, _MAX_ENTITIES)
    for heading, items, cap in (("Facts", facts, _MAX_FACTS), ("No longer true", outdated, _MAX_OUTDATED)):
        if not items:
            continue
        if body:
            body.append("")
        body.append(f"<b>{heading}</b>")
        body += [f"• {_esc(_truncate(f, _FACT_CHARS))}" for f in items[:cap]]
        body += _more(items, cap)
    text = "\n".join(body) or _NOTHING_EXTRACTED

    if ro is None:
        return text

    header: list[str] = []
    if ro.title:
        header.append(f"<b>{_esc(_truncate(ro.title, _TITLE_CHARS))}</b>")
    meta = []
    if ro.author:
        meta.append(f"✍️ {_esc(_truncate(ro.author, _META_CHARS))}")
    if ro.sitename:
        meta.append(f"🌐 {_esc(_truncate(ro.sitename, _META_CHARS))}")
    if meta:
        header.append("  ·  ".join(meta))
    if ro.url:
        # The link's visible text gets whatever the rest leaves under the limit
        # (+1 for its own newline, +2 for the blank line before the body).
        rest = _visible_len("\n".join(header)) + (1 if header else 0) + 2 + _visible_len(text)
        room = max(_TELEGRAM_LIMIT - 1 - rest, 20)
        header.append(f'<a href="{_esc(ro.url)}">{_esc(_truncate(ro.url, room))}</a>')

    return "\n".join(header) + "\n\n" + text if header else text


async def send_html(chat_id, message_id, text: str, *, token: str, client=None):
    """POST an already-formatted Telegram HTML message, replying to the source message."""
    payload = {
        "chat_id": chat_id,
        "text": text,
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


def _unique(items: list[str]) -> list[str]:
    """Drop blanks and repeats (same ignoring case and surrounding whitespace); first spelling wins."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        stripped = (item or "").strip()
        key = stripped.casefold()
        if stripped and key not in seen:
            seen.add(key)
            out.append(stripped)
    return out


def _more(items: list[str], cap: int) -> list[str]:
    return [f"+{len(items) - cap} more"] if len(items) > cap else []


def _visible_len(s: str) -> int:
    """Characters Telegram shows (and counts toward its limit): tags stripped, entities decoded."""
    return len(_html.unescape(re.sub(r"<[^>]+>", "", s)))
