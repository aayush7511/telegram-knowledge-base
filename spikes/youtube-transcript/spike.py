"""Spike: can youtube-transcript-api fetch captions from a Google Cloud IP?

Tries a few videos with no proxy first, then once through each proxy in
YTT_PROXIES. Prints one line per attempt: ok (with transcript length) or the
exception name (RequestBlocked / IpBlocked = YouTube blocked that IP).

Proxy credentials come from the environment only, never from arguments, so
they can't end up in shell history or in this file:
  YTT_PROXIES      comma-separated host:port list (optional)
  YTT_PROXY_USER   proxy username
  YTT_PROXY_PASS   proxy password
"""
import os
import time

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

VIDEOS = ["zjkBMFhNj_g", "kCc8FmEb1nY", "aircAruvnKk"]  # Karpathy LLM intro, Karpathy GPT-from-scratch, 3Blue1Brown neural nets


def attempt(label: str, api: YouTubeTranscriptApi) -> None:
    for vid in VIDEOS:
        start = time.monotonic()
        try:
            chars = sum(len(s.text) for s in api.fetch(vid))
            print(f"{label:<22} {vid}  ok  {chars} chars  {time.monotonic() - start:.1f}s")
        except Exception as e:  # the exception type is the result we're after
            print(f"{label:<22} {vid}  {type(e).__name__}")


attempt("direct", YouTubeTranscriptApi())

user, password = os.environ.get("YTT_PROXY_USER"), os.environ.get("YTT_PROXY_PASS")
for i, hostport in enumerate(p for p in os.environ.get("YTT_PROXIES", "").split(",") if p):
    url = f"http://{user}:{password}@{hostport.strip()}"
    # Label by index, not host — keeps proxy addresses out of pasted output.
    attempt(f"proxy {i + 1}", YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=url, https_url=url)))
