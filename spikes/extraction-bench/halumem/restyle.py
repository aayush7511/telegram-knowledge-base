"""Rewrite each sampled session's gold memories in Graphiti's fact style -> styled.json (for MODE=goldstyled).

Same information, Graphiti's shape: short atomic facts, person by first name, one fact per line.
Uses gpt-4.1-mini (free data-sharing tokens); temperature 0.
"""
import json
import os
from pathlib import Path

from openai import OpenAI

import run_sample

PROMPT = """Rewrite these memories the way a knowledge-graph extractor (Graphiti) writes facts:
- split each memory into short atomic facts, one per line
- refer to the person by first name only (e.g. "Martin", not "Martin Mark")
- keep every detail and date exactly as given; add nothing, drop nothing
Return JSON: {{"facts": ["...", "..."]}}

MEMORIES:
{memories}"""

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
styled = {}
for u, user in zip(run_sample.RUNS, run_sample.build_users()):
    for i, s in zip(user["picked"], user["sessions"]):
        gold = [m["memory_content"] for m in s["memory_points"] if m["memory_source"] != "interference"]
        r = client.chat.completions.create(
            model="gpt-4.1-mini-2025-04-14", temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": PROMPT.format(memories="\n".join(f"- {g}" for g in gold))}])
        styled[f"{u}-{i}"] = json.loads(r.choices[0].message.content)["facts"]
Path("styled.json").write_text(json.dumps(styled, indent=1))
print(sum(len(v) for v in styled.values()), "styled facts from", len(styled), "sessions")
