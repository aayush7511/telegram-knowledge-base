"""Spike: does FxTwitter's v2 API return long-form X content in full?

For each post ID, calls /2/thread/{id} (which also returns the post itself)
and prints what kind of post it is and how much text came back. No auth, no
cookies. Usage: python3 spike.py [post_id ...]
"""
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_IDS = [
    "2002118205729562949",  # Karpathy — X Article "2025 LLM Year in Review"
    "2103549456662852008",  # The Neuron — X Article, very long newsletter
    "2019137879310836075",  # Karpathy — long post (note tweet)
    "1977755427569111362",  # Karpathy — nanochat thread, 3 posts
    "1977755433172443626",  # same thread, linked from its last post
    "1983584366547829073",  # Sam Altman — long post + self-reply
    "2102153039121621069",  # James Zou — post that's mostly a link
    "1000000000000000001",  # doesn't exist
]


def get(path: str):
    req = urllib.request.Request(f"https://api.fxtwitter.com/2/{path}", headers={"User-Agent": "kb-spike/0.1"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30)), "ok"
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"


for sid in sys.argv[1:] or DEFAULT_IDS:
    start = time.monotonic()
    d, status = get(f"thread/{sid}")
    took = f"{time.monotonic() - start:.1f}s"
    if not d:
        print(sid, status, took)
        continue
    s, thread = d["status"], d.get("thread") or []
    if s.get("article"):
        blocks = s["article"]["content"]["blocks"]
        kind, chars = "article", sum(len(b["text"]) for b in blocks)
    else:
        kind, chars = ("note" if s.get("is_note_tweet") else "post"), sum(len(p.get("text", "")) for p in thread)
    authors = sorted({p["author"]["screen_name"] for p in thread})
    print(sid, status, took, "|", kind, "| thread posts:", len(thread), "| authors:", authors, "| chars:", chars)
