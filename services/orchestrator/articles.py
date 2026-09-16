"""Archive the cleaned article text of a blog job in R2 (`articles/{job_id}.txt`).

The pipeline only keeps the summary otherwise; the full text lets a post be
re-summarized or re-extracted later without re-fetching a page that may have
changed. R2 is S3-compatible, so this is a plain boto3 put with R2 credentials.
Best-effort like the status posts: a failure is logged, never fails the job.
No-op until the R2_* variables are configured.

The bucket's future 2-day lifecycle rule must stay scoped to `raw-media/` —
`articles/` is meant to be kept.
"""
from __future__ import annotations

import asyncio
import logging
import os

import boto3

log = logging.getLogger("kb-orchestrator.articles")


def article_key(job_id: str) -> str:
    return f"articles/{job_id}.txt"


def _put(key: str, text: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    client.put_object(
        Bucket=os.environ.get("R2_BUCKET", "kb-raw-media"),
        Key=key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )


async def store_article(job_id: str, text: str) -> None:
    if not os.environ.get("R2_ACCOUNT_ID"):
        log.info("article archive skipped (R2_ACCOUNT_ID unset): job_id=%s", job_id)
        return
    key = article_key(job_id)
    try:
        # boto3 is synchronous — keep it off the event loop like the summarizer.
        await asyncio.to_thread(_put, key, text)
        log.info("article archived: job_id=%s key=%s bytes=%d", job_id, key, len(text.encode("utf-8")))
    except Exception as exc:
        log.error("article archive failed: job_id=%s key=%s: %s", job_id, key, exc)
