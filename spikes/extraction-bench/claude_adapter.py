"""OpenAI-compatible /v1/chat/completions that answers with `claude -p` on the Claude subscription,
so a frontier reference run doesn't spend OpenRouter credit.

    ../../services/orchestrator/.venv/bin/python claude_adapter.py   # serves 127.0.0.1:8787

Each call runs headless Claude Code with no tools and no MCP servers (an empty --mcp-config with
--strict-mcp-config: otherwise every connected server's tool definitions ride along, ~287K tokens
per call). The JSON schema is described in the prompt (Graphiti adds it too); bench.py's wrapper
retries answers that aren't a valid instance.
"""
import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
import uvicorn

HERE = Path(__file__).parent
CLAUDE = os.environ.get("CLAUDE_BIN", str(Path.home() / ".nvm/versions/node/v20.19.4/bin/claude"))
MODEL = os.environ.get("CLAUDE_MODEL", "opus")
EMPTY_MCP = HERE / "results" / "empty-mcp.json"
LIMIT = asyncio.Semaphore(int(os.environ.get("CLAUDE_CONCURRENCY", "4")))
WORKDIR = tempfile.mkdtemp(prefix="claude-adapter-")  # outside the repo, so no project CLAUDE.md is loaded

app = FastAPI()


def _text(content) -> str:
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    system = "\n\n".join(_text(m["content"]) for m in body["messages"] if m["role"] == "system")
    convo = "\n\n".join(f"[{m['role']}]\n{_text(m['content'])}" for m in body["messages"] if m["role"] != "system")
    rf = body.get("response_format") or {}
    if rf.get("type") == "json_schema":
        convo += ("\n\nReply with ONLY a JSON object that is a valid instance of this JSON schema "
                  f"(fill in the fields; do not repeat the schema):\n{json.dumps(rf['json_schema']['schema'])}")
    elif rf.get("type") == "json_object":
        convo += "\n\nReply with ONLY a JSON object."
    sys_prompt = (system + "\n\n" if system else "") + "Output only the requested JSON, no prose, no code fences."

    async with LIMIT:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE, "-p", "--model", MODEL, "--output-format", "json", "--system-prompt", sys_prompt,
            "--tools", "", "--mcp-config", str(EMPTY_MCP), "--strict-mcp-config",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=WORKDIR, env={**os.environ, "PATH": f"{Path(CLAUDE).parent}:{os.environ['PATH']}"},
        )
        out, err = await proc.communicate(convo.encode())
    raw = out.decode().strip().splitlines()
    d = json.loads(raw[-1]) if raw else {}
    text = (d.get("result") or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    u = d.get("usage") or {}
    prompt_tokens = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion", "created": int(time.time()),
        "model": ",".join((d.get("modelUsage") or {}).keys()) or MODEL,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": u.get("output_tokens") or 0,
                  "total_tokens": prompt_tokens + (u.get("output_tokens") or 0)},
        "api_equivalent_usd": d.get("total_cost_usd"),
    }


if __name__ == "__main__":
    EMPTY_MCP.write_text('{"mcpServers":{}}')
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")
