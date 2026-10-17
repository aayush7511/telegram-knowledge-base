"""kb-orchestrator — Cloud Run processing orchestrator.

Receives job descriptors pushed by Worker 2, authenticated with a shared
secret. URL jobs share one pipeline: fetch (per source — sources.py; blogs are
rendered with Playwright and extracted with Trafilatura + extruct) → write the
content into the knowledge graph (Graphiti → FalkorDB) → reply on Telegram with
the entities and facts it extracted. Plain-text notes go straight into the
graph, with the same reply. Sources
without a fetcher yet, and native media, remain stubs (native-media ASR comes
in v4). See ../../CLAUDE.md for the architecture and ../../docs/design/v2.md /
v3.md for the graph and source decisions.

Processing is **synchronous**: `/jobs` does the work and only then responds, so
everything happens inside the request window. Cloud Run only guarantees CPU
during request processing (default no-CPU-throttling=off), so work deferred past
the response — e.g. a FastAPI BackgroundTask — risks being starved mid-render.
Holding the request keeps that guarantee and keeps request-based billing honest.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request

import articles
import graph
import sources
import telegram
from extract import ResponseObject
from summarize import Overloaded, Summarizer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("kb-orchestrator")

# httpx logs every request line at INFO, and the Telegram Bot API embeds the bot
# token in the URL path — that would write the token into Cloud Run logs on every
# reply. Warnings and errors still come through.
logging.getLogger("httpx").setLevel(logging.WARNING)
# pypdf warns once per font it can't fully decode (dozens per arXiv paper)
# without changing the extracted text — measured identical with fontTools.
logging.getLogger("pypdf").setLevel(logging.ERROR)

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


# --- Retrying a job later: YouTube home worker unreachable, Gemini overloaded -
# specs/youtube-home-worker.md, specs/summarize-retry.md: up to 3 retries, an hour apart, never between
# midnight and 6 a.m. Chicago time. Cloud Run can't wait that long inside a
# request, so Worker 2 puts the job back on the queue with a delay (/retry).

MAX_RETRIES = 3
RETRY_AFTER = timedelta(hours=1)
RETRY_TZ = ZoneInfo("America/Chicago")  # follows CDT/CST
RETRY_WINDOW_START_HOUR = 6
RETRY_CALL_ATTEMPTS = 3


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def retry_delay_seconds(now: datetime) -> int:
    """Seconds from `now` to the next retry: an hour later, pushed to 6 a.m.
    Chicago time if that would land between midnight and 6 a.m."""
    at = (now + RETRY_AFTER).astimezone(RETRY_TZ)
    if at.hour < RETRY_WINDOW_START_HOUR:
        at = at.replace(hour=RETRY_WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    return int((at - now).total_seconds())


async def request_retry(job_id: str, delay_seconds: int) -> bool:
    """Ask Worker 2 to re-enqueue the job after `delay_seconds`. Unlike status
    posts this isn't best-effort — a lost request means the job is never
    retried — so it's tried up to RETRY_CALL_ATTEMPTS times. True on success."""
    retry_url = os.environ.get("WORKER2_RETRY_URL")
    if not retry_url:
        log.error("retry not scheduled (WORKER2_RETRY_URL unset): job_id=%s", job_id)
        return False
    for attempt in range(1, RETRY_CALL_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    retry_url,
                    json={"job_id": job_id, "delay_seconds": delay_seconds},
                    headers={"X-KB-Secret": os.environ.get("WORKER2_SHARED_SECRET", "")},
                )
            if resp.status_code == 200:
                return True
            log.error("retry request failed: job_id=%s attempt=%d -> %d", job_id, attempt, resp.status_code)
        except httpx.HTTPError as exc:
            log.error("retry request failed: job_id=%s attempt=%d: %s", job_id, attempt, exc)
    return False


async def handle_worker_unreachable(job: dict, target: str, exc: Exception) -> None:
    await retry_later(job, target, exc, why="home worker unreachable", give_up_reply="Unable to get captions")


async def handle_gemini_overloaded(job: dict, target: str, exc: Exception) -> None:
    """specs/summarize-retry.md: the retry resumes at summarizing from the R2 archive."""
    await retry_later(
        job, target, exc, why="gemini overloaded",
        give_up_reply="Couldn't summarize it, please send it again later",
    )


async def retry_later(job: dict, target: str, exc: Exception, *, why: str, give_up_reply: str) -> None:
    """Schedule the next retry, or give up after MAX_RETRIES (one count per job,
    whatever the cause). Only the first failure tells the user; later ones are
    silent until the last."""
    job_id = job["job_id"]
    retries = job.get("retry_count") or 0
    if retries >= MAX_RETRIES:
        log.info("%s after %d retries: job_id=%s: %s", why, retries, job_id, exc)
        await reply_not_supported(job, target, give_up_reply)
        await post_status(job_id, "failed", error=f"{why} after {retries} retries: {exc}")
        return

    log.info("%s, retrying later: job_id=%s retry_count=%d: %s", why, job_id, retries, exc)
    await post_status(job_id, "retrying", error=str(exc))
    if not await request_retry(job_id, retry_delay_seconds(utcnow())):
        await post_status(job_id, "failed", error=f"couldn't schedule a retry: {exc}")
        return
    if retries == 0:
        await reply_not_supported(job, target, "Unavailable at the moment, I'll try again later")


# Below this much text an item wasn't summarized. Unused since summarizing was
# dropped (specs/extraction-reply.md); goes with the Gemini code.
SUMMARY_MIN_CHARS = 1_500

COULDNT_SAVE_REPLY = "Couldn't save this to memory"


async def reply_not_supported(job: dict, target: str, reason: str) -> None:
    """Tell the user an item (a link, or "your PDF") was skipped, in the same
    shape as Worker 1's reply.

    Best-effort like status posts: the job's `failed` state is the record.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = job.get("chat_id")
    if not token or chat_id is None:
        log.info("not-supported reply skipped (token/chat_id missing): job_id=%s", job.get("job_id"))
        return
    text = f"Skipped (not ingestible):\n• {target} — {reason}"
    try:
        await telegram.send_text(chat_id, job.get("message_id"), text, token=token)
    except httpx.HTTPError as exc:
        log.error("not-supported reply failed: job_id=%s: %s", job.get("job_id"), exc)


async def process_url_job(job: dict) -> None:
    """A link: the fetcher comes from sources.FETCHERS by `url_source`."""
    url, source = job.get("url"), job["url_source"]

    async def fetch():
        if not url:
            raise ValueError("url job missing url")
        return await sources.FETCHERS[source](url)

    await process_source_job(job, source, fetch, target=url or "")


async def process_pdf_file_job(job: dict) -> None:
    """A PDF sent as a Telegram file: Worker 1 already stored it in R2."""
    r2_key = (job.get("media") or {}).get("r2_key")

    async def fetch():
        if not r2_key:
            raise ValueError("document job missing media.r2_key")
        return await sources.fetch_pdf_file(r2_key)

    await process_source_job(job, "pdf", fetch, target="your PDF")


async def process_source_job(job: dict, source: str, fetch, *, target: str) -> None:
    """Shared pipeline: fetching → indexing → reply → saved (or failed, or
    retrying while the YouTube home worker is unreachable).

    `fetch()` returns the item's ResponseObject; everything after it is shared.
    The reply lists what the graph write extracted (specs/extraction-reply.md).
    `target` names the item in replies and is the episode name without a title.

    Runs inline in the request. Never raises: a failure is recorded as terminal
    `failed` in D1 and swallowed, so Worker 2 still gets a 2xx and acks the
    queue message rather than replaying an expensive fetch that would fail
    identically. A link with nothing to remember gets a "not supported" reply
    and ends `failed` before anything is archived or graphed.
    """
    job_id = job["job_id"]
    try:
        # Every delivery fetches, retries included: resuming from the R2
        # archive would move retrying → indexing, which canTransition rejects
        # (specs/extraction-reply.md). The archive is still written.
        await post_status(job_id, "fetching")
        ro = await fetch()
        await articles.store_article(job_id, ro.text)
        await articles.store_meta(job_id, ro)

        # `summary` here is the D1 column name (predates the full-text switch,
        # see graph.py) — it holds the full episode body, so the graph can be
        # rebuilt from D1 alone without re-fetching a page that may have changed.
        body, source_description = graph.url_episode(ro, source)
        await post_status(job_id, "indexing", summary=body)
        extracted = await write_episode_or_reply(
            job,
            name=ro.title or target,
            body=body,
            source_description=source_description,
        )
        await reply_saved(job, ro, extracted)
        await post_status(job_id, "saved")
    except sources.WorkerUnreachable as exc:
        await handle_worker_unreachable(job, target, exc)
    except Overloaded as exc:
        await handle_gemini_overloaded(job, target, exc)
    except sources.NotSupported as exc:
        log.info("job not supported: job_id=%s: %s", job_id, exc)
        await reply_not_supported(job, target, str(exc))
        await post_status(job_id, "failed", error=f"not supported: {exc}")
    except Exception as exc:
        log.exception("job failed: job_id=%s", job_id)
        await post_status(job_id, "failed", error=str(exc))


async def process_text_job(job: dict) -> None:
    """Text note: indexing → reply → saved (or failed)."""
    job_id = job["job_id"]
    try:
        text = (job.get("text") or "").strip()
        if not text:
            raise ValueError("text job missing text")

        await post_status(job_id, "indexing")
        extracted = await write_episode_or_reply(
            job,
            name=text.splitlines()[0][:60],
            body=text,
            source_description="telegram text note",
        )
        await reply_saved(job, None, extracted)
        await post_status(job_id, "saved")
    except Exception as exc:
        log.exception("text job failed: job_id=%s", job_id)
        await post_status(job_id, "failed", error=str(exc))


async def write_episode_or_reply(job: dict, *, name: str, body: str, source_description: str) -> graph.Extracted:
    """The graph write; on failure, tell the user before re-raising (the caller marks `failed`)."""
    try:
        return await graph.write_episode(
            job["job_id"],
            name=name,
            body=body,
            source_description=source_description,
            reference_time=graph.parse_time_received(job.get("time_received")),
        )
    except Exception:
        await send_reply(job, COULDNT_SAVE_REPLY, html=False)
        raise


async def reply_saved(job: dict, ro: ResponseObject | None, extracted: graph.Extracted) -> None:
    """Reply with what went into memory. Best-effort: a formatting or send error
    is logged and the job still ends `saved` (the graph write already happened)."""
    try:
        text = telegram.format_extraction_reply(ro, extracted.entities, extracted.facts)
    except Exception:
        log.exception("extraction reply not built: job_id=%s", job["job_id"])
        return
    await send_reply(job, text, html=True)


async def send_reply(job: dict, text: str, *, html: bool) -> None:
    """Best-effort reply threaded to the job's message; never raises."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = job.get("chat_id")
    if not token or chat_id is None:
        log.info("telegram reply skipped (token/chat_id missing): job_id=%s", job["job_id"])
        return
    send = telegram.send_html if html else telegram.send_text
    try:
        await send(chat_id, job.get("message_id"), text, token=token)
    except Exception:
        log.exception("telegram reply failed: job_id=%s", job["job_id"])


# Not /healthz: Google's frontend reserves that path on run.app and answers
# with its own 404 before the request reaches the container.
@app.get("/health")
def health():
    return {"ok": True}


def require_secret(request: Request) -> None:
    secret = os.environ.get("KB_SHARED_SECRET")
    if not secret or request.headers.get("X-KB-Secret") != secret:
        raise HTTPException(status_code=401, detail="bad or missing X-KB-Secret")


SEARCH_MAX_RESULTS = 30


@app.post("/search")
async def search(request: Request):
    """Fact search for the MCP connector (kb-mcp) — see docs/design/v3.md#mcp-connector."""
    require_secret(request)
    body = await request.json()
    query = (body.get("query") or "").strip()
    limit = body.get("limit", 10)
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    if type(limit) is not int or not 1 <= limit <= SEARCH_MAX_RESULTS:
        raise HTTPException(status_code=400, detail=f"limit must be an integer from 1 to {SEARCH_MAX_RESULTS}")
    return {"results": await graph.search_facts(query, limit)}


@app.post("/jobs")
async def receive_job(request: Request):
    require_secret(request)

    job = await request.json()
    job_id = job.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id required")

    log.info("job received: %s", job)

    content_type = job.get("content_type")
    if content_type == "url" and job.get("url_source") in sources.FETCHERS:
        # Synchronous: Worker 2's push stays open for the full pipeline
        # (fetch, then the graph write). Outcome
        # is recorded in D1 either way, so the response is 2xx regardless — see
        # process_url_job.
        await process_url_job(job)
    elif content_type == "text":
        await process_text_job(job)
    elif content_type == "url":
        # A source Worker 1 recognizes but no fetcher exists for yet (Reddit
        # awaits API approval, Instagram is v4): say so instead of leaving the
        # message at 👀.
        reason = f"{job.get('url_source')} links aren't supported yet"
        await reply_not_supported(job, job.get("url") or "", reason)
        await post_status(job_id, "failed", error=f"not supported: {reason}")
    elif content_type == "document" and (job.get("media") or {}).get("mime_type") == "application/pdf":
        await process_pdf_file_job(job)
    elif content_type == "document":
        reason = "only PDF files are supported"
        await reply_not_supported(job, "your file", reason)
        await post_status(job_id, "failed", error=f"not supported: {reason}")
    else:
        # Other job types not built yet — placeholder status so the round trip
        # stays testable end to end.
        await post_status(job_id, "summarizing")

    return {"accepted": True, "job_id": job_id}
