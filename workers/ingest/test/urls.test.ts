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

  it("splits two URLs glued together with no whitespace", () => {
    expect(extractUrls("https://youtu.be/abc123https://www.instagram.com/p/Cxyz1234abc/")).toEqual([
      "https://youtu.be/abc123",
      "https://www.instagram.com/p/Cxyz1234abc/",
    ]);
  });

  it("splits comma-separated URLs", () => {
    expect(extractUrls("https://a.example/one,https://b.example/two")).toEqual([
      "https://a.example/one",
      "https://b.example/two",
    ]);
  });

  it("does not split on bare 'http' text inside a query param", () => {
    expect(extractUrls("https://example.com/search?q=httproutersetup")).toEqual([
      "https://example.com/search?q=httproutersetup",
    ]);
  });

  it("keeps a full URL embedded as a query param value whole", () => {
    expect(extractUrls("https://example.com/redirect?url=https://target.com/page")).toEqual([
      "https://example.com/redirect?url=https://target.com/page",
    ]);
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

const accepts = (url: string, source: string) => expect(checkUrl(url)).toMatchObject({ ok: true, source });
const rejects = (url: string, reason: string) => expect(checkUrl(url)).toMatchObject({ ok: false, reason });

describe("checkUrl — x", () => {
  it("accepts posts on both domains, with or without trailing segments", () => {
    accepts("https://x.com/karpathy/status/1977755427569111362", "x");
    accepts("https://twitter.com/karpathy/status/1977755427569111362/photo/1", "x");
    accepts("https://mobile.twitter.com/i/status/1977755427569111362", "x");
    accepts("https://x.com/i/web/status/1977755427569111362", "x");
  });

  it("rejects profiles, their tabs, and site pages", () => {
    for (const u of [
      "https://x.com/karpathy",
      "https://x.com/karpathy/with_replies",
      "https://x.com/karpathy/likes",
      "https://x.com/search?q=graphiti",
      "https://x.com/explore",
      "https://x.com/home",
      "https://x.com/hashtag/AI",
      "https://x.com/i/lists/123",
      "https://x.com/settings",
    ]) {
      rejects(u, "X profile/page, not a post");
    }
  });

  it("rejects a status link without a numeric id", () => {
    rejects("https://x.com/karpathy/status/", "X profile/page, not a post");
  });

  it("rejects Spaces and bare article links with their own reasons", () => {
    rejects("https://x.com/i/spaces/1abc", "X Spaces are audio — not until v4");
    rejects("https://x.com/i/article/2002114638226522112", "X article link — send the link to the post that shares it");
  });
});

describe("checkUrl — reddit", () => {
  const LISTING = "Reddit subreddit/user/listing, not a post";

  it("accepts posts, comment permalinks, short and share links", () => {
    accepts("https://www.reddit.com/r/LocalLLaMA/comments/1abc2de/some_title/", "reddit");
    accepts("https://old.reddit.com/r/LocalLLaMA/comments/1abc2de/some_title/kx9y8z7/", "reddit");
    accepts("https://reddit.com/comments/1abc2de", "reddit");
    accepts("https://www.reddit.com/user/someone/comments/1abc2de/title/", "reddit");
    accepts("https://redd.it/1abc2de", "reddit");
    accepts("https://www.reddit.com/r/LocalLLaMA/s/AbCdEf123", "reddit");
  });

  it("rejects subreddits, sorts, users, and listings", () => {
    for (const u of [
      "https://www.reddit.com/",
      "https://www.reddit.com/r/LocalLLaMA/",
      "https://www.reddit.com/r/LocalLLaMA/top/?t=week",
      "https://www.reddit.com/r/popular",
      "https://www.reddit.com/user/someone",
      "https://www.reddit.com/u/someone/",
      "https://www.reddit.com/search/?q=graphiti",
    ]) {
      rejects(u, LISTING);
    }
  });

  it("rejects Reddit-hosted media until v4", () => {
    rejects("https://i.redd.it/abc123.jpg", "Reddit-hosted image/video — not until v4");
    rejects("https://v.redd.it/abc123", "Reddit-hosted image/video — not until v4");
    rejects("https://www.reddit.com/gallery/1abc2de", "Reddit image gallery — not until v4");
  });
});

describe("checkUrl — stack exchange", () => {
  it("accepts questions and short links across the network", () => {
    accepts("https://stackoverflow.com/questions/11227809/why-is-processing-a-sorted-array-faster", "stackexchange");
    accepts("https://stackoverflow.com/q/11227809", "stackexchange");
    accepts("https://stackoverflow.com/a/11227902", "stackexchange");
    accepts("https://unix.stackexchange.com/questions/12345/title", "stackexchange");
    accepts("https://askubuntu.com/questions/12345/title", "stackexchange");
  });

  it("rejects lists, tags, users, and search", () => {
    for (const u of [
      "https://stackoverflow.com/",
      "https://stackoverflow.com/questions",
      "https://stackoverflow.com/questions/tagged/python",
      "https://stackoverflow.com/tags",
      "https://stackoverflow.com/users/22656/jon-skeet",
      "https://stackoverflow.com/search?q=graphiti",
    ]) {
      rejects(u, "Stack Exchange listing/profile, not a question");
    }
  });
});

describe("checkUrl — github", () => {
  const LISTING = "GitHub profile/listing, not a repo, issue, or PR";

  it("accepts repos, issues, PRs, discussions, and gists", () => {
    accepts("https://github.com/getzep/graphiti", "github");
    accepts("https://github.com/getzep/graphiti/", "github");
    accepts("https://github.com/getzep/graphiti/issues/123", "github");
    accepts("https://github.com/getzep/graphiti/pull/456", "github");
    accepts("https://github.com/getzep/graphiti/discussions/78", "github");
    accepts("https://gist.github.com/karpathy/abc123", "github");
  });

  it("accepts a repo whose name looks like a site page", () => {
    accepts("https://github.com/probot/settings", "github");
  });

  it("rejects users, site pages, and repo listings", () => {
    for (const u of [
      "https://github.com/",
      "https://github.com/getzep",
      "https://github.com/search?q=graphiti",
      "https://github.com/trending",
      "https://github.com/topics/knowledge-graph",
      "https://github.com/getzep/graphiti/issues",
      "https://github.com/getzep/graphiti/pulls",
      "https://github.com/getzep/graphiti/commits/main",
      "https://github.com/getzep/graphiti/tree/main/mcp_server",
      "https://github.com/getzep/graphiti/blob/main/README.md",
      "https://gist.github.com/karpathy",
    ]) {
      rejects(u, LISTING);
    }
  });
});

describe("checkUrl — any host", () => {
  it("rejects search results", () => {
    rejects("https://www.google.com/search?q=graphiti", "search results page");
    rejects("https://www.google.co.uk/search?q=graphiti", "search results page");
    rejects("https://www.bing.com/search?q=graphiti", "search results page");
    rejects("https://duckduckgo.com/?q=graphiti", "search results page");
  });

  it("rejects maps, invites, and meetings", () => {
    rejects("https://www.google.com/maps/place/Austin", "map link");
    rejects("https://maps.app.goo.gl/abc123", "map link");
    rejects("https://us02web.zoom.us/j/123456789", "invite/meeting link");
    rejects("https://meet.google.com/abc-defg-hij", "invite/meeting link");
    rejects("https://discord.gg/abc123", "invite/meeting link");
    rejects("https://t.me/somechannel", "invite/meeting link");
    rejects("https://calendly.com/someone/30min", "invite/meeting link");
  });

  it("rejects Hacker News listings but keeps item pages", () => {
    rejects("https://news.ycombinator.com/", "Hacker News listing, not a post");
    rejects("https://news.ycombinator.com/newest", "Hacker News listing, not a post");
    accepts("https://news.ycombinator.com/item?id=43859015", "blog");
  });

  it("rejects pages behind a login and unsupported platforms", () => {
    rejects("https://docs.google.com/document/d/abc/edit", "needs a login — can't fetch");
    rejects("https://www.dropbox.com/s/abc/file", "needs a login — can't fetch");
    rejects("https://www.tiktok.com/@someone/video/123", "not supported yet");
    rejects("https://www.linkedin.com/posts/someone_activity-123", "not supported yet");
  });

  it("rejects account pages, but not article slugs that merely contain the word", () => {
    rejects("https://example.com/login", "account/login page");
    rejects("https://shop.example.com/cart?item=3", "account/login page");
    rejects("https://example.com/users/account/", "account/login page");
    accepts("https://example.com/blog/account-security-tips", "blog");
  });

  it("rejects file downloads and media files", () => {
    rejects("https://example.com/releases/app.dmg", "file download, not a page");
    rejects("https://example.com/src.tar.gz", "file download, not a page");
    rejects("https://example.com/img/diagram.PNG", "media file — not until v4");
    rejects("https://example.com/talk.mp3?dl=1", "media file — not until v4");
  });

  it("rejects private network addresses, however they're written", () => {
    for (const u of [
      "http://localhost:3000/",
      "http://127.0.0.1/",
      "http://2130706433/", // 127.0.0.1 as a decimal
      "http://10.128.0.2:3000/",
      "http://192.168.1.10/",
      "http://172.20.0.5/",
      "http://169.254.169.254/computeMetadata/v1/",
      "http://metadata.google.internal/",
      "http://printer.local/",
      "http://[::1]:6379/",
      "http://[::ffff:127.0.0.1]/",
    ]) {
      rejects(u, "private network address");
    }
    accepts("https://172.32.0.1/post", "blog"); // just outside 172.16/12
  });
});

describe("checkUrl — everything else", () => {
  it("treats any other https url as a blog", () => {
    expect(checkUrl("https://simonwillison.net/2026/some-post/")).toMatchObject({ ok: true, source: "blog" });
  });

  it("routes .pdf links on any host to the pdf source", () => {
    accepts("https://arxiv.org/pdf/2501.13956v1.pdf", "pdf");
    accepts("https://example.com/Paper.PDF", "pdf");
  });

  it("rejects non-http schemes", () => {
    expect(checkUrl("ftp://example.com/file")).toMatchObject({ ok: false });
  });
});
