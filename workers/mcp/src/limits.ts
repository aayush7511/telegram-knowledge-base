// Tool-call caps (docs/design/v3.md#limits). They keep kb-mcp's downstream
// work — Cloud Run, OpenAI embeddings and extraction, Gemini, Supadata — inside
// free quotas. Counted in D1, not KV: KV's 1,000 writes/day go to OAuth tokens.
// Only signed-in tool calls are counted; an unauthenticated request never gets
// this far, and counting it would spend D1 writes the job pipeline needs.

export const LIMITS = {
  burstPerMinute: 30,
  search_memory: 500, // per UTC day
  save_to_memory: 50, // per UTC day
} as const;

export type LimitedTool = "search_memory" | "save_to_memory";

/**
 * Count one call to `tool` and return null if it's within the caps, or the
 * message to show the model if it's over. Counts even when over, so a looping
 * client stays blocked for the rest of the window.
 */
export async function takeCall(db: D1Database, tool: LimitedTool, now = new Date()): Promise<string | null> {
  const minute = Math.floor(now.getTime() / 60_000);
  const day = now.toISOString().slice(0, 10);
  const minuteEnd = new Date((minute + 1) * 60_000).toISOString();
  const dayEnd = new Date(`${day}T00:00:00.000Z`);
  dayEnd.setUTCDate(dayEnd.getUTCDate() + 1);

  const bump = db.prepare(
    `INSERT INTO usage (bucket, count, window_end) VALUES (?, 1, ?)
     ON CONFLICT(bucket) DO UPDATE SET count = count + 1
     RETURNING count`,
  );
  const [, burst, daily] = await db.batch<{ count: number }>([
    db.prepare("DELETE FROM usage WHERE window_end <= ?").bind(now.toISOString()),
    bump.bind(`burst:${minute}`, minuteEnd),
    bump.bind(`${tool}:${day}`, dayEnd.toISOString()),
  ]);

  if (burst.results[0].count > LIMITS.burstPerMinute) {
    return `Rate limit: more than ${LIMITS.burstPerMinute} memory tool calls in a minute. Wait a minute and try again.`;
  }
  if (daily.results[0].count > LIMITS[tool]) {
    return `Daily limit reached: ${LIMITS[tool]} ${tool} calls per day. It resets at 00:00 UTC.`;
  }
  return null;
}
