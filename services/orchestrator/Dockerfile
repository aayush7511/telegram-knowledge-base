# Cloud Run deploy image. The orchestrator renders blog pages with Playwright,
# which needs Chromium + a stack of system libraries. Rather than track a
# specific mcr.microsoft.com/playwright tag (whose bundled browser must match
# the pip Playwright version), we build from a slim Python base and let
# `playwright install --with-deps chromium` pull the exact browser build that
# matches whatever Playwright pip resolves — no image/tag drift.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium

COPY . .

# Cloud Run injects $PORT (defaults to 8080). Same invocation as the Procfile,
# which stays for local buildpack/foreman runs but is ignored once this
# Dockerfile drives the `gcloud run deploy --source` build.
ENV PORT=8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
