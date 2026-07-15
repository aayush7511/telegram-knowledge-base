import { describe, expect, it } from "vitest";
import { classify, mediaRef } from "../src/classify";
import { message, textMessage, voiceMessage } from "./fixtures";

describe("classify", () => {
  it("text message → text", () => {
    expect(classify(textMessage("a note"))).toBe("text");
  });

  it("whitespace-only text → unsupported", () => {
    expect(classify(textMessage("   "))).toBe("unsupported");
  });

  it("voice memo → voice", () => {
    expect(classify(voiceMessage())).toBe("voice");
  });

  it("audio file → voice (both go to ASR)", () => {
    expect(
      classify(message({ audio: { file_id: "a", file_unique_id: "au", mime_type: "audio/mpeg", duration: 200 } })),
    ).toBe("voice");
  });

  it("video → video, video note → video", () => {
    expect(classify(message({ video: { file_id: "v", file_unique_id: "vu", duration: 30 } }))).toBe("video");
    expect(classify(message({ video_note: { file_id: "vn", file_unique_id: "vnu", duration: 15 } }))).toBe("video");
  });

  it("photo → photo", () => {
    expect(
      classify(message({ photo: [{ file_id: "p1", file_unique_id: "p1u", width: 90, height: 60 }] })),
    ).toBe("photo");
  });

  it("document → document", () => {
    expect(classify(message({ document: { file_id: "d", file_unique_id: "du", mime_type: "application/pdf" } }))).toBe(
      "document",
    );
  });

  it("sticker/empty message → unsupported", () => {
    expect(classify(message())).toBe("unsupported");
  });
});

describe("mediaRef", () => {
  it("picks the largest photo size", () => {
    const msg = message({
      photo: [
        { file_id: "small", file_unique_id: "s", width: 90, height: 60, file_size: 1_000 },
        { file_id: "large", file_unique_id: "l", width: 1280, height: 853, file_size: 150_000 },
        { file_id: "medium", file_unique_id: "m", width: 320, height: 213, file_size: 20_000 },
      ],
    });
    expect(mediaRef(msg, "photo")).toMatchObject({ file_id: "large", mime_type: "image/jpeg" });
  });

  it("defaults voice mime to audio/ogg and carries duration", () => {
    const msg = message({ voice: { file_id: "v", file_unique_id: "vu", duration: 42 } });
    expect(mediaRef(msg, "voice")).toMatchObject({
      file_id: "v",
      mime_type: "audio/ogg",
      duration_seconds: 42,
    });
  });
});
