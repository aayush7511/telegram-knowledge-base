"""kb-orchestrator — Cloud Run processing orchestrator.

Receives job descriptors pushed by Worker 2, authenticated with a shared
secret. Blog URLs are fully processed here: render (Playwright) → extract text +
metadata (Trafilatura + extruct) → summarize (Gemini) → reply on Telegram →
write the summary into the knowledge graph (Graphiti → FalkorDB). Plain-text
notes go straight into the graph. Other job types remain stubs (native-media
Instagram/YouTube fetching comes in v3, native-media ASR in v4). See ../../CLAUDE.md for the
architecture and ../../docs/design/v2.md for the graph decisions.

Processing is **synchronous**: `/jobs` does the work and only then responds, so
everything happens inside the request window. Cloud Run only guarantees CPU
during request processing (default no-CPU-throttling=off), so work deferred past
the response — e.g. a FastAPI BackgroundTask — risks being starved mid-render.
Holding the request keeps that guarantee and keeps request-based billing honest.
"""

import asyncio
import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Request

import articles
import fetcher
import graph
import telegram
from extract import ResponseObject, extract_content
from summarize import Summarizer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("kb-orchestrator")

# httpx logs every request line at INFO, and the Telegram Bot API embeds the bot
# token in the URL path — that would write the token into Cloud Run logs on every
# reply. Warnings and errors still come through.
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI()

_summarizer: Summarizer | None = None


def get_summarizer() -> Summarizer:
    """Lazily build the Gemini summarizer (needs GEMINI_API_KEY at first use)."""
    global _summarizer
    if _summarizer is None:
        _summarizer = Summarizer(api_key=os.environ.get("GEMINI_API_KEY"))
    return _summarizer


async def post_status(
    job_id: str,
    state: str,
    r2_key: str | None = None,
    error: str | None = None,
    summary: str | None = None,
) -> None:
    """Report a job state change to Worker 2, which owns the D1 writes.

    Best-effort: failures are logged but never propagate — D1 state drives
    retries, not this callback. No-op until WORKER2_STATUS_URL is configured.
    Async so it never blocks the event loop while a job holds the request open.
    `summary` rides along with `indexing` so D1 keeps the graph episode text.
    """
    status_url = os.environ.get("WORKER2_STATUS_URL")
    if not status_url:
        log.info("status update skipped (WORKER2_STATUS_URL unset): job_id=%s state=%s", job_id, state)
        return
    body = {"job_id": job_id, "state": state, "r2_key": r2_key, "error": error, "summary": summary}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                status_url,
                json=body,
                headers={"X-KB-Secret": os.environ.get("WORKER2_SHARED_SECRET", "")},
            )
        log.info("status update sent: job_id=%s state=%s -> %d", job_id, state, resp.status_code)
    except httpx.HTTPError as exc:
        log.error("status update failed: job_id=%s state=%s: %s", job_id, state, exc)


# Below this much extracted text a page has nothing to remember: login walls,
# error and bot-challenge pages, empty shells. Real articles measured 6K–67K
# chars; bot-block pages 41–460 (docs/design/v3.md#no-useful-content).
MIN_ARTICLE_CHARS = 1_000


class NotSupported(Exception):
    """The page has nothing to remember — reply and fail the job, don't save."""


async def reply_not_supported(job: dict, reason: str) -> None:
    """Tell the user a link was skipped, in the same shape as Worker 1's reply.

    Best-effort like status posts: the job's `failed` state is the record.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = job.get("chat_id")
    if not token or chat_id is None:
        log.info("not-supported reply skipped (token/chat_id missing): job_id=%s", job.get("job_id"))
        return
    text = f"Skipped (not ingestible):\n• {job.get('url')} — {reason}"
    try:
        await telegram.send_text(chat_id, job.get("message_id"), text, token=token)
    except httpx.HTTPError as exc:
        log.error("not-supported reply failed: job_id=%s: %s", job.get("job_id"), exc)


async def process_blog_job(job: dict) -> None:
    """Blog pipeline: fetching → summarizing → reply → indexing → saved (or failed).

    Runs inline in the request. Never raises: a failure is recorded as terminal
    `failed` in D1 and swallowed, so Worker 2 still gets a 2xx and acks the
    queue message rather than replaying an expensive render+summarize that would
    fail identically and burn the Gemini rate budget. A page with nothing to
    remember (HTTP error, too little article text) gets a "not supported" reply
    and ends `failed` before anything is archived, summarized, or graphed.
    """
    job_id = job["job_id"]
    url = job.get("url")
    try:
        if not url:
            raise ValueError("blog job missing url")

        await post_status(job_id, "fetching")
        try:
            html = await fetcher.render(url)
        except fetcher.PageBlocked as exc:
            raise NotSupported(f"the site returned HTTP {exc.status}") from exc
        ro: ResponseObject = extract_content(html, url)
        if len((ro.text or "").strip()) < MIN_ARTICLE_CHARS:
            raise NotSupported("no article text found")
        await articles.store_article(job_id, ro.text)

        await post_status(job_id, "summarizing")
        # summarize() blocks (rate-limiter sleeps + a sync SDK call), so it goes
        # to a worker thread — otherwise it would stall the whole event loop.
        ro.summary = await asyncio.to_thread(
            get_summarizer().summarize, ro.text, title=ro.title
        )

        log.info(
            "response object: job_id=%s title=%r author=%r sitename=%r summary_len=%d",
            job_id, ro.title, ro.author, ro.sitename, len(ro.summary or ""),
        )

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = job.get("chat_id")
        if token and chat_id is not None:
            await telegram.send_summary(chat_id, job.get("message_id"), ro, token=token)
        else:
            log.info("telegram reply skipped (token/chat_id missing): job_id=%s", job_id)

        # The reply is out, so the user has the summary even if the graph write
        # fails — that failure is recoverable from D1, which gets the episode
        # text with the `indexing` status.
        # `summary` here is the D1 column name (predates the full-text switch,
        # see graph.py) — it now holds the full episode body, not a short
        # summary, which only strengthens its purpose: rebuilding the graph
        # from D1 alone without re-fetching a page that may have changed.
        body, source_description = graph.blog_episode(ro)
        await post_status(job_id, "indexing", summary=body)
        await graph.write_episode(
            job_id,
            name=ro.title or url,
            body=body,
            source_description=source_description,
            reference_time=graph.parse_time_received(job.get("time_received")),
        )

        await post_status(job_id, "saved")
    except NotSupported as exc:
        log.info("blog job not supported: job_id=%s: %s", job_id, exc)
        await reply_not_supported(job, str(exc))
        await post_status(job_id, "failed", error=f"not supported: {exc}")
    except Exception as exc:
        log.exception("blog job failed: job_id=%s", job_id)
        await post_status(job_id, "failed", error=str(exc))


async def process_text_job(job: dict) -> None:
    """Text note: indexing → saved (or failed). No reply — the 👌 reaction is the ack."""
    job_id = job["job_id"]
    try:
        text = (job.get("text") or "").strip()
        if not text:
            raise ValueError("text job missing text")

        await post_status(job_id, "indexing")
        await graph.write_episode(
            job_id,
            name=text.splitlines()[0][:60],
            body=text,
            source_description="telegram text note",
            reference_time=graph.parse_time_received(job.get("time_received")),
        )
        await post_status(job_id, "saved")
    except Exception as exc:
        log.exception("text job failed: job_id=%s", job_id)
        await post_status(job_id, "failed", error=str(exc))


# Not /healthz: Google's frontend reserves that path on run.app and answers
# with its own 404 before the request reaches the container.
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/jobs")
async def receive_job(request: Request):
    secret = os.environ.get("KB_SHARED_SECRET")
    if not secret or request.headers.get("X-KB-Secret") != secret:
        raise HTTPException(status_code=401, detail="bad or missing X-KB-Secret")

    job = await request.json()
    job_id = job.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id required")

    log.info("job received: %s", job)

    content_type = job.get("content_type")
    if content_type == "url" and job.get("url_source") == "blog":
        # Synchronous: Worker 2's push stays open for the full pipeline
        # (render + summarize ~20-30s, plus the graph write). Outcome is
        # recorded in D1 either way, so the response is 2xx regardless — see
        # process_blog_job.
        await process_blog_job(job)
    elif content_type == "text":
        await process_text_job(job)
    else:
        # Other job types not built yet — placeholder status so the round trip
        # stays testable end to end.
        await post_status(job_id, "summarizing")

    return {"accepted": True, "job_id": job_id}
