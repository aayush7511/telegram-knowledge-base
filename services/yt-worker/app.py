"""yt-worker — fetches English YouTube captions from a home IP for kb-orchestrator.

YouTube blocks Cloud Run's IPs; from a home connection youtube-transcript-api
returns captions in about a second (spikes/youtube-transcript). Cloud Run calls
POST /transcript through Tailscale Funnel; this server listens on 127.0.0.1
only. Spec: ../../specs/youtube-home-worker.md.

Every real answer is a 200 with a `status`, so Cloud Run can treat anything
else (Funnel's 502 when this is down, a 500 from a crash) as "unreachable".
"""
import hmac
import os

from fastapi import FastAPI, HTTPException, Request
from youtube_transcript_api import (
    InvalidVideoId,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
)

app = FastAPI()


def get_api() -> YouTubeTranscriptApi:
    return YouTubeTranscriptApi()


def _is_english(language_code: str) -> bool:
    return language_code == "en" or language_code.startswith("en-")


@app.post("/transcript")
async def transcript(request: Request):
    # Its own secret (YT_WORKER_SECRET), not Worker 2's: this box is the least
    # protected in the system, so a leak here opens nothing else.
    secret = os.environ.get("YT_WORKER_SECRET", "")
    if not secret or not hmac.compare_digest(request.headers.get("X-KB-Secret", ""), secret):
        raise HTTPException(status_code=401, detail="bad or missing X-KB-Secret")

    video_id = (await request.json()).get("video_id", "")
    try:
        english = [t for t in get_api().list(video_id) if _is_english(t.language_code)]
        if not english:
            return {"status": "no_captions"}
        fetched = english[0].fetch()
    except TranscriptsDisabled:
        return {"status": "no_captions"}
    except RequestBlocked:  # includes its subclass IpBlocked
        return {"status": "blocked"}
    except (VideoUnavailable, VideoUnplayable, InvalidVideoId):
        return {"status": "unavailable"}
    return {
        "status": "ok",
        "text": " ".join(s.text for s in fetched.snippets),
        "language": fetched.language_code,
        "is_generated": fetched.is_generated,
    }
