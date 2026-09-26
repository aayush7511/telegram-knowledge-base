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
import html
import os
import re
from typing import Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import httpx
import lxml.html
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
    except fetcher.PrivateAddress as exc:
        raise NotSupported("the link leads to a private network address") from exc
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


# --- Stack Exchange: official API (no key needed) ---------------------------
# The question + its accepted answer, else the top-voted one, else the question
# alone. A link to an answer saves the question + that answer. Without a key the
# quota is 300 requests/day per IP, and Cloud Run's egress IPs are shared, so a
# free key (STACKEXCHANGE_KEY, from stackapps.com) raises it to 10,000/day.

_SE_API = "https://api.stackexchange.com/2.3/"


def stackexchange_ref(url: str) -> tuple[str, str, str]:
    """(site domain, "question" | "answer", id) from a question or answer link."""
    u = urlparse(url)
    site = (u.hostname or "").lower().removeprefix("www.")
    segs = [s for s in u.path.split("/") if s]
    first = segs[0].lower() if segs else ""
    if first == "a" and len(segs) > 1 and segs[1].isdigit():
        return site, "answer", segs[1]
    if first in ("questions", "q") and len(segs) > 1 and segs[1].isdigit():
        # /questions/{qid}/{slug}/{answer_id} is an answer permalink
        if first == "questions" and len(segs) > 3 and segs[3].isdigit():
            return site, "answer", segs[3]
        return site, "question", segs[1]
    raise ValueError(f"no Stack Exchange question or answer in {url}")


async def _se_get(path: str, site: str, **params) -> list[dict]:
    query = {"site": site, "filter": "withbody", **params}
    if key := os.environ.get("STACKEXCHANGE_KEY"):
        query["key"] = key
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_SE_API + path, params=query)
    data = resp.json()
    if data.get("error_id"):
        raise RuntimeError(f"Stack Exchange API error {data['error_id']}: {data.get('error_message')}")
    return data.get("items", [])


def _html_text(fragment: str) -> str:
    return lxml.html.fromstring(fragment).text_content().strip() if (fragment or "").strip() else ""


def _owner(item: dict) -> str | None:
    name = (item.get("owner") or {}).get("display_name")
    return html.unescape(name) if name else None


async def fetch_stackexchange(url: str) -> ResponseObject:
    site, kind, item_id = stackexchange_ref(url)
    answer, label = None, None
    if kind == "answer":
        found = await _se_get(f"answers/{item_id}", site)
        if not found:
            raise NotSupported("the answer doesn't exist or was deleted")
        answer, label, question_id = found[0], "Linked answer", found[0]["question_id"]
    else:
        question_id = item_id
    found = await _se_get(f"questions/{question_id}", site)
    if not found:
        raise NotSupported("the question doesn't exist or was deleted")
    question = found[0]
    if answer is None and question.get("accepted_answer_id"):
        answer, label = (await _se_get(f"answers/{question['accepted_answer_id']}", site) or [None])[0], "Accepted answer"
    if answer is None and question.get("answer_count"):
        top = await _se_get(f"questions/{question_id}/answers", site, sort="votes", order="desc", pagesize=1)
        answer, label = (top or [None])[0], "Top-voted answer"
    text = _html_text(question.get("body", ""))
    if answer:
        by = f" by {_owner(answer)}" if _owner(answer) else ""
        text += f"\n\n{label}{by}:\n\n{_html_text(answer.get('body', ''))}"
    return ResponseObject(
        url=url, title=html.unescape(question.get("title", "")) or None, author=_owner(question),
        sitename=site, text=text,
    )


# --- GitHub: REST API -------------------------------------------------------
# A repo is its README; an issue or PR its title + description (no comments);
# a gist its files. Discussions have no REST endpoint (GraphQL needs a token)
# and render with every comment, so Worker 1 rejects them. GITHUB_TOKEN is optional: without it
# the limit is 60 requests/hour per IP, and Cloud Run's egress IPs are shared.

_GITHUB_API = "https://api.github.com/"


async def _github_get(path: str, *, raw: bool = False) -> httpx.Response:
    headers = {
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        "User-Agent": "kb-orchestrator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        resp = await client.get(_GITHUB_API + path)
    if resp.status_code != 404:
        resp.raise_for_status()
    return resp


async def fetch_github(url: str) -> ResponseObject:
    u = urlparse(url)
    segs = [s for s in u.path.split("/") if s]
    if u.hostname == "gist.github.com":
        resp = await _github_get(f"gists/{segs[1]}")
        if resp.status_code == 404:
            raise NotSupported("the gist doesn't exist or is secret")
        gist = resp.json()
        files = [f for f in (gist.get("files") or {}).values() if f.get("content")]
        return ResponseObject(
            url=url, title=gist.get("description") or (files[0]["filename"] if files else None),
            author=(gist.get("owner") or {}).get("login"), sitename="GitHub",
            text="\n\n".join(f"{f['filename']}:\n\n{f['content']}" for f in files),
        )
    owner, repo = segs[0], segs[1].removesuffix(".git")
    if len(segs) >= 4:  # issues/{n} or pull/{n} — PRs are issues in the REST API
        resp = await _github_get(f"repos/{owner}/{repo}/issues/{segs[3]}")
        if resp.status_code == 404:
            raise NotSupported("the issue or PR doesn't exist or is private")
        issue = resp.json()
        return ResponseObject(
            url=url, title=issue.get("title"), author=(issue.get("user") or {}).get("login"),
            sitename=f"GitHub · {owner}/{repo}", text=(issue.get("body") or "").strip(),
        )
    resp = await _github_get(f"repos/{owner}/{repo}/readme", raw=True)
    if resp.status_code == 404:
        exists = (await _github_get(f"repos/{owner}/{repo}")).status_code != 404
        raise NotSupported("the repo has no README" if exists else "the repo doesn't exist or is private")
    return ResponseObject(url=url, title=f"{owner}/{repo}", author=owner, sitename="GitHub", text=resp.text)


FETCHERS: dict[str, Callable[[str], Awaitable[ResponseObject]]] = {
    "blog": fetch_blog,
    "youtube": fetch_youtube,
    "x": fetch_x,
    "stackexchange": fetch_stackexchange,
    "github": fetch_github,
}
