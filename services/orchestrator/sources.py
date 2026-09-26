"""Per-source fetchers for URL jobs: url → ResponseObject, or NotSupported.

Every URL source runs the same pipeline (main.process_url_job: fetch →
archive → summarize → reply → graph); only fetching differs, picked from
FETCHERS by the job's `url_source`. A fetcher raises NotSupported when the link
has nothing to remember, so the job gets a "not supported" reply instead of
being saved. Sources without a fetcher yet stay on the orchestrator's
placeholder. Decisions per source: ../../docs/design/v3.md.
"""
from __future__ import annotations

import asyncio
import re
from typing import Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import httpx
import youtube_transcript_api as yta

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


# --- YouTube: captions (youtube-transcript-api) + title/channel (oEmbed) -----
# Works from Cloud Run's IPs but slowly (4–154s per video in the spike vs ~1s
# from home — spikes/youtube-transcript), so each fetch gets its own timeout
# well inside the 600s request. A block or timeout is an ordinary `failed`.

YOUTUBE_TIMEOUT_S = 240
NO_CAPTIONS = "the video has no captions — transcription comes in v4"
_YT_ID = re.compile(r"^[\w-]{11}$")


def youtube_video_id(url: str) -> str:
    """The 11-char id from a watch / youtu.be / shorts / live link."""
    u = urlparse(url)
    segs = [s for s in u.path.split("/") if s]
    if u.hostname == "youtu.be":
        vid = segs[0] if segs else ""
    elif segs and segs[0] in ("shorts", "live") and len(segs) > 1:
        vid = segs[1]
    else:
        vid = parse_qs(u.query).get("v", [""])[0]
    if not _YT_ID.match(vid):
        raise ValueError(f"no YouTube video id in {url}")
    return vid


def _youtube_transcript(video_id: str) -> str:
    """Caption text, English preferred (manual before auto), else any language;
    "" when the video has no captions at all.

    Blocking (requests under the hood) — called via asyncio.to_thread.
    """
    transcripts = yta.YouTubeTranscriptApi().list(video_id)
    try:
        transcript = transcripts.find_transcript(["en", "en-US", "en-GB"])
    except yta.NoTranscriptFound:
        transcript = next(iter(transcripts), None)
    if transcript is None:
        return ""
    return " ".join(s.text for s in transcript.fetch().snippets)


async def _youtube_oembed(video_id: str) -> dict:
    """Title + channel. Best-effort: missing metadata never fails the job."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            )
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError):
        return {}


async def fetch_youtube(url: str) -> ResponseObject:
    video_id = youtube_video_id(url)
    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(_youtube_transcript, video_id), timeout=YOUTUBE_TIMEOUT_S
        )
    except yta.TranscriptsDisabled as exc:
        raise NotSupported(NO_CAPTIONS) from exc
    except (yta.VideoUnavailable, yta.VideoUnplayable, yta.AgeRestricted, yta.InvalidVideoId) as exc:
        raise NotSupported("the video is unavailable, private, or age-restricted") from exc
    if not text.strip():
        raise NotSupported(NO_CAPTIONS)
    meta = await _youtube_oembed(video_id)
    return ResponseObject(
        url=url, title=meta.get("title"), author=meta.get("author_name"), sitename="YouTube", text=text
    )


# --- X: FxTwitter v2 (no login) — spikes/x-fxtwitter -----------------------
# /2/thread/{id} returns the linked post plus the author's own thread (their
# posts only, in order) from any post in it. Saved as the whole thread; an X
# Article's text comes as Draft.js blocks, flattened here.

_FXTWITTER = "https://api.fxtwitter.com/2/thread/{id}"


def x_status_id(url: str) -> str:
    segs = [s for s in urlparse(url).path.split("/") if s]
    for i, seg in enumerate(segs[:-1]):
        if seg.lower() == "status" and segs[i + 1].isdigit():
            return segs[i + 1]
    raise ValueError(f"no X post id in {url}")


def flatten_article(article: dict) -> str:
    """Draft.js blocks → plain text, keeping list markers and paragraph breaks."""
    lines, n = [], 0
    for block in (article.get("content") or {}).get("blocks", []):
        kind, text = block.get("type"), (block.get("text") or "").strip()
        n = n + 1 if kind == "ordered-list-item" else 0
        if not text or kind == "atomic":  # atomic = embedded media
            continue
        if kind == "ordered-list-item":
            text = f"{n}. {text}"
        elif kind == "unordered-list-item":
            text = f"- {text}"
        lines.append(text)
    return "\n\n".join(lines)


def _x_post_text(post: dict) -> str:
    text = flatten_article(post["article"]) if post.get("article") else (post.get("text") or "").strip()
    quote = post.get("quote")
    if quote and (quote.get("text") or "").strip():
        who = (quote.get("author") or {}).get("screen_name", "?")
        text = f"{text}\n\nQuoting @{who}: {quote['text'].strip()}".strip()
    return text


async def _x_thread(status_id: str) -> dict | None:
    """FxTwitter's thread payload, or None when the post doesn't exist (404)."""
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "kb-orchestrator"}) as client:
        resp = await client.get(_FXTWITTER.format(id=status_id))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def fetch_x(url: str) -> ResponseObject:
    data = await _x_thread(x_status_id(url))
    if not data or not data.get("status"):
        raise NotSupported("the post doesn't exist (deleted or private)")
    status = data["status"]
    posts = data.get("thread") or [status]
    text = "\n\n".join(t for t in (_x_post_text(p) for p in posts) if t)
    if not text:
        raise NotSupported("the post has no text — images and video come in v4")
    author = status.get("author") or {}
    article = next((p["article"] for p in posts if p.get("article")), None)
    return ResponseObject(
        url=url,
        title=article.get("title") if article else None,
        author=f"@{author['screen_name']}" if author.get("screen_name") else None,
        sitename="X",
        text=text,
    )


FETCHERS: dict[str, Callable[[str], Awaitable[ResponseObject]]] = {
    "blog": fetch_blog,
    "youtube": fetch_youtube,
    "x": fetch_x,
}
