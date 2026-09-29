# Spike: long-form X content through FxTwitter

**Question:** is [FxTwitter](https://github.com/FxEmbed/FxEmbed)'s free,
no-login API enough for X, including long posts, threads, and X Articles? Or
do we need twitter-cli with a throwaway account's cookies?

API: v2, documented by the OpenAPI spec in the FxEmbed repo
(`docs/specs/fxtwitter-openapi.json`). The relevant endpoints are
`GET /2/status/{id}` and `GET /2/thread/{id}`, which unrolls the author's
thread and also returns the post itself.

## Run it

```bash
python3 spike.py              # the built-in sample posts
python3 spike.py <post_id>    # any others
```

Standard library only.

## Results (2026-09-26, home IP and Cloud Shell GCP IP)

| Post | Kind | Result |
|---|---|---|
| Karpathy, "2025 LLM Year in Review" | X Article | Full text: 10,201 chars in 33 blocks, through to the last line, with inline links |
| The Neuron newsletter | X Article | Full text: **80,095 chars** in 336 blocks |
| Karpathy, vibe-coding retrospective | Long post | Full 1,677 chars, not truncated at 280 |
| Karpathy, nanochat | Thread (3 posts) | All 3 posts, author only, in order. Linking the middle or last post returns the same full thread |
| Sam Altman | Long post + self-reply | Both posts |
| James Zou | Post that's mostly a link | 138 chars; `t.co` link expanded to the real NYT URL; `embed_card` and `quote` present |
| Nonexistent ID | — | Clean `404` with `{"code":404}` |

Every call took 1–3s, **from the GCP IP too — no throttling**, unlike YouTube.

**Conclusion: FxTwitter is enough; twitter-cli isn't needed.** Caveats:
- **Articles arrive as rich-text blocks, not plain text.** `article.content` is Draft.js (`blocks` + `entityMap` for links), and the post's own `text` is empty. We flatten the blocks ourselves.
- **Articles can be huge.** 80K chars is roughly 20K tokens of episode body, run through ~7 Graphiti LLM calls. That's fine now and then within the 2.5M/day free tokens, but it's the long-content problem v5 is for.
- **The longest thread tested was 3 posts.** Whether 20+ post threads come back whole is untested.
- **Replies from other people aren't included.** `/2/thread` is the author's posts only; `/2/conversation` adds replies, but we don't want those.
- **A post that's mostly a link has little in it by itself.** The value is in the linked page.
- **It's a third-party service.** FxEmbed is MIT and runs on Cloudflare Workers, so we could self-host it within the free tier if the public instance goes away.
