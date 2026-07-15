import { describe, expect, it } from "vitest";
import { checkUrl, extractUrls } from "../src/urls";

describe("extractUrls", () => {
  it("returns empty for plain text", () => {
    expect(extractUrls("just a plain note about groceries")).toEqual([]);
  });

  it("finds multiple urls in prose", () => {
    const text = "check https://youtu.be/abc123 and also https://example.com/post later";
    expect(extractUrls(text)).toEqual(["https://youtu.be/abc123", "https://example.com/post"]);
  });

  it("strips trailing punctuation", () => {
    expect(extractUrls("read this (https://example.com/a), ok?")).toEqual(["https://example.com/a"]);
  });
});

describe("checkUrl — instagram", () => {
  it("accepts reels", () => {
    expect(checkUrl("https://www.instagram.com/reel/Cxyz1234abc/")).toMatchObject({
      ok: true,
      source: "instagram",
    });
  });

  it("accepts /p/ posts (ambiguous — resolved at fetch time)", () => {
    expect(checkUrl("https://instagram.com/p/Cxyz1234abc/")).toMatchObject({ ok: true, source: "instagram" });
  });

  it("rejects profiles", () => {
    expect(checkUrl("https://www.instagram.com/natgeo/")).toMatchObject({ ok: false });
  });

  it("rejects stories", () => {
    expect(checkUrl("https://www.instagram.com/stories/natgeo/123456/")).toMatchObject({ ok: false });
  });

  it("rejects comment permalinks", () => {
    expect(checkUrl("https://www.instagram.com/p/Cxyz1234abc/c/17891234/")).toMatchObject({ ok: false });
  });

  it("rejects a post link with no id", () => {
    expect(checkUrl("https://www.instagram.com/reel/")).toMatchObject({ ok: false });
  });
});

describe("checkUrl — youtube", () => {
  it("accepts watch urls", () => {
    expect(checkUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ")).toMatchObject({
      ok: true,
      source: "youtube",
    });
  });

  it("accepts shorts", () => {
    expect(checkUrl("https://youtube.com/shorts/abc123XYZ")).toMatchObject({ ok: true, source: "youtube" });
  });

  it("accepts youtu.be short links", () => {
    expect(checkUrl("https://youtu.be/dQw4w9WgXcQ")).toMatchObject({ ok: true, source: "youtube" });
  });

  it("rejects playlists", () => {
    expect(checkUrl("https://www.youtube.com/playlist?list=PL123")).toMatchObject({ ok: false });
  });

  it("rejects channels and handles", () => {
    expect(checkUrl("https://www.youtube.com/@mkbhd")).toMatchObject({ ok: false });
    expect(checkUrl("https://www.youtube.com/channel/UC123abc")).toMatchObject({ ok: false });
  });

  it("rejects watch urls without a video id", () => {
    expect(checkUrl("https://www.youtube.com/watch")).toMatchObject({ ok: false });
  });
});

describe("checkUrl — everything else", () => {
  it("treats any other https url as a blog", () => {
    expect(checkUrl("https://simonwillison.net/2026/some-post/")).toMatchObject({ ok: true, source: "blog" });
  });

  it("rejects non-http schemes", () => {
    expect(checkUrl("ftp://example.com/file")).toMatchObject({ ok: false });
  });
});
