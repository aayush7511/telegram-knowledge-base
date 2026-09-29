import { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";
import { takeCall } from "./limits";
import type { Env, Props, SaveResult } from "./types";

// Two tools aimed at the tasks, not a wrapper per Graphiti call, and nothing
// that deletes: a model must never be able to erase memory. See
// docs/design/v3.md#tools.

// Worker 1's cap (MAX_SAVE_CHARS): the "Saving from" echo must fit Telegram's 4,096.
const MAX_SAVE_CHARS = 4000;
const SEARCH_TIMEOUT_MS = 60_000; // a Cloud Run cold start plus the search

export interface Fact {
  fact: string;
  valid_at: string | null;
  invalid_at: string | null;
  sources: { title: string; kind: string; url: string | null; saved_at: string | null }[];
}

type ToolResult = { content: { type: "text"; text: string }[]; isError?: boolean };

const text = (t: string, isError = false): ToolResult => ({ content: [{ type: "text", text: t }], ...(isError ? { isError } : {}) });

export function buildServer(env: Env, props: Props): McpServer {
  const server = new McpServer({ name: "kb-memory", version: "1.0.0" });

  server.registerTool(
    "search_memory",
    {
      title: "Search memory",
      description:
        "Search the user's personal knowledge graph: facts extracted from the articles, videos, posts, papers, " +
        "and notes they chose to save. Use it when the user asks what they've read, saved, or noted about a topic, " +
        "or when their past reading would help answer. Returns facts, closest matches first, each with its source " +
        "(title and link) and when it was saved. These are the nearest matches, not guaranteed ones: ignore facts " +
        "that aren't about the question. Doesn't search the web.",
      inputSchema: z.object({
        query: z.string().min(1).max(500).describe("What to look for, in natural language or keywords."),
        limit: z.number().int().min(1).max(30).default(10).describe("How many facts to return (1–30)."),
      }),
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async ({ query, limit }) => {
      const over = await takeCall(env.DB, "search_memory");
      if (over) return text(over, true);
      let facts: Fact[];
      try {
        facts = await search(env, query, limit);
      } catch (err) {
        console.error("search failed", err);
        return text(`Search failed (${err instanceof Error ? err.message : String(err)}). Try again in a minute.`, true);
      }
      return text(formatFacts(facts));
    },
  );

  server.registerTool(
    "save_to_memory",
    {
      title: "Save to memory",
      description:
        "Save something to the user's knowledge graph: one or more links (articles, YouTube videos, X posts, " +
        "Stack Overflow questions, GitHub repos, issues, and PRs, PDFs) or a short note. Only call this when the " +
        "user asks to save or remember something: what goes into their memory is their choice. Links are fetched, " +
        "summarized, and added in the background, usually within a minute, and the user sees progress in their " +
        "Telegram chat. Returns what was queued, and any link that can't be saved (such as a profile page) with the reason.",
      inputSchema: z.object({
        content: z
          .string()
          .min(1)
          .max(MAX_SAVE_CHARS)
          .describe("The link(s) or note to save, as the user would send it in a chat message."),
      }),
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
    },
    async ({ content }) => {
      const over = await takeCall(env.DB, "save_to_memory");
      if (over) return text(over, true);
      let result: SaveResult;
      try {
        result = await env.INGEST.createJobs(content, props.clientName);
      } catch (err) {
        console.error("save failed", err);
        return text(`Save failed (${err instanceof Error ? err.message : String(err)}). Nothing was queued.`, true);
      }
      return formatSave(result);
    },
  );

  return server;
}

async function search(env: Env, query: string, limit: number): Promise<Fact[]> {
  const res = await fetch(`${env.CLOUD_RUN_URL}/search`, {
    method: "POST",
    headers: { "content-type": "application/json", "X-KB-Secret": env.CLOUD_RUN_SECRET },
    body: JSON.stringify({ query, limit }),
    signal: AbortSignal.timeout(SEARCH_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`the search service returned HTTP ${res.status}`);
  return ((await res.json()) as { results: Fact[] }).results;
}

const day = (iso: string | null) => (iso ? iso.slice(0, 10) : "unknown date");

export function formatFacts(facts: Fact[]): string {
  if (facts.length === 0) return "Nothing in memory matches that.";
  const lines = facts.map((f, i) => {
    const sources = f.sources.map((s) =>
      s.url ? `${s.title} (${s.kind}) — ${s.url}, saved ${day(s.saved_at)}` : `${s.title} (${s.kind}), saved ${day(s.saved_at)}`,
    );
    const out = [`${i + 1}. ${f.fact}`, ...sources.map((s) => `   Source: ${s}`)];
    if (f.invalid_at) out.push(`   No longer true as of ${day(f.invalid_at)}.`);
    return out.join("\n");
  });
  return `${facts.length} fact${facts.length === 1 ? "" : "s"}, closest matches first:\n\n${lines.join("\n\n")}`;
}

export function formatSave(result: SaveResult): ToolResult {
  const parts: string[] = [];
  if (result.jobs.length > 0) {
    const items = result.jobs.map((j) => `- ${j.url ?? "note"}`).join("\n");
    parts.push(
      `Queued ${result.jobs.length} item${result.jobs.length === 1 ? "" : "s"} to save:\n${items}\n` +
        "Each is processed in the background, usually within a minute; the user sees progress in Telegram.",
    );
  }
  if (result.rejected.length > 0) {
    parts.push(`Not saved:\n${result.rejected.map((r) => `- ${r.url}: ${r.reason}`).join("\n")}`);
  }
  return text(parts.join("\n\n"), result.jobs.length === 0);
}
