# yt-worker

Fetches English YouTube captions from the owner's Mac for `kb-orchestrator`. YouTube blocks Cloud Run's IPs, but a home connection gets captions in about a second. Spec: [specs/youtube-home-worker.md](../../specs/youtube-home-worker.md).

```
kb-orchestrator ──HTTPS + X-KB-Secret──▶ Tailscale Funnel ──▶ 127.0.0.1:8765 (this worker) ──▶ YouTube
```

## Contract

`POST /transcript` with `X-KB-Secret: <YT_WORKER_SECRET>` and `{"video_id": "<11-char id>"}`.

| Outcome | HTTP | Body |
|---|---|---|
| English captions (human-written or auto-generated; `en`, `en-GB`, …) | 200 | `{"status": "ok", "text", "language", "is_generated"}` |
| No captions, or none in English | 200 | `{"status": "no_captions"}` |
| YouTube blocked the request | 200 | `{"status": "blocked"}` |
| Private, deleted, or invalid video | 200 | `{"status": "unavailable"}` |
| Secret missing or wrong | 401 | — |

Every real answer is a 200, so Cloud Run treats anything else (Funnel's 502 when the Mac is asleep, a 500 from a crash, a timeout after 30s) as unreachable and retries the job later.

`YT_WORKER_SECRET` is its own value, not the same as `X-KB-Secret` elsewhere: this box is the least protected in the system, so a leak here opens nothing else.

## Develop

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx
.venv/bin/python -m pytest
```

## Install on the Mac (one time)

1. Build the venv (above, without the test packages if you like).
2. Make the secret and install the LaunchAgent (starts at login, restarts on exit). Run from this directory:
   ```bash
   SECRET=$(openssl rand -hex 32)
   sed -e "s|__DIR__|$PWD|g" -e "s|__SECRET__|$SECRET|g" com.kb.yt-worker.plist > ~/Library/LaunchAgents/com.kb.yt-worker.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kb.yt-worker.plist
   ```
   Keep `$SECRET` for step 4 (`echo $SECRET` in the same shell); it isn't stored anywhere else.
3. Expose it with Tailscale Funnel (free personal plan; Funnel must be enabled for the tailnet in the admin console):
   ```bash
   tailscale funnel --bg 8765
   ```
   The public URL is `https://<mac>.<tailnet>.ts.net`.
4. Point Cloud Run at it — see "YouTube home worker" in [services/orchestrator/README.md](../orchestrator/README.md#youtube-home-worker).

Check it's up: `curl -s -X POST localhost:8765/transcript` should return 401. Logs: `/tmp/kb-yt-worker.log`. Restart: `launchctl kickstart -k gui/$(id -u)/com.kb.yt-worker`.

The Mac may sleep: a sleeping Mac is just "unreachable", and the job is retried (up to 3 times, an hour apart, 6 a.m.–midnight Chicago time).
