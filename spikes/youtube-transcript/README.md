# Spike: YouTube captions from a Google Cloud IP

**Question:** can Cloud Run fetch YouTube captions with
[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)
(MIT, pinned `1.2.4`), or does v3 need the home Pi for YouTube? The library's
README warns that YouTube blocks most cloud-provider IPs, and that static
proxies get banned "after extended use" — it recommends paid rotating
residential proxies, which would break the $0 constraint. This spike measures
both the direct path and Webshare's free static proxies from a real GCP IP.

Already confirmed from a home IP (2026-09-26): the Karpathy LLM talk returned
1,704 auto-caption snippets (64K chars), and YouTube's oEmbed endpoint
(`youtube.com/oembed?url=…&format=json`, no auth) gave the title and channel.

## Run it

In [Cloud Shell](https://shell.cloud.google.com) (a GCP IP, free — nothing
touches the production VM or Cloud Run):

```bash
python3 -m venv .venv && .venv/bin/pip install youtube-transcript-api==1.2.4
# Optional, for the proxy half. `read -s` keeps the password off screen and out of history.
export YTT_PROXIES="host1:port1,host2:port2"
export YTT_PROXY_USER="…"
read -s YTT_PROXY_PASS && export YTT_PROXY_PASS
.venv/bin/python spike.py
```

Each line is `ok` with a transcript length, or the exception name —
`RequestBlocked` / `IpBlocked` means YouTube blocked that IP.

## Reading the result

- **Direct works** → YouTube runs on Cloud Run with no proxy and no Pi (re-check over time — blocks come and go).
- **Direct blocked, free proxies work** → Cloud Run + free proxies, with the Pi as the fallback once they get banned.
- **Everything blocked** → YouTube goes through the home Pi, as originally planned.

## Results (2026-09-26, Cloud Shell, GCP IP `35.222.106.82`, no proxy)

| Video | Chars | Run 1 | Run 2 | Home IP |
|---|---|---|---|---|
| `zjkBMFhNj_g` | 62,649 | 4.0s | 4.7s | 0.9s |
| `kCc8FmEb1nY` | 106,036 | 28.6s | 70.9s | 1.0s |
| `aircAruvnKk` | 18,145 | 153.6s | 12.8s | 0.9s |

**Not blocked — 6/6 fetches succeeded with full transcripts.** But slow and
erratic from a cloud IP: 4–154s against ~1s from home. Run 2 started fast
again and didn't climb steadily, so it looks like YouTube deprioritizing a
cloud IP rather than an escalating block. The proxy half wasn't run.

Caveats: six fetches is a snapshot, not a trend, and Cloud Run's egress IPs
aren't Cloud Shell's (same provider, same reputation class).

**Conclusion:** YouTube can run on Cloud Run directly for now — no Pi, no
proxy. Give each fetch its own timeout well inside the 600s request, and
treat `RequestBlocked` / `IpBlocked` / timeout as a normal `failed` job. If
blocks show up in production, the fallbacks in order: Webshare's free
static proxies, then the home Pi.

## Results, part 2 (2026-09-26, production + Webshare free proxies)

**Production Cloud Run is blocked.** The first real YouTube job after deploy
failed in 18s with `RequestBlocked` — Cloud Run's egress IPs are on YouTube's
blocklist even though Cloud Shell's weren't. Cloud Shell was the wrong proxy
for Cloud Run.

**Webshare's free proxies are blocked too.** All 10 free static datacenter
proxies (US, GB, ES, PL, JP, DE; all "valid" per Webshare's API), run from a
home Mac so only the proxy IP differed: 8 → `RequestBlocked`, 2 → `IpBlocked`,
on all three videos. The library README's warning holds: only rotating
*residential* proxies work, and those are paid.

The spike can now read proxies and their credentials from Webshare's API
(`WEBSHARE_API_KEY`) instead of hand-typed values — hand-typed credentials were
the cause of an earlier all-`ProxyError` run.

**Conclusion:** YouTube captions need a residential IP (the home Pi) or a
route that doesn't fetch from our IP at all.
