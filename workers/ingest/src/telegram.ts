// Minimal Telegram Bot API surface — only the Update fields and methods Worker 1 touches.

export interface TgUpdate {
  update_id: number;
  message?: TgMessage;
}

export interface TgChat {
  id: number;
  type: string;
}

export interface TgFileBase {
  file_id: string;
  file_unique_id: string;
  file_size?: number;
  mime_type?: string;
  duration?: number;
}

export interface TgPhotoSize {
  file_id: string;
  file_unique_id: string;
  width: number;
  height: number;
  file_size?: number;
}

export interface TgMessage {
  message_id: number;
  date: number;
  chat: TgChat;
  media_group_id?: string;
  text?: string;
  caption?: string;
  voice?: TgFileBase;
  audio?: TgFileBase;
  video?: TgFileBase;
  video_note?: TgFileBase;
  photo?: TgPhotoSize[];
  document?: TgFileBase & { file_name?: string };
}

const API_BASE = "https://api.telegram.org";

/** Telegram answered with ok:false — a permanent, API-level rejection (vs. a network error). */
export class TelegramApiError extends Error {
  constructor(
    method: string,
    public description: string,
  ) {
    super(`Telegram ${method} failed: ${description}`);
    this.name = "TelegramApiError";
  }
}

interface TgResponse<T> {
  ok: boolean;
  result?: T;
  description?: string;
}

async function call<T>(token: string, method: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}/bot${token}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = (await res.json()) as TgResponse<T>;
  if (!body.ok) throw new TelegramApiError(method, body.description ?? `HTTP ${res.status}`);
  return body.result as T;
}

export function sendMessage(
  token: string,
  chat_id: number,
  text: string,
  reply_to_message_id?: number,
): Promise<unknown> {
  return call(token, "sendMessage", {
    chat_id,
    text,
    ...(reply_to_message_id ? { reply_parameters: { message_id: reply_to_message_id } } : {}),
  });
}

/** The 👀 ingestion ack — zero chat noise. */
export function setSeenReaction(token: string, chat_id: number, message_id: number): Promise<unknown> {
  return call(token, "setMessageReaction", {
    chat_id,
    message_id,
    reaction: [{ type: "emoji", emoji: "👀" }],
  });
}

/** getFile + download. Returns the raw file Response (body unread). */
export async function downloadFile(token: string, file_id: string): Promise<Response> {
  const info = await call<{ file_path?: string }>(token, "getFile", { file_id });
  if (!info.file_path) throw new TelegramApiError("getFile", "no file_path in response");
  const res = await fetch(`${API_BASE}/file/bot${token}/${info.file_path}`);
  if (!res.ok) throw new Error(`Telegram file download failed: HTTP ${res.status}`);
  return res;
}
