"""Archive the cleaned article text of a blog job in R2 (`articles/{job_id}.txt`).

The pipeline only keeps the summary otherwise; the full text lets a post be
re-summarized or re-extracted later without re-fetching a page that may have
changed. R2 is S3-compatible, so this is a plain boto3 put with R2 credentials.
Best-effort like the status posts: a failure is logged, never fails the job.
No-op until the R2_* variables are configured.

Next to it, `articles/{job_id}.json` keeps the item's url/title/author/sitename,
so a job retried while Gemini is overloaded can resume at summarizing from R2
alone instead of fetching again (specs/summarize-retry.md).

The bucket's future 2-day lifecycle rule must stay scoped to `raw-media/` —
`articles/` is meant to be kept.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import boto3

from extract import ResponseObject

log = logging.getLogger("kb-orchestrator.articles")


def article_key(job_id: str) -> str:
    return f"articles/{job_id}.txt"


def meta_key(job_id: str) -> str:
    return f"articles/{job_id}.json"


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _bucket() -> str:
    return os.environ.get("R2_BUCKET", "kb-raw-media")


def read_object(key: str) -> bytes:
    """Bytes of an R2 object (e.g. a Telegram file Worker 1 stored under
    `raw-media/`). Blocking — call via asyncio.to_thread. Raises if missing."""
    return _client().get_object(Bucket=_bucket(), Key=key)["Body"].read()


def _put(key: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
    _client().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=text.encode("utf-8"),
        ContentType=content_type,
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


async def store_meta(job_id: str, ro: ResponseObject) -> None:
    if not os.environ.get("R2_ACCOUNT_ID"):
        log.info("article meta skipped (R2_ACCOUNT_ID unset): job_id=%s", job_id)
        return
    key = meta_key(job_id)
    meta = {"url": ro.url, "title": ro.title, "author": ro.author, "sitename": ro.sitename}
    try:
        await asyncio.to_thread(_put, key, json.dumps(meta), "application/json")
        log.info("article meta archived: job_id=%s key=%s", job_id, key)
    except Exception as exc:
        log.error("article meta archive failed: job_id=%s key=%s: %s", job_id, key, exc)


async def load_archive(job_id: str) -> ResponseObject | None:
    """The archived text + metadata as a ResponseObject, or None if R2 isn't
    configured or either object is missing or unreadable."""
    if not os.environ.get("R2_ACCOUNT_ID"):
        return None
    try:
        text = (await asyncio.to_thread(read_object, article_key(job_id))).decode("utf-8")
        meta = json.loads(await asyncio.to_thread(read_object, meta_key(job_id)))
        return ResponseObject(
            url=meta["url"], title=meta.get("title"), author=meta.get("author"),
            sitename=meta.get("sitename"), text=text,
        )
    except Exception as exc:
        log.info("no usable archive: job_id=%s: %s", job_id, exc)
        return None
