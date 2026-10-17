# Spike: Instagram posts and reels without a login

**Question:** can the pipeline read Instagram with no logged-in session, and
from which IPs? The v3 design doc deferred Instagram to v4 on the assumption
that Instagram's anti-scraping had broken every open-source tool and only a
logged-in Chrome would work. This spike tests that assumption
with yt-dlp, instaloader, and gallery-dl, tried in that order as a fallback
chain.

Each tool runs in its own subprocess, fetches metadata only (caption + media
URLs, no download), and gets a 60s timeout. The timing covers the fetch alone,
not interpreter startup. The chain's time is the sum of the attempts up to the
first success. There's a 2s pause between requests.

URLs: 10 posts (`/p/`) and 10 reels (`/reel/`), public and high-profile, taken
from Wikipedia's most-viewed-reels and most-liked-posts lists. The `/p/` set
mixes videos, single images, and image carousels.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install yt-dlp==2026.8.19 instaloader==4.15.3 gallery-dl==1.32.14
.venv/bin/python spike.py              # the built-in URLs
.venv/bin/python spike.py <url> ...    # any others
```

Writes `results/<timestamp>.json`. `SPIKE_TOOLS=yt-dlp,instaloader` limits the
run to those tools, in that order.

**From Cloud Run** (a one-off job, deleted afterwards): the job runs the public
`python:3.12-slim` image from Docker Hub, so nothing is pushed to Artifact
Registry. The script goes in as a base64 environment variable. Use `~` as the
args delimiter, because the shell command itself contains `|`:

```bash
B64=$(base64 -i spike.py | tr -d '\n')
CMD='mkdir -p /w/results && echo "$SPIKE_B64" | base64 -d > /w/spike.py && pip install -q yt-dlp==2026.8.19 instaloader==4.15.3 gallery-dl==1.32.14 && python /w/spike.py'
gcloud run jobs deploy ig-spike --region us-central1 --image docker.io/library/python:3.12-slim \
  --command sh --args="^~^-c~$CMD" --set-env-vars="^|^SPIKE_TOOLS=yt-dlp,instaloader|SPIKE_B64=$B64" \
  --task-timeout 20m --max-retries 0 --memory 1Gi
gcloud run jobs execute ig-spike --region us-central1 --wait
gcloud run jobs delete ig-spike --region us-central1
```

The results table goes to the job's logs in Cloud Logging.

## Results (2026-09-30, no login, no cookies)

Success rate, with median / max fetch time over the successful fetches:

| Tool | Where | Posts | Reels |
|---|---|---|---|
| yt-dlp | Home IP | 3/10 · 1.5s / 2.7s | 9/10 · 1.6s / 2.4s |
| | Cloud Shell (`34.66.66.210`) | 3/10 · 1.7s / 1.7s | 9/10 · 1.9s / 2.2s |
| | **Cloud Run** (`136.124.33.140`) | 3/10 · 1.6s / 1.9s | 9/10 · 1.6s / 1.8s |
| instaloader | Home IP | **10/10** · 3.0s / 8.5s | **10/10** · 8.2s / 21.2s |
| | Cloud Shell | **10/10** · 2.3s / 8.0s | **10/10** · 8.3s / 25.6s |
| | **Cloud Run** | **10/10** · 1.9s / 6.0s | **10/10** · 5.8s / 18.4s |
| gallery-dl | Home IP | 0/10 | 0/10 |
| | Cloud Shell | 0/10 | 0/10 |
| | Cloud Run | not run | not run |
| **Chain** | Home IP | **10/10** · 2.8s / 9.9s | **10/10** · 1.7s / 3.6s |
| | Cloud Shell | **10/10** · 3.4s / 9.8s | **10/10** · 1.9s / 10.2s |
| | **Cloud Run** | **10/10** · 2.6s / 6.0s | **10/10** · 1.7s / 3.5s |

**All three places gave the same results, including production Cloud Run.**
Nothing was blocked, and every URL returned its full caption and media URLs.
This is unlike YouTube, which blocks Cloud Run. The Cloud Run run was a
one-off job in `us-central1`, the orchestrator's region. It had no VPC
connection, which gives it the same kind of internet egress as the
orchestrator (the orchestrator's VPC egress is `private-ranges-only`).
gallery-dl was skipped there because it can't work without a login.

- **yt-dlp is video-only, not blocked.** Every failure was a photo: `There is
  no video in this post` (single images) or `No video formats found!` (image
  carousels). It returned every video, and it's the fastest tool at ~1.5–2s.
  The one "reel" it missed (`DOuM2pFiEsz`) is actually an image.
- **instaloader handles everything.** Images, videos, and carousels (up to 8
  items), with captions up to 1,207 chars. It's slower on videos (median ~8s,
  worst 25.6s), where it seems to make extra requests.
- **gallery-dl needs a login.** At home every request redirected to
  `/accounts/login/` within a second. On GCP every request hit the 60s
  timeout, probably retrying the same redirect. It adds nothing as a
  no-login fallback, and on GCP each attempt costs 60s.
- **The chain works because the two tools cover each other.** yt-dlp takes the
  videos fast. Its photo failures come back in ~1.7s, and instaloader picks up
  the photos. Worst case was 10.2s.

Caveats: 20 URLs × 3 runs is a snapshot, not a trend. These are all
high-profile public accounts. Instagram's limits are per IP and tighter for
anonymous traffic, so heavy use may still hit 429s or the login wall. Cloud
Run's egress IPs are shared with other GCP customers, so their reputation can
change. That's why YouTube ended up behind a block (see
[youtube-transcript](../youtube-transcript/README.md#results-part-2-2026-09-26-production--webshare-free-proxies)).

**Conclusion:** Instagram metadata (caption + media URLs) works from Cloud Run
with no login and no third-party API. The chain should be yt-dlp →
instaloader, without gallery-dl. The v4 design assumption ("only a logged-in
Chrome works") doesn't hold for public posts and reels today. Still to check:
whether media downloads (the reel's audio for transcription, not just
metadata) go through from Cloud Run.
