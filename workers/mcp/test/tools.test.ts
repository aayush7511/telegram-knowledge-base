// The two tools over MCP, as a signed-in client calls them, and the caps.
import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { LIMITS, takeCall } from "../src/limits";
import { call, connectAsOwner } from "./flow";

interface ToolResult {
  content: { type: string; text: string }[];
  isError?: boolean;
}

let token: string;
let nextId = 1;

beforeEach(async () => {
  token = await connectAsOwner("Claude");
});

// MCP 2026-07-28: every request carries its protocol version, client info and capabilities.
async function rpc(method: string, params: Record<string, unknown> = {}) {
  const res = await call("/mcp", {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      "mcp-protocol-version": "2026-07-28",
      "mcp-method": method,
      ...(typeof params.name === "string" ? { "mcp-name": params.name } : {}),
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: nextId++,
      method,
      params: {
        ...params,
        _meta: {
          "io.modelcontextprotocol/protocolVersion": "2026-07-28",
          "io.modelcontextprotocol/clientInfo": { name: "test", version: "1" },
          "io.modelcontextprotocol/clientCapabilities": {},
        },
      },
    }),
  });
  if (res.status !== 200) throw new Error(`${res.status} ${await res.text()}`);
  return (await res.json()) as { result?: any; error?: { code: number; message: string } };
}

async function tool(name: string, args: Record<string, unknown>): Promise<ToolResult> {
  const body = await rpc("tools/call", { name, arguments: args });
  expect(body.error).toBeUndefined();
  return body.result as ToolResult;
}

const textOf = (r: ToolResult) => r.content.map((c) => c.text).join("\n");

describe("tools/list", () => {
  it("offers exactly search and save, and marks search read-only", async () => {
    const { result } = await rpc("tools/list");
    const tools = result.tools as { name: string; annotations: Record<string, boolean> }[];
    expect(tools.map((t) => t.name)).toEqual(["search_memory", "save_to_memory"]);
    expect(tools[0].annotations.readOnlyHint).toBe(true);
    expect(tools[1].annotations).toMatchObject({ readOnlyHint: false, destructiveHint: false });
  });
});

describe("search_memory", () => {
  it("returns facts with their sources, asking Cloud Run for 10 by default", async () => {
    const r = await tool("search_memory", { query: "agent memory" });
    expect(r.isError).toBeFalsy();
    expect(textOf(r)).toBe(
      "1 fact, closest matches first:\n\n" +
        "1. A fact about agent memory (limit 10)\n" +
        "   Source: An Article (blog) — https://example.com/a, saved 2026-09-19",
    );
  });

  it("passes the limit through", async () => {
    expect(textOf(await tool("search_memory", { query: "q", limit: 3 }))).toContain("(limit 3)");
  });

  it("reports a failing search as a tool error the model can read", async () => {
    const r = await tool("search_memory", { query: "boom" });
    expect(r.isError).toBe(true);
    expect(textOf(r)).toContain("HTTP 500");
  });

  it("rejects a limit over 30 before searching", async () => {
    const r = await tool("search_memory", { query: "q", limit: 31 });
    expect(r.isError).toBe(true);
  });
});

describe("save_to_memory", () => {
  it("queues links and notes through Worker 1", async () => {
    const r = await tool("save_to_memory", { content: "https://example.com/post" });
    expect(r.isError).toBeFalsy();
    expect(textOf(r)).toContain("Queued 1 item to save:\n- https://example.com/post");
    expect(textOf(await tool("save_to_memory", { content: "a note" }))).toContain("Queued 1 item to save:\n- note");
  });

  it("tells Worker 1 which client is saving, from the name it registered", async () => {
    // the fake answers "whoami" with the client name it was given
    expect(textOf(await tool("save_to_memory", { content: "whoami" }))).toContain("- whoami: Claude");
    token = await connectAsOwner("Codex");
    expect(textOf(await tool("save_to_memory", { content: "whoami" }))).toContain("- whoami: Codex");
  });

  it("reports rejected links next to the saved ones", async () => {
    const r = await tool("save_to_memory", {
      content: "https://example.com/post https://www.instagram.com/natgeo/",
    });
    expect(r.isError).toBeFalsy();
    expect(textOf(r)).toContain("Not saved:\n- https://www.instagram.com/natgeo/: Instagram profile, not a post");
  });

  it("is an error when nothing could be saved", async () => {
    const r = await tool("save_to_memory", { content: "https://www.instagram.com/natgeo/" });
    expect(r.isError).toBe(true);
  });

  it("says nothing was queued when Worker 1 fails", async () => {
    const r = await tool("save_to_memory", { content: "boom" });
    expect(r.isError).toBe(true);
    expect(textOf(r)).toContain("Nothing was queued");
  });
});

describe("caps", () => {
  it("stops saves after the daily cap, with when it resets", async () => {
    const day = new Date().toISOString().slice(0, 10);
    await env.DB.prepare("INSERT INTO usage (bucket, count, window_end) VALUES (?, ?, ?)")
      .bind(`save_to_memory:${day}`, LIMITS.save_to_memory, "2999-01-01T00:00:00.000Z")
      .run();
    const r = await tool("save_to_memory", { content: "a note" });
    expect(r.isError).toBe(true);
    expect(textOf(r)).toBe(`Daily limit reached: ${LIMITS.save_to_memory} save_to_memory calls per day. It resets at 00:00 UTC.`);
    // searching has its own cap
    expect((await tool("search_memory", { query: "q" })).isError).toBeFalsy();
  });

  it("counts per minute across both tools, and forgets expired windows", async () => {
    const t = new Date("2026-09-29T10:00:30Z");
    for (let i = 0; i < LIMITS.burstPerMinute; i++) {
      expect(await takeCall(env.DB, i % 2 ? "search_memory" : "save_to_memory", t)).toBeNull();
    }
    expect(await takeCall(env.DB, "search_memory", t)).toContain("Rate limit");
    // the next minute starts fresh, and the old minute's row is deleted
    expect(await takeCall(env.DB, "search_memory", new Date("2026-09-29T10:01:05Z"))).toBeNull();
    const { results } = await env.DB.prepare("SELECT bucket FROM usage WHERE bucket LIKE 'burst:%'").all();
    expect(results).toHaveLength(1);
  });

  it("resets the daily count at 00:00 UTC", async () => {
    for (let i = 0; i < LIMITS.save_to_memory; i++) {
      await takeCall(env.DB, "save_to_memory", new Date(Date.UTC(2026, 8, 29, 23, i % 59, 0)));
    }
    expect(await takeCall(env.DB, "save_to_memory", new Date("2026-09-29T23:59:30Z"))).toContain("Daily limit");
    expect(await takeCall(env.DB, "save_to_memory", new Date("2026-09-30T00:00:10Z"))).toBeNull();
  });
});
