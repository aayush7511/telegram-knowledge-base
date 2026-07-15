import type { TgMessage } from "./telegram";

export type MessageKind = "text" | "voice" | "photo" | "video" | "document" | "unsupported";

// Audio files and voice memos both go to ASR → "voice"; video notes are just round videos.
export function classify(msg: TgMessage): MessageKind {
  if (msg.voice || msg.audio) return "voice";
  if (msg.video || msg.video_note) return "video";
  if (msg.photo && msg.photo.length > 0) return "photo";
  if (msg.document) return "document";
  if (typeof msg.text === "string" && msg.text.trim().length > 0) return "text";
  return "unsupported";
}

export interface MediaRef {
  file_id: string;
  file_size: number | null;
  mime_type: string | null;
  duration_seconds: number | null;
}

export function mediaRef(msg: TgMessage, kind: MessageKind): MediaRef | null {
  if (kind === "voice") {
    const f = (msg.voice ?? msg.audio)!;
    return {
      file_id: f.file_id,
      file_size: f.file_size ?? null,
      mime_type: f.mime_type ?? "audio/ogg",
      duration_seconds: f.duration ?? null,
    };
  }
  if (kind === "video") {
    const f = (msg.video ?? msg.video_note)!;
    return {
      file_id: f.file_id,
      file_size: f.file_size ?? null,
      mime_type: f.mime_type ?? "video/mp4",
      duration_seconds: f.duration ?? null,
    };
  }
  if (kind === "photo") {
    // Telegram sends multiple sizes of the same photo — take the largest
    const best = msg.photo!.reduce((a, b) => (b.width > a.width ? b : a));
    return { file_id: best.file_id, file_size: best.file_size ?? null, mime_type: "image/jpeg", duration_seconds: null };
  }
  if (kind === "document") {
    const f = msg.document!;
    return { file_id: f.file_id, file_size: f.file_size ?? null, mime_type: f.mime_type ?? null, duration_seconds: null };
  }
  return null;
}
