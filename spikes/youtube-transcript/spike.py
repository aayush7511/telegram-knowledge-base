"""Spike: can youtube-transcript-api fetch captions from a Google Cloud IP?

Tries a few videos with no proxy first, then once through each proxy.
Prints one line per attempt: ok (with transcript length) or the exception
name (RequestBlocked / IpBlocked = YouTube blocked that IP; ProxyError = the
proxy itself refused, with the reason).

Proxies come from the environment only, never from arguments, so credentials
can't end up in shell history or in this file. Either:
  WEBSHARE_API_KEY  — the proxy list and each proxy's credentials are read
                      from Webshare's API (preferred: nothing to retype)
or, for any other provider:
  YTT_PROXIES       comma-separated host:port list
  YTT_PROXY_USER    proxy username
  YTT_PROXY_PASS    proxy password
"""
import json
import os
import time
import urllib.request

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

VIDEOS = ["zjkBMFhNj_g", "kCc8FmEb1nY", "aircAruvnKk"]  # Karpathy LLM intro, Karpathy GPT-from-scratch, 3Blue1Brown neural nets
_SECRETS: list[str] = []  # scrubbed from printed errors


def attempt(label: str, api: YouTubeTranscriptApi) -> None:
    for vid in VIDEOS:
        start = time.monotonic()
        try:
            chars = sum(len(s.text) for s in api.fetch(vid))
            print(f"{label:<22} {vid}  ok  {chars} chars  {time.monotonic() - start:.1f}s")
        except Exception as e:  # the exception type is the result we're after
            print(f"{label:<22} {vid}  {type(e).__name__}{_proxy_cause(e)}")


def _proxy_cause(e: Exception) -> str:
    """For proxy failures, the underlying reason (e.g. "407 Proxy Authentication
    Required" = wrong credentials) with any credentials scrubbed."""
    if type(e).__name__ != "ProxyError":
        return ""
    msg = str(e)
    for secret in _SECRETS:
        msg = msg.replace(secret, "***")
    for hint in ("407", "Proxy Authentication", "Connection refused", "timed out", "Tunnel connection failed"):
        if hint in msg:
            start = msg.find(hint)
            return f"  ({msg[start:start + 60]})"
    return f"  ({msg[-80:]})"


def proxies() -> list[tuple[str, str, str]]:
    """(host:port, username, password) for each proxy."""
    if key := os.environ.get("WEBSHARE_API_KEY"):
        req = urllib.request.Request(
            "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page_size=25",
            headers={"Authorization": f"Token {key}"},
        )
        results = json.load(urllib.request.urlopen(req, timeout=20))["results"]
        return [(f"{p['proxy_address']}:{p['port']}", p["username"], p["password"]) for p in results if p["valid"]]
    user, password = os.environ.get("YTT_PROXY_USER", ""), os.environ.get("YTT_PROXY_PASS", "")
    return [(hp.strip(), user, password) for hp in os.environ.get("YTT_PROXIES", "").split(",") if hp.strip()]


attempt("direct", YouTubeTranscriptApi())

for i, (hostport, user, password) in enumerate(proxies()):
    _SECRETS.extend(s for s in (user, password) if s)
    url = f"http://{user}:{password}@{hostport}"
    # Label by index, not host — keeps proxy addresses out of pasted output.
    attempt(f"proxy {i + 1}", YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=url, https_url=url)))
