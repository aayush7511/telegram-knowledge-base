"""kb-orchestrator — Cloud Run processing orchestrator.

Receives job descriptors pushed by Worker 2, authenticated with a shared
secret. Blog URLs are fully processed here: render (Playwright) → extract text +
metadata (Trafilatura + extruct) → summarize (Gemini 2.5 Flash) → assemble a
Response Object, log it, and reply on Telegram. Other job types remain stubs
(native-media ASR and Instagram/YouTube Pi delegation come later). See
../../convo_summary.md for the architecture.

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

import fetcher
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
) -> None:
    """Report a job state change to Worker 2, which owns the D1 writes.

    Best-effort: failures are logged but never propagate — D1 state drives
    retries, not this callback. No-op until WORKER2_STATUS_URL is configured.
    Async so it never blocks the event loop while a job holds the request open.
    """
    status_url = os.environ.get("WORKER2_STATUS_URL")
    if not status_url:
        log.info("status update skipped (WORKER2_STATUS_URL unset): job_id=%s state=%s", job_id, state)
        return
    body = {"job_id": job_id, "state": state, "r2_key": r2_key, "error": error}
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


async def process_blog_job(job: dict) -> None:
    """Blog pipeline: fetching → summarizing → saved (or failed), with a reply.

    Runs inline in the request. Never raises: a failure is recorded as terminal
    `failed` in D1 and swallowed, so Worker 2 still gets a 2xx and acks the
    queue message rather than replaying an expensive render+summarize that would
    fail identically and burn the Gemini rate budget.
    """
    job_id = job["job_id"]
    url = job.get("url")
    try:
        if not url:
            raise ValueError("blog job missing url")

        await post_status(job_id, "fetching")
        html = await fetcher.render(url)
        ro: ResponseObject = extract_content(html, url)

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

        await post_status(job_id, "saved")
    except Exception as exc:
        log.exception("blog job failed: job_id=%s", job_id)
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

    if job.get("content_type") == "url" and job.get("url_source") == "blog":
        # Synchronous: Worker 2's push stays open for the full pipeline
        # (~20-30s). Outcome is recorded in D1 either way, so the response is
        # 2xx regardless — see process_blog_job.
        await process_blog_job(job)
    else:
        # Other job types not built yet — placeholder status so the round trip
        # stays testable end to end.
        await post_status(job_id, "summarizing")

    return {"accepted": True, "job_id": job_id}
