"""kb-orchestrator — Cloud Run processing orchestrator (stub).

Receives job descriptors pushed by Worker 2, authenticated with a shared
secret. For now it only logs the descriptor and exercises the status-update
callback to Worker 2; real processing (blog extraction, Groq ASR/summarize,
Pi delegation) comes later. See ../../convo_summary.md for the architecture.
"""

import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("kb-orchestrator")

app = FastAPI()


def post_status(
    job_id: str,
    state: str,
    r2_key: str | None = None,
    error: str | None = None,
) -> None:
    """Report a job state change to Worker 2, which owns the D1 writes.

    Best-effort: failures are logged but never propagate — D1 state drives
    retries, not this callback. No-op until WORKER2_STATUS_URL is configured
    (Worker 2 doesn't exist yet).
    """
    status_url = os.environ.get("WORKER2_STATUS_URL")
    if not status_url:
        log.info("status update skipped (WORKER2_STATUS_URL unset): job_id=%s state=%s", job_id, state)
        return
    body = {"job_id": job_id, "state": state, "r2_key": r2_key, "error": error}
    try:
        resp = httpx.post(
            status_url,
            json=body,
            headers={"X-KB-Secret": os.environ.get("WORKER2_SHARED_SECRET", "")},
            timeout=10,
        )
        log.info("status update sent: job_id=%s state=%s -> %d", job_id, state, resp.status_code)
    except httpx.HTTPError as exc:
        log.error("status update failed: job_id=%s state=%s: %s", job_id, state, exc)


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

    # Stub: no processing yet. Fire a placeholder state update so the
    # Cloud Run -> Worker 2 -> D1 round trip is testable end to end the
    # moment Worker 2 deploys.
    post_status(job_id, "summarizing")

    return {"accepted": True, "job_id": job_id}
