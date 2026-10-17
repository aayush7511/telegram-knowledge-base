"""Spike: can yt-dlp, instaloader, or gallery-dl read Instagram posts and reels without a login?

For each URL, runs each tool in its own subprocess (metadata only, no media
download) with a hard timeout, and records whether it returned the caption and
media URLs, how long the fetch took, and the error if it failed. Then scores
the fallback chain yt-dlp → instaloader → gallery-dl: the first tool that
succeeds wins, and the chain's time is the sum of the attempts up to it.

Usage: .venv/bin/python spike.py [url ...]
SPIKE_TOOLS=yt-dlp,instaloader limits the run to those tools, in that order.
Writes results/<timestamp>.json.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
TOOLS = os.environ.get("SPIKE_TOOLS", "yt-dlp,instaloader,gallery-dl").split(",")
TIMEOUT = 60  # seconds per tool per URL
PAUSE = 2  # seconds between requests, to stay polite to Instagram's rate limiter

# Public posts and reels from Wikipedia's "most-viewed Instagram reels" and
# "most-liked Instagram posts" lists — real, high-profile, and unlikely to vanish.
DEFAULT_URLS = [
    "https://www.instagram.com/p/C9GAp84SPWW/",
    "https://www.instagram.com/p/DJjZATXyi2W/",
    "https://www.instagram.com/p/DQ3zR6-DPGm/",
    "https://www.instagram.com/p/DRPzD6oCLFZ/",
    "https://www.instagram.com/p/DUNGKnBCSdC/",
    "https://www.instagram.com/p/DVOOZXek3sl/",
    "https://www.instagram.com/p/DaU7f-CjE1c/",
    "https://www.instagram.com/p/Db6URBZAWgg/",
    "https://www.instagram.com/p/Be3rTNplCHf/",
    "https://www.instagram.com/p/BsOGulcndj-/",
    "https://www.instagram.com/reel/C8CaBfWs1mr/",
    "https://www.instagram.com/reel/DGyFM8jq-va/",
    "https://www.instagram.com/reel/DKcalTzoftf/",
    "https://www.instagram.com/reel/DMmxU4bKcsR/",
    "https://www.instagram.com/reel/DOuM2pFiEsz/",
    "https://www.instagram.com/reel/DPd8KODDA4d/",
    "https://www.instagram.com/reel/DQCkNLtgqEe/",
    "https://www.instagram.com/reel/DZaO__gO0rz/",
    "https://www.instagram.com/reel/Da6DPjrsSgB/",
    "https://www.instagram.com/reel/DcBx_I1iHZW/",  # NASA
]


def shortcode(url: str) -> str:
    return re.search(r"/(?:p|reels?)/([A-Za-z0-9_-]+)", url).group(1)


# --- workers: each runs in a child process and prints one JSON line ---------

def work_ytdlp(url):
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 20}) as ydl:
        info = ydl.extract_info(url, download=False)
    items = info.get("entries") or [info]
    return {
        "caption_chars": len(info.get("description") or ""),
        "media": sum(1 for i in items if i.get("url") or i.get("formats")),
        "kind": "carousel" if info.get("entries") else "video",
    }


def work_instaloader(url):
    import instaloader

    L = instaloader.Instaloader(quiet=True, max_connection_attempts=1)
    post = instaloader.Post.from_shortcode(L.context, shortcode(url))
    if post.typename == "GraphSidecar":
        media = sum(1 for _ in post.get_sidecar_nodes())
    else:
        media = 1 if (post.video_url if post.is_video else post.url) else 0
    return {
        "caption_chars": len(post.caption or ""),
        "media": media,
        "kind": {"GraphImage": "image", "GraphVideo": "video", "GraphSidecar": "carousel"}.get(post.typename, post.typename),
    }


def work_gallerydl(url):
    # `-j` dumps the extractor's messages as JSON without downloading anything.
    # Type 2 = directory metadata, type 3 = one media file (url, metadata).
    p = subprocess.run([sys.executable, "-m", "gallery_dl", "-j", url], capture_output=True, text=True, timeout=TIMEOUT)
    try:
        msgs = json.loads(p.stdout)
    except json.JSONDecodeError:
        msgs = []
    files = [m for m in msgs if m and m[0] == 3]
    errors = [m for m in msgs if m and m[0] == -1]
    if not files:
        detail = errors[0][1] if errors else None
        raise RuntimeError(json.dumps(detail) if detail else (p.stderr.strip().splitlines() or ["no media returned"])[-1])
    meta = files[0][2]
    return {
        "caption_chars": len(meta.get("description") or ""),
        "media": len(files),
        "kind": "carousel" if len(files) > 1 else ("video" if meta.get("video_url") or meta.get("extension") == "mp4" else "image"),
    }


WORKERS = {"yt-dlp": work_ytdlp, "instaloader": work_instaloader, "gallery-dl": work_gallerydl}


def worker_main(tool, url):
    start = time.monotonic()
    try:
        out = {"ok": True, **WORKERS[tool](url)}
    except Exception as e:  # the error class/message is the result
        msg = str(e).strip().splitlines()[0] if str(e).strip() else ""
        out = {"ok": False, "error": f"{type(e).__name__}: {msg}"[:200]}
    out["secs"] = round(time.monotonic() - start, 2)  # fetch time, excluding interpreter + import startup
    print(json.dumps(out))


# --- driver ------------------------------------------------------------------

def run(tool, url):
    try:
        p = subprocess.run([sys.executable, __file__, "--worker", tool, url], capture_output=True, text=True, timeout=TIMEOUT)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {TIMEOUT}s", "secs": TIMEOUT}
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "error": "worker crashed: " + (p.stderr.strip().splitlines() or [""])[-1][:200], "secs": None}


def main(urls):
    rows = []
    for url in urls:
        row = {"url": url, "type": "reel" if "/reel" in url else "post"}
        for tool in TOOLS:
            r = row[tool] = run(tool, url)
            status = f"ok  {r.get('kind')}, media={r.get('media')}, caption={r.get('caption_chars')}" if r["ok"] else f"ERR {r['error']}"
            print(f"{shortcode(url):14} {row['type']:4} {tool:11} {r['secs']!s:>6}s  {status}", flush=True)
            time.sleep(PAUSE)
        winner = next((t for t in TOOLS if row[t]["ok"]), None)
        tried = TOOLS[: TOOLS.index(winner) + 1] if winner else TOOLS
        row["chain"] = {"ok": bool(winner), "winner": winner, "secs": round(sum(row[t]["secs"] or TIMEOUT for t in tried), 2)}
        rows.append(row)

    print("\nSuccess rate and fetch time (median / max of successful fetches)")
    for kind in ("post", "reel", "all"):
        sub = [r for r in rows if kind == "all" or r["type"] == kind]
        for tool in TOOLS + ["chain"]:
            ok = sorted(r[tool]["secs"] for r in sub if r[tool]["ok"])
            times = f"{ok[len(ok) // 2]:.1f}s / {ok[-1]:.1f}s" if ok else "-"
            print(f"  {kind:4} {tool:11} {len(ok)}/{len(sub)}  {times}")

    out = HERE / "results" / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nwrote {out.relative_to(HERE)}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        worker_main(sys.argv[2], sys.argv[3])
    else:
        main(sys.argv[1:] or DEFAULT_URLS)
