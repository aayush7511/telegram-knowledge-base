---
name: kb-memory
description: Tailor answers to the user with their personal knowledge base (the kb-memory MCP server's search_memory tool), which holds what they chose to save as worthwhile — articles, videos, posts, papers, repos, and notes. Use it whenever the best answer depends on who this user is — recommendations ("what should I read/learn/build next"), advice on their career, projects, or learning path, "based on what I've been saving", comparisons against sources they've kept, or explanations that could point to material they already flagged — even when they never mention the knowledge base. It's one source among several: combine it with your own knowledge, web search, and the codebase, never limit the answer to it.
---

# Tailoring answers with the knowledge base

The user keeps a personal knowledge graph: everything they send their Telegram bot, or save through `save_to_memory`, is fetched, summarized, and broken into facts. Use it to make answers fit this person, not to replace what you'd otherwise say.

**Saved doesn't mean read.** People save things to come back to: a paper they mean to get through, a repo that looked promising, a video for later. An item in the knowledge base tells you the user judged it *worth keeping*, which makes it a strong signal of what they care about and a good place to look, but not proof they've read it, remember it, or agree with it. So treat the knowledge base as their curated shelf, not a record of what they know.

## When to search

Ask yourself: *would knowing what this person has saved or noted change my answer?* If yes, search before answering.

- **Search:** "what should I learn next about agents?", "is this approach a good idea for my project?", "recommend some papers on RL", "how does X compare to that article I saved about Y?", "explain transformers" (they may have saved the paper or a good explainer worth pointing back to), "help me prepare for ML interviews".
- **Don't search:** a self-contained task where personal context can't matter — fix this stack trace, convert this date, write a regex, run the tests. Searching there wastes a call and invites irrelevant asides.

When in doubt and the question is about the user's interests, work, or learning, search: it's one cheap call.

## How to search

- Run 1–3 short, topical queries, not the user's whole message: `agent memory`, `reinforcement learning`, `ML interview preparation`. Keywords and short phrases match best; different angles on the topic catch more than one long query.
- `limit` 10 is usually enough; go higher only when surveying a broad area ("what have I been into?").
- Results are always the *nearest* facts, even when nothing relevant exists. Read them critically and drop anything that isn't really about the question. An empty-handed search is normal — then just answer without the knowledge base, and don't mention the miss unless the user asked about their knowledge base directly.
- Each fact has a source (title, link) and a saved date; `No longer true as of …` marks a fact that was later superseded. Check dates when recency matters.

## How to use what you find

Blend it into a complete answer. The knowledge base tells you *what the user finds worthwhile*; your own knowledge, web search, and the codebase supply *the rest*.

- Point them back to their own sources: when a saved item answers part of the question, name it — it's something they already judged worth their time, maybe still unread. "The Transformer paper you saved covers exactly this in section 3" is more useful than a generic reading list.
- Connect rather than assume: link new material to what they saved, and note where something extends or contradicts it. Don't skip the basics on the grounds that they saved a source on the topic — ask or pitch the explanation from what they've said, not from what they've kept.
- Fill the gaps freely: if they ask for recommendations, suggest things that aren't in the knowledge base — that's usually the point. Items they've saved but may not have gotten to can be part of the plan ("start with the Weng article you saved, then …").
- Don't let the knowledge base narrow the answer: a few saved items about agents doesn't mean every answer should be about agents.

## Say what came from the knowledge base

Make it clear which parts of the answer come from their saved material, so they can tell their own sources from your general knowledge. Name the source and link it:

> From your knowledge base: you saved Lilian Weng's ["LLM Powered Autonomous Agents"](https://lilianweng.github.io/posts/2023-06-23-agent/), which covers planning with LLM+P — worth reading before …

Describe it as what they *saved*, never as what they read or believe: "you saved Karpathy's 2025 year-in-review", not "as you read in Karpathy's review" or "you're really into LLMs". One saved article is a hint, not an identity.

## Saving

`save_to_memory` adds to their graph and posts in their Telegram chat, so call it only when the user asks to save or remember something. Don't save things on your own initiative.

## If the tool fails

A tool error or a daily-limit message just means answering without the knowledge base this time. Say so in one short line only if the user was relying on it ("I couldn't reach your knowledge base just now").
