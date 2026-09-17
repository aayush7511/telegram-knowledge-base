// The 👀 → 👌 swap: sent once every job from a Telegram message is saved.
// Runs against the real Worker via SELF; the fake Telegram in vitest.config.ts
// records every Bot API call, so a test can assert the reaction was — or
// wasn't — actually sent.
import { SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { seedJob, textJob } from "./fixtures";

interface TelegramCall {
  path: string;
  chat_id: number;
  message_id: number;
  reaction: { type: string; emoji: string }[];
}

const REACTIONS_URL = "https://api.telegram.org/__reactions";

async function telegramCalls(): Promise<TelegramCall[]> {
  return (await fetch(REACTIONS_URL)).json();
}

beforeEach(async () => {
  await fetch(REACTIONS_URL, { method: "DELETE" });
});

async function post(body: unknown): Promise<Response> {
  return SELF.fetch("https://kb-forward.test/status", {
    method: "POST",
    headers: { "content-type": "application/json", "X-KB-Secret": "test-worker2-secret" },
    body: JSON.stringify(body),
  });
}

describe("👌 reaction", () => {
  it("reacts when a single-job message is saved", async () => {
    await seedJob(textJob("j1"), "indexing");
    expect((await post({ job_id: "j1", state: "saved" })).status).toBe(200);
    expect(await telegramCalls()).toEqual([
      {
        path: "/bottest-token/setMessageReaction",
        chat_id: 12345,
        message_id: 1,
        reaction: [{ type: "emoji", emoji: "👌" }],
      },
    ]);
  });

  it("waits for the last job of a multi-link message", async () => {
    await seedJob(textJob("j1", { message_id: 7 }), "indexing");
    await seedJob(textJob("j2", { message_id: 7 }), "indexing");
    await post({ job_id: "j1", state: "saved" });
    expect(await telegramCalls()).toEqual([]);
    await post({ job_id: "j2", state: "saved" });
    const calls = await telegramCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0].message_id).toBe(7);
  });

  it("stays 👀 when a sibling job failed", async () => {
    await seedJob(textJob("j1", { message_id: 7 }), "failed");
    await seedJob(textJob("j2", { message_id: 7 }), "indexing");
    await post({ job_id: "j2", state: "saved" });
    expect(await telegramCalls()).toEqual([]);
  });

  it("does not react on non-saved states", async () => {
    await seedJob(textJob("j1"), "forwarded");
    await post({ job_id: "j1", state: "indexing" });
    expect(await telegramCalls()).toEqual([]);
  });

  it("still returns 200 when Telegram rejects the reaction", async () => {
    await seedJob(textJob("j1", { chat_id: 666 }), "indexing");
    expect((await post({ job_id: "j1", state: "saved" })).status).toBe(200);
    expect(await telegramCalls()).toHaveLength(1); // attempted, rejected, logged
  });
});
