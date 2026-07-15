import type { TgMessage, TgUpdate } from "../src/telegram";

export const OWNER_CHAT_ID = 12345;

let nextMessageId = 100;

export function message(over: Partial<TgMessage> = {}): TgMessage {
  return {
    message_id: nextMessageId++,
    date: 1752537600,
    chat: { id: OWNER_CHAT_ID, type: "private" },
    ...over,
  };
}

export function textMessage(text: string, over: Partial<TgMessage> = {}): TgMessage {
  return message({ text, ...over });
}

export function voiceMessage(over: Partial<TgMessage> = {}): TgMessage {
  return message({
    voice: {
      file_id: "voice-file-id",
      file_unique_id: "voice-unique",
      file_size: 128_000,
      mime_type: "audio/ogg",
      duration: 12,
    },
    ...over,
  });
}

export function update(msg: TgMessage): TgUpdate {
  return { update_id: 1, message: msg };
}

/** Deterministic id factory for pure-logic tests. */
export function idFactory(): () => string {
  let i = 0;
  return () => `id-${++i}`;
}
