# Experiment: full article text vs. summary as the Graphiti episode body

**Question:** does giving Graphiti the whole cleaned article (Trafilatura
output) extract richer/more entities and facts than the title+summary body
v2 ships with — and is that worth the extra tokens?

Throwaway spike, not production code. Writes into two isolated graphs on the
**production FalkorDB VM** — `experiment_summary` and `experiment_fulltext` —
never the real `second-brain` graph.

## Run it

1. Open a tunnel to FalkorDB (separate from the browser-UI tunnel on 3000):
   ```bash
   gcloud compute ssh falkordb --zone us-central1-a --project=kb-orchestrator-8yuto1 \
     -- -L 6379:localhost:6379 -N &
   ```
2. From this directory:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install "graphiti-core[falkordb]==0.30.2" openai playwright trafilatura lxml_html_clean extruct
   .venv/bin/playwright install chromium
   .venv/bin/python spike.py --url https://example.com/some-post
   ```

Results (gitignored — real article content) land in `results/report.md`.

## Cost

One article costs roughly what M0 measured for the summary variant
(~$0.01–0.02 in OpenAI tokens) plus more for the full-text variant — full
article text is typically 3–8x longer than its summary, so expect
proportionally more input tokens on that side. Trivial against the $5
prepaid credit either way.

## Cleanup

The two experiment graphs are harmless to leave (isolated, small), but to
remove them:
```bash
gcloud compute ssh falkordb --zone us-central1-a --project=kb-orchestrator-8yuto1 --command '
  PW=$(grep -o "requirepass [^ ]*" /etc/systemd/system/falkordb.service | cut -d" " -f2)
  docker exec falkordb redis-cli --no-auth-warning -a "$PW" GRAPH.DELETE experiment_summary
  docker exec falkordb redis-cli --no-auth-warning -a "$PW" GRAPH.DELETE experiment_fulltext'
```
