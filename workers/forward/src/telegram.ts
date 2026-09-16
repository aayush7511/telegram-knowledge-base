// Minimal Telegram Bot API surface for Worker 2: only the 👌 reaction. Mirrors
// workers/ingest/src/telegram.ts on purpose — the workers stay self-contained.

const API_BASE = "https://api.telegram.org";

/** Replace Worker 1's 👀 with 👌 once every job from the message is in the graph.
 *  Bots get one reaction per message, so setting 👌 swaps the 👀 out. */
export async function setDoneReaction(token: string, chat_id: number, message_id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/bot${token}/setMessageReaction`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id, message_id, reaction: [{ type: "emoji", emoji: "👌" }] }),
  });
  const body = (await res.json()) as { ok: boolean; description?: string };
  if (!body.ok) throw new Error(`Telegram setMessageReaction failed: ${body.description ?? `HTTP ${res.status}`}`);
}
