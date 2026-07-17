// Integration tests: full webhook round-trips against the real Worker with
// miniflare-backed D1/R2/Queue bindings. Outbound Telegram API calls are served
// by the fake in vitest.config.ts (outboundService) — no real network access.
import { SELF, env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { textMessage, voiceMessage, message, update, OWNER_CHAT_ID } from "./fixtures";

const SECRET = "test-secret";

function post(body: unknown, secret = SECRET): Promise<Response> {
  return SELF.fetch("https://kb-ingest.test/webhook", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": secret,
    },
    body: JSON.stringify(body),
  });
}

interface JobRow {
  job_id: string;
  chat_id: number;
  message_id: number;
  group_id: string | null;
  content_type: string;
  state: string;
  r2_key: string | null;
  text: string | null;
  url: string | null;
  caption: string | null;
}

async function allRows(): Promise<JobRow[]> {
  const { results } = await env.DB.prepare("SELECT * FROM jobs").all<JobRow>();
  return results;
}

describe("webhook auth & routing", () => {
  it("rejects a wrong secret token with 401", async () => {
    const res = await post(update(textMessage("hi")), "wrong-secret");
    expect(res.status).toBe(401);
    expect(await allRows()).toHaveLength(0);
  });

  it("404s other paths and methods", async () => {
    const res = await SELF.fetch("https://kb-ingest.test/", { method: "GET" });
    expect(res.status).toBe(404);
  });

  it("ignores updates without a message", async () => {
    const res = await post({ update_id: 9 });
    expect(res.status).toBe(200);
    expect(await allRows()).toHaveLength(0);
  });

  it("silently ACKs messages from non-owner chats", async () => {
    const msg = textMessage("hello", { chat: { id: 99999, type: "private" } });
    const res = await post(update(msg));
    expect(res.status).toBe(200);
    expect(await allRows()).toHaveLength(0);
  });
});

describe("text ingestion", () => {
  it("ingests a plain text note → one queued job", async () => {
    const res = await post(update(textMessage("remember: falkordb is redis-based")));
    expect(res.status).toBe(200);

    const rows = await allRows();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      chat_id: OWNER_CHAT_ID,
      content_type: "text",
      state: "queued",
      r2_key: null,
      text: "remember: falkordb is redis-based",
      url: null,
      caption: null,
    });
  });

  it("dedups a webhook retry of an already-ingested message", async () => {
    const msg = textMessage("only once please");
    await post(update(msg));
    await post(update(msg)); // Telegram redelivers the same Update
    expect(await allRows()).toHaveLength(1);
  });

  it("fans out a multi-URL message into url jobs sharing a group_id", async () => {
    const text = "two vids: https://youtu.be/abc123 https://www.youtube.com/watch?v=def456";
    const res = await post(update(textMessage(text)));
    expect(res.status).toBe(200);

    const rows = await allRows();
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.content_type === "url" && r.state === "queued")).toBe(true);
    expect(rows[0].group_id).not.toBeNull();
    expect(rows[0].group_id).toBe(rows[1].group_id);
    // each row stores its own url; caption carries the surrounding prose
    expect(new Set(rows.map((r) => r.url))).toEqual(
      new Set(["https://youtu.be/abc123", "https://www.youtube.com/watch?v=def456"]),
    );
    expect(rows.every((r) => r.caption === text && r.text === null)).toBe(true);
  });

  it("rejects invalid URLs without creating jobs", async () => {
    const res = await post(update(textMessage("https://www.instagram.com/natgeo/")));
    expect(res.status).toBe(200);
    expect(await allRows()).toHaveLength(0);
  });
});

describe("media ingestion", () => {
  it("downloads a voice memo into R2 and queues the job", async () => {
    const res = await post(update(voiceMessage()));
    expect(res.status).toBe(200);

    const rows = await allRows();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ content_type: "voice", state: "queued", text: null, url: null, caption: null });
    expect(rows[0].r2_key).toMatch(/^raw-media\/.+\.ogg$/);

    const obj = await env.RAW_MEDIA.get(rows[0].r2_key!);
    expect(obj).not.toBeNull();
    expect(await obj!.text()).toBe("fake-ogg-bytes");
  });

  it("rejects files over the 20MB Bot API limit without touching R2", async () => {
    const msg = message({
      video: {
        file_id: "big",
        file_unique_id: "bigu",
        file_size: 25 * 1024 * 1024,
        mime_type: "video/mp4",
        duration: 600,
      },
    });
    const res = await post(update(msg));
    expect(res.status).toBe(200);
    expect(await allRows()).toHaveLength(0);
    expect((await env.RAW_MEDIA.list({ prefix: "raw-media/" })).objects).toHaveLength(0);
  });
});

describe("unsupported content", () => {
  it("ACKs with no job for unsupported message types", async () => {
    const res = await post(update(message())); // no text, no media — e.g. a sticker
    expect(res.status).toBe(200);
    expect(await allRows()).toHaveLength(0);
  });
});
