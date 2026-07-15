import type { ContentType, JobDescriptor, JobMedia } from "./types";
import type { TgMessage } from "./telegram";
import { checkUrl, extractUrls, type RejectedUrl } from "./urls";

export interface BuildOpts {
  now: string; // ISO 8601 time_received
  makeId: () => string; // injectable for deterministic tests
}

/**
 * Text message → either one inline text job, or a fan-out of url jobs
 * (one per accepted URL, sharing a generated group_id for failure isolation).
 */
export function buildTextMessageJobs(
  msg: TgMessage,
  opts: BuildOpts,
): { jobs: JobDescriptor[]; rejected: RejectedUrl[] } {
  const text = msg.text ?? "";
  const urls = extractUrls(text);

  const base = {
    chat_id: msg.chat.id,
    message_id: msg.message_id,
    time_received: opts.now,
  };

  if (urls.length === 0) {
    return {
      jobs: [{ ...base, job_id: opts.makeId(), group_id: null, content_type: "text", text }],
      rejected: [],
    };
  }

  const checked = urls.map(checkUrl);
  const accepted = checked.filter((c) => c.ok);
  const rejected = checked.filter((c) => !c.ok);

  // caption carries surrounding prose — only when the message is more than bare links
  const leftover = urls.reduce((t, u) => t.replace(u, ""), text).trim();
  const caption = leftover.length > 0 ? text : undefined;

  const group_id = accepted.length > 1 ? opts.makeId() : null;

  const jobs = accepted.map(
    (a): JobDescriptor => ({
      ...base,
      job_id: opts.makeId(),
      group_id,
      content_type: "url",
      url: a.url,
      url_source: a.source,
      ...(caption ? { caption } : {}),
    }),
  );
  return { jobs, rejected };
}

/**
 * Native media message → one job; bytes are already in R2 (r2_key set).
 * Album items each arrive as their own Update — media_group_id passes through
 * as group_id, no buffering/synchronization (per design doc).
 */
export function buildMediaJob(
  msg: TgMessage,
  kind: Exclude<ContentType, "text" | "url">,
  media: JobMedia,
  opts: { now: string; job_id: string },
): JobDescriptor {
  return {
    job_id: opts.job_id,
    group_id: msg.media_group_id ?? null,
    chat_id: msg.chat.id,
    message_id: msg.message_id,
    time_received: opts.now,
    content_type: kind,
    media,
    ...(msg.caption ? { caption: msg.caption } : {}),
  };
}
