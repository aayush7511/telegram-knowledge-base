import type { Env, JobDescriptor } from "./types";
import type { TgUpdate } from "./telegram";
import { TelegramApiError, downloadFile, sendMessage, setSeenReaction } from "./telegram";
import { classify, mediaRef } from "./classify";
import { buildMediaJob, buildTextMessageJobs } from "./jobs";
import { deleteJobs, findJobsForMessage, insertJobs, markQueued } from "./db";
import type { RejectedUrl } from "./urls";

const MAX_FILE_BYTES = 20 * 1024 * 1024; // Bot API getFile ceiling

const MIME_EXT: Record<string, string> = {
  "audio/ogg": "ogg",
  "audio/mpeg": "mp3",
  "audio/mp4": "m4a",
  "audio/x-m4a": "m4a",
  "audio/wav": "wav",
  "audio/flac": "flac",
  "video/mp4": "mp4",
  "video/quicktime": "mov",
  "video/webm": "webm",
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "application/pdf": "pdf",
  "text/plain": "txt",
};

function ext(mime: string | null): string {
  return (mime && MIME_EXT[mime.toLowerCase()]) || "bin";
}

function ok(): Response {
  return new Response("ok");
}

export default {
  async fetch(request, env, ctx): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (request.method !== "POST" || pathname !== "/webhook") {
      return new Response("not found", { status: 404 });
    }
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("unauthorized", { status: 401 });
    }

    let update: TgUpdate;
    try {
      update = await request.json<TgUpdate>();
    } catch {
      return ok(); // malformed body — ACK so Telegram doesn't redeliver garbage
    }

    try {
      return await handleUpdate(update, env, ctx);
    } catch (err) {
      // transient failure (R2/D1/Queue/network): 500 makes Telegram redeliver;
      // the state-aware dedup in handleUpdate makes the retry safe
      console.error("ingest failed", err instanceof Error ? (err.stack ?? err.message) : err);
      return new Response("internal error", { status: 500 });
    }
  },
} satisfies ExportedHandler<Env>;

async function handleUpdate(update: TgUpdate, env: Env, ctx: ExecutionContext): Promise<Response> {
  const msg = update.message;
  if (!msg) return ok(); // edits, callbacks, reactions — not ingestible
  if (String(msg.chat.id) !== env.OWNER_CHAT_ID) return ok(); // single-user bot

  const reply = (text: string) =>
    ctx.waitUntil(
      sendMessage(env.TELEGRAM_BOT_TOKEN, msg.chat.id, text, msg.message_id).catch((e) =>
        console.error("reply failed", e),
      ),
    );

  // webhook-retry dedup on (chat_id, message_id)
  const existing = await findJobsForMessage(env.DB, msg.chat.id, msg.message_id);
  if (existing.length > 0) {
    if (existing.some((j) => j.state !== "received")) return ok(); // already ingested
    // partial earlier attempt (inserted but never enqueued) — clear and reprocess;
    // any orphaned R2 object from that attempt is caught by the lifecycle rule
    await deleteJobs(env.DB, existing.map((j) => j.job_id));
  }

  const kind = classify(msg);
  if (kind === "unsupported") {
    reply("I can't ingest this content type yet — send text, links, voice, photos, videos, or documents.");
    return ok();
  }

  const now = new Date().toISOString();
  let jobs: JobDescriptor[];
  let rejected: RejectedUrl[] = [];

  if (kind === "text") {
    ({ jobs, rejected } = buildTextMessageJobs(msg, { now, makeId: () => crypto.randomUUID() }));
  } else {
    const media = mediaRef(msg, kind)!;
    if (media.file_size !== null && media.file_size > MAX_FILE_BYTES) {
      const mb = (media.file_size / (1024 * 1024)).toFixed(1);
      reply(`This file is ${mb}MB — the Telegram Bot API only lets me download files up to 20MB.`);
      return ok();
    }

    let download: Response;
    try {
      download = await downloadFile(env.TELEGRAM_BOT_TOKEN, media.file_id);
    } catch (err) {
      if (err instanceof TelegramApiError) {
        // permanent (e.g. "file is too big") — tell the user, don't make Telegram retry
        reply(`Couldn't fetch that file from Telegram: ${err.description}`);
        return ok();
      }
      throw err;
    }

    const job_id = crypto.randomUUID();
    const r2_key = `raw-media/${job_id}.${ext(media.mime_type)}`;
    // ≤20MB guaranteed above, so buffering is safe (R2 put needs a known length)
    const bytes = await download.arrayBuffer();
    const obj = await env.RAW_MEDIA.put(r2_key, bytes, {
      httpMetadata: media.mime_type ? { contentType: media.mime_type } : undefined,
    });
    console.log(`r2 put ${r2_key} size=${obj?.size} etag=${obj?.etag}`);

    jobs = [
      buildMediaJob(
        msg,
        kind,
        {
          r2_key,
          mime_type: media.mime_type,
          size_bytes: obj?.size ?? bytes.byteLength,
          duration_seconds: media.duration_seconds,
        },
        { now, job_id },
      ),
    ];
  }

  if (rejected.length > 0) {
    reply("Skipped (not ingestible):\n" + rejected.map((r) => `• ${r.url} — ${r.reason}`).join("\n"));
  }
  if (jobs.length === 0) return ok(); // everything in the message was rejected

  await insertJobs(env.DB, jobs);
  if (jobs.length === 1) {
    await env.JOB_QUEUE.send(jobs[0]);
  } else {
    await env.JOB_QUEUE.sendBatch(jobs.map((body) => ({ body })));
  }
  await markQueued(env.DB, jobs.map((j) => j.job_id), new Date().toISOString());

  ctx.waitUntil(
    setSeenReaction(env.TELEGRAM_BOT_TOKEN, msg.chat.id, msg.message_id).catch((e) =>
      console.error("reaction failed", e),
    ),
  );
  return ok();
}
