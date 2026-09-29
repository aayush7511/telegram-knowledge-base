// IngestRpc.createJobs — the save path kb-mcp calls over a service binding.
// Called through the Worker's own exports, so it's a real RPC call inside
// workerd; D1/Queue are miniflare-backed and Telegram is the fake in
// vitest.config.ts, whose sendMessage answers with message_ids from 9000 up.
import { env } from "cloudflare:test";
import { exports } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import type { SaveResult } from "../src/index";
import { MAX_SAVE_CHARS } from "../src/index";
import { OWNER_CHAT_ID } from "./fixtures";

interface Rpc {
  createJobs(content: string, clientName: string): Promise<SaveResult>;
}
const rpc = (exports as unknown as { IngestRpc: Rpc }).IngestRpc;

interface JobRow {
  job_id: string;
  chat_id: number;
  message_id: number;
  group_id: string | null;
  content_type: string;
  state: string;
  text: string | null;
  url: string | null;
  caption: string | null;
}

async function allRows(): Promise<JobRow[]> {
  const { results } = await env.DB.prepare("SELECT * FROM jobs ORDER BY url").all<JobRow>();
  return results;
}

describe("createJobs", () => {
  it("saves a note keyed to the bot's echo message in the owner chat", async () => {
    const result = await rpc.createJobs("  FalkorDB runs on the e2-micro  ", "Claude");

    const rows = await allRows();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      chat_id: OWNER_CHAT_ID,
      content_type: "text",
      state: "queued",
      text: "FalkorDB runs on the e2-micro", // the content, not the "Saving from" echo text
      url: null,
    });
    expect(rows[0].message_id).toBeGreaterThanOrEqual(9000); // the echo, not a user message
    expect(result).toEqual({ jobs: [{ job_id: rows[0].job_id, url: null }], rejected: [] });
  });

  it("fans links out into url jobs and reports the rejected ones", async () => {
    const content = "two good, one profile: https://youtu.be/abc123 https://x.com/a/status/1 https://www.instagram.com/natgeo/";
    const result = await rpc.createJobs(content, "Codex");

    const rows = await allRows();
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.content_type === "url" && r.state === "queued" && r.caption === content)).toBe(true);
    expect(rows[0].group_id).not.toBeNull();
    expect(rows[0].group_id).toBe(rows[1].group_id);
    expect(rows[0].message_id).toBe(rows[1].message_id);

    expect(new Set(result.jobs.map((j) => j.url))).toEqual(
      new Set(["https://youtu.be/abc123", "https://x.com/a/status/1"]),
    );
    expect(result.rejected).toHaveLength(1);
    expect(result.rejected[0].url).toBe("https://www.instagram.com/natgeo/");
  });

  it("creates no jobs when every link is rejected", async () => {
    const result = await rpc.createJobs("https://www.instagram.com/natgeo/", "Claude");
    expect(result.jobs).toEqual([]);
    expect(result.rejected).toHaveLength(1);
    expect(await allRows()).toHaveLength(0);
  });

  it("gives each save its own echo message, so identical saves aren't deduped away", async () => {
    await rpc.createJobs("same note", "Claude");
    await rpc.createJobs("same note", "Claude");
    const rows = await allRows();
    expect(rows).toHaveLength(2);
    expect(rows[0].message_id).not.toBe(rows[1].message_id);
  });

  it("rejects empty and oversized content before posting anything", async () => {
    // .then(ok, err) rather than expect().rejects: an RPC promise handed to
    // expect() still surfaces as an unhandled rejection in workerd. workerd
    // also logs the throw on the callee side ("uncaught exception") — expected
    // here; kb-mcp's input schema keeps these inputs from reaching it.
    const failure = (content: string) =>
      rpc.createJobs(content, "Claude").then(
        () => null,
        (e: Error) => e.message,
      );
    expect(await failure("   ")).toBe("content is empty");
    expect(await failure("x".repeat(MAX_SAVE_CHARS + 1))).toBe(`content is over ${MAX_SAVE_CHARS} characters`);
    expect(await allRows()).toHaveLength(0);
  });

  it("accepts content at the limit", async () => {
    const result = await rpc.createJobs("x".repeat(MAX_SAVE_CHARS), "");
    expect(result.jobs).toHaveLength(1);
  });
});
