"""Synthetic memory dataset generator (spike; plan: specs/memory-dataset-generation.md).

Decide the story first, then write conversations that reveal it, so the gold memories and the
question answers are known by construction. Stages per user:

  1. persona   one call: a person card, seeded from our own attribute lists
  2. timeline  one call: dated sessions, each with structured memory points (some replace older ones)
               and distractors that must NOT be remembered
  3. dialogue  one call per session (in parallel): persona + "story so far" + this session's plan.
               The story so far is computed from the plan in code, so sessions don't depend on each other
  4. questions one call: questions whose answers come from the plan
  5. check     one call per session: does the dialogue reveal each memory point, and keep distractors
               out of the user's own facts?

    GEN_MODEL=deepseek-ai/DeepSeek-V4.1-Flash RUN=ds python gen.py --users 1 --sessions 20

Env: GEN_BASE_URL (default DeepInfra), GEN_MODEL, GEN_KEY_ENV (default DEEPINFRA_API_KEY), RUN (output folder).
"""
import argparse
import asyncio
import json
import os
import random
import re

import validate
from datetime import datetime, timedelta
from pathlib import Path

from openai import AsyncOpenAI

HERE = Path(__file__).parent
OUT = HERE / "out"  # set in main()

# Our own seed lists (not HaluMem's): enough spread that people differ in life stage, place and work.
COUNTRIES = ["United States", "India", "Brazil", "Germany", "Nigeria", "Japan", "Mexico", "Canada", "Kenya",
             "Australia", "Philippines", "Poland", "Egypt", "South Korea", "Spain"]
FIELDS = ["nursing", "software", "teaching", "construction", "retail", "law", "farming", "graphic design",
          "logistics", "restaurant kitchen", "accounting", "research lab", "film production", "civil service"]
STAGES = ["college student", "early career", "mid career with young kids", "career changer",
          "recently retired", "freelancer", "small business owner"]
GENDERS = ["woman", "man", "woman", "man", "non-binary person"]
AGES = ["19-24", "25-32", "33-45", "46-60", "61-75"]
TRAITS = ["anxious planner", "spontaneous", "dry humor", "competitive", "very private", "chatty",
          "health-focused", "frugal", "night owl", "family-first", "ambitious", "easily distracted"]

PERSONA = """Invent one realistic person for a long-term chat-assistant memory dataset.
Seed: a {gender} aged {age}; lives in {country}; works in {field}; life stage: {stage}; personality: {traits}.
Return JSON:
{{"name": full name, "gender": "...", "birth_date": "YYYY-MM-DD", "city": "...", "job": "...", "employer": "...",
  "family": [{{"relation": "...", "name": "...", "detail": "..."}}], "health": "...", "hobbies": ["..."],
  "preferences": ["concrete likes/dislikes"], "goals": ["..."], "personality": "...",
  "speaking_style": "how they TEXT a chat assistant: casual, e.g. message length, punctuation, humor, typos (English only)"}}"""

TIMELINE = """Plan {n} chat sessions between this person and their AI assistant, spread over about {months} months
starting {start}. This plan is the ground truth for a memory benchmark.

PERSON:
{persona}

Rules:
- Session 1 introduces core facts about the person (name, city, job, family, a few preferences).
- Each session has a topic and 2-6 memory points the person reveals in it.
- At least {updates} memory points across the plan CHANGE an earlier one (moves city, changes job, new
  relationship status, changed preference, health change, plan completed or abandoned). Those set
  "replaces" to the id of the memory point they supersede.
- Each session also has 1-2 distractors: a FALSE statement about the person that a careless memory system
  might store, plus how it comes up without being true. Example: {{"claim": "Ana is learning Spanish",
  "how": "the assistant suggests a Spanish course; Ana says she has no time"}}. Sources: the assistant's
  suggestions, a friend's situation, a hypothetical, something the person rejects.
- Mix types: "persona" (lasting traits/facts), "event" (things that happen), "relationship" (people in their life).
- Memory point fields: id ("m1", "m2", ... unique across the plan), type, subject (full entity name),
  relation (UPPER_SNAKE_CASE), object (entity or value), fact (one standalone sentence using the person's
  full name; give an absolute date only when something started, changed or happened then, e.g. "moved to
  Austin on 2026-03-14"; never "As of <date>, ..." for standing facts), replaces (id or null),
  importance (0.25, 0.5, 0.75 or 1.0).
Return JSON: {{"sessions": [{{"index": 1, "date": "YYYY-MM-DD", "topic": "...",
  "memory_points": [{{"id": "m1", "type": "...", "subject": "...", "relation": "...", "object": "...",
                     "fact": "...", "replaces": null, "importance": 0.75}}],
  "distractors": [{{"claim": "...", "how": "..."}}]}}]}}"""

DIALOGUE = """Write a chat between {name} (role "user") and their AI assistant (role "assistant") on {date}.

PERSON: {persona_short}
WHAT THE ASSISTANT ALREADY KNOWS FROM EARLIER CHATS (don't repeat it unless natural):
{story}

THIS SESSION — topic: {topic}
The user must reveal each of these naturally, in their own words (not as a list, not all in one message):
{points}
These claims must come up as described but must stay FALSE about the user (never confirmed by them):
{distractors}

{turns} turns total, alternating user/assistant, starting with the user. The user TEXTS like a real person on
their phone: short messages, contractions, casual phrasing, fragments, typos or lowercase are fine, small talk
and asides are fine, details come out in passing rather than as announcements. Never formal requests ("I would
like guidance on...", "Please provide...", "Could you give me a rough estimate"). Their style: "{style}".
The assistant is friendly and concise. Write the whole chat in plain ENGLISH: no words
from other languages, even if the person is from another country. Dates relative to {date} are fine in speech.
Return JSON: {{"turns": [{{"role": "user", "content": "..."}}, {{"role": "assistant", "content": "..."}}]}}"""

QUESTION_TYPES = {
    "recall": "a stated fact",
    "update": "the CURRENT value of something that changed (answer = latest version)",
    "boundary": 'something plausible that was never stated (answer: "Unknown")',
    "multi_hop": "needs two memory points combined",
    "temporal": "when something happened (answer: an absolute date)",
}

QUESTIONS = """Write {n} memory-test questions of type "{qtype}" ({desc}) about {name}, answerable after
reading all their chats. Use only this plan (ground truth). Keep answers short.
PLAN (latest memory points win when they replace older ones):
{plan}
Return JSON: {{"questions": [{{"question": "...", "answer": "...", "type": "...", "evidence": ["m3", "m9"]}}]}}"""

CHECK = """Check a chat against its plan.
CHAT:
{dialogue}

For each MEMORY POINT, does the USER (not only the assistant) convey it? Paraphrase counts. Relative or
partial dates count ("on Saturday", "last week", "July 10" for 2026-07-10): only the substance must be there.
Mark a memory missing only if its substance is absent from what the user says.
{points}
For each FALSE CLAIM, did the user state or confirm it as true about themselves? (Discussing and
rejecting it, or the assistant suggesting it, is NOT a leak.)
{distractors}
Also: does anything the user says CONTRADICT a memory point (e.g. plan says co-owner, user says sole owner)?
Return JSON: {{"missing": [ids of memory points NOT revealed], "leaked": [indexes (1-based) of false claims the
user stated or confirmed], "contradicted": [ids of memory points the chat contradicts]}}"""


class Gen:
    def __init__(self, model: str, base_url: str, key: str):
        self.model, self.client = model, AsyncOpenAI(api_key=key, base_url=base_url, timeout=300, max_retries=3)
        self.usage = {"calls": 0, "in": 0, "out": 0}
        self.sem = asyncio.Semaphore(int(os.environ.get("CONCURRENCY", "8")))

    async def json(self, prompt: str, temperature: float, max_tokens: int) -> dict:
        try:
            return await self._json(prompt, temperature, max_tokens)
        except RuntimeError as e:
            if "truncated" not in str(e):
                raise
            return await self._json(prompt, 0.0, max_tokens)  # loops are usually sampling; retry greedy once

    async def _json(self, prompt: str, temperature: float, max_tokens: int) -> dict:
        async with self.sem:
            r = await self.client.chat.completions.create(
                model=self.model, temperature=temperature, max_tokens=max_tokens,
                response_format={"type": "json_object"}, messages=[{"role": "user", "content": prompt}],
                extra_body={"reasoning_effort": os.environ.get("REASONING", "low")} if "gpt-oss" in self.model  # can't switch reasoning off
                else {"chat_template_kwargs": {"enable_thinking": False}})
        if r.choices[0].finish_reason == "length":
            dump = OUT / f"truncated-{self.usage['calls']}.txt"  # keep the looping answer for inspection
            dump.write_text(prompt[-2000:] + "\n\n===== ANSWER =====\n" + (r.choices[0].message.content or ""))
            self.usage["calls"] += 1
            self.usage["in"] += r.usage.prompt_tokens
            self.usage["out"] += r.usage.completion_tokens
            raise RuntimeError(f"answer hit max_tokens={max_tokens} (truncated, saved {dump.name})")
        if r.model != self.model:  # hosts may redirect retired models (DeepInfra did on 2026-10-17)
            raise RuntimeError(f"asked for {self.model}, served {r.model}")
        self.usage["calls"] += 1
        self.usage["in"] += r.usage.prompt_tokens
        self.usage["out"] += r.usage.completion_tokens
        return json.loads(r.choices[0].message.content)


BUDGET_STOP = float(os.environ.get("BUDGET_STOP", "19"))


def modal_spend() -> float | None:
    """This month's Modal usage in dollars (free CLI query), or None if it can't be read."""
    import subprocess
    try:
        out = subprocess.run(["modal", "billing", "summary"], capture_output=True, text=True, timeout=60).stdout
        return float(re.search(r"Metered Cost:\s*([\d.]+)", out).group(1))
    except Exception:
        return None


def hard_problems(s: dict) -> list[str]:
    """Problems that keep a session out of the dataset unless a regenerated chat fixes them."""
    c, out = s.get("check", {}), []
    if c.get("contradicted"):
        out.append(f"contradicts {c['contradicted']}")
    if c.get("leaked"):
        out.append(f"leaked false claims {c['leaked']}")
    # "missing" is only a flag (s["check"]): the checker was wrong 10/10 times on it in the 2026-10-18 test
    day = datetime.strptime(s["date"], "%Y-%m-%d").date()
    for t in s["dialogue"]:
        if t["role"] == "user" and any(d.date() > day for d in validate.dates_in(t["content"])):
            out.append("user mentions a future date")
            break
    if not s["dialogue"] or s["dialogue"][0]["role"] != "user":
        out.append("chat doesn't start with the user")
    return out


def fix_plan(sessions: list[dict], min_updates: int) -> tuple[list[dict], list[str]]:
    """Repair what code can (dates), report what it can't (validate.py's hard rules on the plan)."""
    sessions = sorted(sessions, key=lambda s: s.get("index", 0))
    prev = None
    for s in sessions:  # a session can't plan something after its own date: move the session to that day
        day = datetime.strptime(s["date"], "%Y-%m-%d")
        latest = max([d for p in s["memory_points"] for d in validate.dates_in(p["fact"])], default=None)
        if latest and latest > day:
            day = latest
        if prev and day <= prev:
            day = prev + timedelta(days=1)
        s["date"], prev = day.strftime("%Y-%m-%d"), day
    problems = [line for k, v in validate.check_user({"sessions": [{**s, "dialogue": [{"role": "user", "content": "x"}]}
                                                                    for s in sessions]}, min_updates).items()
                if k in ("plan", "updates") for line in v]
    for s in sessions:  # downstream code expects one id or None (a multi-id list is reported above, first kept)
        for p in s["memory_points"]:
            p["replaces"] = next(iter(validate.replaces_list(p)), None)
    return sessions, problems


def story_so_far(sessions: list[dict], upto: int) -> str:
    """Latest version of every memory point revealed before session `upto` (replaced ones dropped)."""
    points = [p for s in sessions if s["index"] < upto for p in s["memory_points"]]
    replaced = {p["replaces"] for p in points if p.get("replaces")}
    lines = [f"- {p['fact']}" for p in points if p["id"] not in replaced]
    return "\n".join(lines) or "(nothing yet: this is the first chat)"


def timestamps(date: str, n: int, rng: random.Random) -> list[str]:
    t = datetime.strptime(date, "%Y-%m-%d") + timedelta(hours=rng.randint(7, 21), minutes=rng.randint(0, 59))
    out = []
    for _ in range(n):
        out.append(t.strftime("%b %d, %Y, %H:%M:%S"))  # HaluMem's timestamp format
        t += timedelta(seconds=rng.randint(20, 240))
    return out


async def make_user(g: Gen, uid: int, n_sessions: int, rng: random.Random) -> dict:
    seed = dict(gender=rng.choice(GENDERS), age=rng.choice(AGES), country=rng.choice(COUNTRIES),
                field=rng.choice(FIELDS), stage=rng.choice(STAGES), traits=", ".join(rng.sample(TRAITS, 2)))
    if (OUT / f"user{uid}.json").exists():  # resume: finished user
        return json.loads((OUT / f"user{uid}.json").read_text())
    saved = OUT / f"user{uid}-sessions.json"
    if saved.exists():  # resume: sessions done, questions missing
        partial = json.loads(saved.read_text())
        return await add_questions(g, partial)
    persona = await g.json(PERSONA.format(**seed), 0.9, 2000)
    start = (datetime(2025, 9, 1) + timedelta(days=rng.randint(0, 120))).strftime("%Y-%m-%d")
    min_updates = max(3, n_sessions * 2 // 5)
    best = None
    for attempt in range(3):  # a plan is one call: retry it rather than write chats on a broken plan
        plan = await g.json(TIMELINE.format(n=n_sessions, months=max(3, n_sessions // 2), start=start,
                                            persona=json.dumps(persona), updates=min_updates), 0.8, 16000)
        sessions, problems = fix_plan(plan["sessions"], min_updates)
        if best is None or len(problems) < len(best[1]):
            best = (sessions, problems)
        if not problems:
            break
    sessions, plan_problems = best
    style = persona.get("speaking_style", "casual")
    short = f"{persona['name']}, {persona.get('job', '')} in {persona.get('city', '')}; {persona.get('personality', '')}"

    async def one(s: dict) -> dict:
        best = None
        for attempt in range(2):  # regenerate the chat once if it has hard problems
            out = await write_and_check(s)
            problems = hard_problems(out)
            if best is None or len(problems) < len(best[1]):
                best = (out, problems)
            if not problems:
                break
        out, problems = best
        return {**out, "problems": problems, "excluded": bool(problems)}

    async def write_and_check(s: dict) -> dict:
        points = "\n".join(f"- {p['fact']}" for p in s["memory_points"])
        distr = "\n".join(f"- claim: {d['claim']} | how it comes up: {d['how']}" for d in s["distractors"]) or "(none)"
        d = await g.json(DIALOGUE.format(name=persona["name"], date=s["date"], persona_short=short,
                                         story=story_so_far(sessions, s["index"]), topic=s["topic"], points=points,
                                         distractors=distr, turns=rng.choice([10, 12, 14, 16]), style=style), 0.8, 6000)
        turns = []
        for t in d["turns"]:  # drop junk, merge a speaker's consecutive lines into one message
            if t.get("role") not in ("user", "assistant") or not t.get("content"):
                continue
            if turns and turns[-1]["role"] == t["role"]:
                turns[-1]["content"] += "\n" + t["content"]
            else:
                turns.append({"role": t["role"], "content": t["content"]})
        for t, ts in zip(turns, timestamps(s["date"], len(turns), rng)):
            t["timestamp"] = ts
        chat = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
        c = await g.json(CHECK.format(dialogue=chat,
                                      points="\n".join(f"{p['id']}: {p['fact']}" for p in s["memory_points"]),
                                      distractors="\n".join(f"{i + 1}. {x['claim']}" for i, x in enumerate(s["distractors"]))
                                      or "(none)"), 0.0, 4000)  # gpt-oss reasoning counts toward the cap
        return {**s, "dialogue": turns, "check": c}

    done = await asyncio.gather(*(one(s) for s in sessions))
    partial = {"user_id": uid, "seed": seed, "persona": persona, "sessions": done, "plan_problems": plan_problems}
    (OUT / f"user{uid}-sessions.json").write_text(json.dumps(partial, indent=1, ensure_ascii=False))
    return await add_questions(g, partial)


async def add_questions(g: Gen, user: dict) -> dict:
    sessions = user["sessions"]
    plan_text = "\n".join(f"{p['id']} [{s['date']}] {p['fact']}" + (f" (replaces {p['replaces']})" if p.get("replaces") else "")
                          for s in sessions for p in s["memory_points"])
    questions, failed = [], []
    for qtype, desc in QUESTION_TYPES.items():  # small batches: one long answer looped on some plans
        try:
            qs = await g.json(QUESTIONS.format(n=4, qtype=qtype, desc=desc, name=user["persona"]["name"],
                                               plan=plan_text), 0.3, 2000)
            questions += [{**q, "type": qtype} for q in qs["questions"]]
        except RuntimeError as e:  # questions only feed the end-to-end test: log and keep going
            failed.append(qtype)
            print(f"  questions[{qtype}] for {user['persona']['name']} failed: {e}")
    full = {**user, "questions": questions, "questions_failed": failed}
    (OUT / f"user{user['user_id']}.json").write_text(json.dumps(full, indent=1, ensure_ascii=False))
    return full


async def main(n_users: int, n_sessions: int) -> None:
    for line in (HERE.parent / "extraction-bench" / ".env").read_text().splitlines():  # reuse the bench keys
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    model = os.environ["GEN_MODEL"]
    g = Gen(model, os.environ.get("GEN_BASE_URL", "https://api.deepinfra.com/v1/openai"),
            os.environ[os.environ.get("GEN_KEY_ENV", "DEEPINFRA_API_KEY")])
    global OUT
    out = OUT = HERE / "out" / os.environ.get("RUN", "run")
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(int(os.environ.get("SEED", "1")))  # same seed -> same person seed for both models
    base = int(os.environ.get("SEED", "1"))
    lanes = asyncio.Semaphore(int(os.environ.get("USERS_AT_ONCE", "1")))

    async def lane(u: int) -> dict | None:
        async with lanes:
            spent = modal_spend() if "modal.run" in g.client.base_url.host else None
            if spent is not None and spent >= BUDGET_STOP:
                print(f"user{u}: skipped, Modal usage ${spent:.2f} >= ${BUDGET_STOP} (resume after the credit resets)")
                return None
            return await make_user(g, u, n_sessions, random.Random(base * 1000 + u))
    users = [u for u in await asyncio.gather(*(lane(u) for u in range(n_users))) if u]
    (out / "users.json").write_text(json.dumps(users, indent=1, ensure_ascii=False))
    (out / "usage.json").write_text(json.dumps({"model": model, **g.usage}, indent=1))
    for u in users:
        ss = u["sessions"]
        n_points = sum(len(s["memory_points"]) for s in ss)
        missing = sum(len(s["check"].get("missing", [])) for s in ss)
        leaked = sum(len(s["check"].get("leaked", [])) for s in ss)
        print(f"{u['persona']['name']}: {len(ss)} sessions, {n_points} memory points "
              f"({sum(1 for s in ss for p in s['memory_points'] if p.get('replaces'))} updates), "
              f"{sum(len(s['dialogue']) for s in ss)} turns, check: {missing} missing, {leaked} leaked; "
              f"{len(u['questions'])} questions; excluded {sum(1 for s in ss if s.get('excluded'))} sessions "
              f"{[(s['index'], s['problems']) for s in ss if s.get('excluded')]}")
    print("usage:", g.usage)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=1)
    ap.add_argument("--sessions", type=int, default=20)
    a = ap.parse_args()
    asyncio.run(main(a.users, a.sessions))
