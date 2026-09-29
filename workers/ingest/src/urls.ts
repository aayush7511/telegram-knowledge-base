import type { UrlSource } from "./types";

export interface AcceptedUrl {
  ok: true;
  url: string;
  source: UrlSource;
}

export interface RejectedUrl {
  ok: false;
  url: string;
  reason: string;
}

export type CheckedUrl = AcceptedUrl | RejectedUrl;

const URL_RE = /https?:\/\/[^\s<>"']+/gi;
const TRAILING_PUNCT = /[).,!?:;\]}]+$/;
// A scheme appearing mid-token means two URLs got pasted together with no
// whitespace — split there. The lookbehind keeps legitimately-embedded URLs
// whole (?url=https://…, archive.org/web/…/https://…).
const SCHEME_BOUNDARY = /(?<![=&?/])(?=https?:\/\/)/gi;

export function extractUrls(text: string): string[] {
  const matches = text.match(URL_RE) ?? [];
  return matches
    .flatMap((m) => m.split(SCHEME_BOUNDARY))
    .map((m) => m.replace(TRAILING_PUNCT, ""))
    .filter(Boolean);
}

const IG_HOSTS = new Set(["instagram.com", "www.instagram.com", "instagr.am"]);
const YT_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"]);
const X_HOSTS = new Set(["x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"]);
const STACK_EXCHANGE_DOMAINS = [
  "stackoverflow.com",
  "stackexchange.com",
  "superuser.com",
  "serverfault.com",
  "askubuntu.com",
  "mathoverflow.net",
];

/** `host` is `domain` or one of its subdomains. */
const hostIs = (host: string, domain: string) => host === domain || host.endsWith("." + domain);

// Any-host rejections: links that are navigation, not something to remember.
// Applied to hosts no per-source check handles (so a GitHub repo named
// "settings" isn't mistaken for an account page). `path` is matched against
// pathname + search. One rule per line — add new ones here.
const REJECT_RULES: { host?: RegExp; path?: RegExp; reason: string }[] = [
  { host: /^(www\.)?google\.[a-z.]+$/, path: /^\/search/, reason: "search results page" },
  { host: /^(www\.)?bing\.com$/, path: /^\/search/, reason: "search results page" },
  { host: /^(www\.|html\.)?duckduckgo\.com$/, path: /[?&]q=/, reason: "search results page" },
  { host: /^search\.yahoo\.com$/, reason: "search results page" },
  { host: /^(www\.)?google\.[a-z.]+$/, path: /^\/maps/, reason: "map link" },
  { host: /^(maps\.google\.[a-z.]+|maps\.app\.goo\.gl|maps\.apple\.com)$/, reason: "map link" },
  { host: /(^|\.)zoom\.us$/, path: /^\/(j|my|w)\//, reason: "invite/meeting link" },
  { host: /^(meet\.google\.com|teams\.microsoft\.com|teams\.live\.com)$/, reason: "invite/meeting link" },
  { host: /^(discord\.gg|t\.me|telegram\.me|chat\.whatsapp\.com|wa\.me)$/, reason: "invite/meeting link" },
  { host: /^(www\.)?discord\.com$/, path: /^\/invite\//, reason: "invite/meeting link" },
  { host: /^(www\.)?calendly\.com$/, reason: "invite/meeting link" },
  { host: /^(docs|drive)\.google\.com$/, reason: "needs a login — can't fetch" },
  { host: /(^|\.)dropbox\.com$/, reason: "needs a login — can't fetch" },
  { host: /^news\.ycombinator\.com$/, path: /^\/(?!item\?)/, reason: "Hacker News listing, not a post" },
  { host: /(^|\.)(tiktok\.com|facebook\.com|fb\.com|linkedin\.com|threads\.net|threads\.com)$/, reason: "not supported yet" },
  {
    path: /^[^?]*\/(login|signin|sign-in|signup|sign-up|register|logout|account|settings|checkout|cart)(\/|\?|$)/i,
    reason: "account/login page",
  },
  { path: /^[^?]*\.(zip|exe|dmg|pkg|msi|apk|iso|tar\.gz|tgz)(\?|$)/i, reason: "file download, not a page" },
  { path: /^[^?]*\.(png|jpe?g|gif|webp|svg|mp3|mp4|mov|wav|m4a)(\?|$)/i, reason: "media file — not until v4" },
];

// Literal private/loopback/link-local addresses. Cloud Run reaches the VPC
// (FalkorDB, its browser UI) through Direct VPC egress, so these must never be
// fetched — linked-post fan-out means link targets can come from strangers.
// Hostnames that merely resolve to private IPs need a fetch-time check too.
const PRIVATE_HOST =
  /^(localhost|0\.0\.0\.0|127\.[\d.]+|10\.[\d.]+|192\.168\.[\d.]+|169\.254\.[\d.]+|172\.(1[6-9]|2\d|3[01])\.[\d.]+|\[(::1?|::ffff:[0-9a-f:.]*|f[cd][0-9a-f:]*|fe80:[0-9a-f:]*)\])$|\.(local|internal|localhost)$/;

// Layer-1 validation: reject on URL shape alone — anything that's a profile,
// feed, listing, search page, or other navigation rather than a single piece of
// content. IG /p/ is ambiguous (image vs video vs carousel) — accepted here,
// resolved at fetch time on the Pi (Layer 2). Unrecognized hosts are treated
// as blogs; the blog pipeline rejects pages with no article text (Layer 2).
export function checkUrl(raw: string): CheckedUrl {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return { ok: false, url: raw, reason: "not a valid URL" };
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    return { ok: false, url: raw, reason: "unsupported scheme" };
  }

  const host = u.hostname.toLowerCase();
  const segs = u.pathname.split("/").filter(Boolean);

  if (PRIVATE_HOST.test(host)) return { ok: false, url: raw, reason: "private network address" };

  if (IG_HOSTS.has(host)) return checkInstagram(raw, segs);
  if (YT_HOSTS.has(host)) return checkYouTube(raw, u, segs);
  if (host === "youtu.be") {
    return segs.length >= 1
      ? { ok: true, url: raw, source: "youtube" }
      : { ok: false, url: raw, reason: "YouTube link has no video id" };
  }
  if (X_HOSTS.has(host)) return checkX(raw, segs);
  if (hostIs(host, "reddit.com") || hostIs(host, "redd.it")) return checkReddit(raw, host, segs);
  if (STACK_EXCHANGE_DOMAINS.some((d) => hostIs(host, d))) return checkStackExchange(raw, segs);
  if (host === "github.com" || host === "www.github.com") return checkGitHub(raw, segs);
  if (host === "gist.github.com") {
    return segs.length >= 2
      ? { ok: true, url: raw, source: "github" }
      : { ok: false, url: raw, reason: "GitHub profile/listing, not a repo, issue, or PR" };
  }

  const pathAndQuery = u.pathname + u.search;
  for (const rule of REJECT_RULES) {
    if ((!rule.host || rule.host.test(host)) && (!rule.path || rule.path.test(pathAndQuery))) {
      return { ok: false, url: raw, reason: rule.reason };
    }
  }
  if (/\.pdf$/i.test(u.pathname)) return { ok: true, url: raw, source: "pdf" };
  return { ok: true, url: raw, source: "blog" };
}

const NUMERIC = /^\d+$/;

function checkX(raw: string, segs: string[]): CheckedUrl {
  const [a, b, c, d] = segs.map((s) => s.toLowerCase());
  // /{user}/status/{id}, /i/status/{id}, /i/web/status/{id} — trailing
  // /photo/1, /analytics etc. are fine, the fetcher only needs the id.
  if (b === "status" && NUMERIC.test(c ?? "")) return { ok: true, url: raw, source: "x" };
  if (a === "i" && b === "web" && c === "status" && NUMERIC.test(d ?? "")) return { ok: true, url: raw, source: "x" };
  if (a === "i" && b === "spaces") return { ok: false, url: raw, reason: "X Spaces are audio — not until v4" };
  // Article ids aren't post ids and can't be fetched on their own.
  if (a === "i" && b === "article") {
    return { ok: false, url: raw, reason: "X article link — send the link to the post that shares it" };
  }
  return { ok: false, url: raw, reason: "X profile/page, not a post" };
}

function checkReddit(raw: string, host: string, segs: string[]): CheckedUrl {
  if (host === "i.redd.it" || host === "v.redd.it") {
    return { ok: false, url: raw, reason: "Reddit-hosted image/video — not until v4" };
  }
  if (host === "redd.it") {
    return segs.length === 1
      ? { ok: true, url: raw, source: "reddit" }
      : { ok: false, url: raw, reason: "Reddit subreddit/user/listing, not a post" };
  }
  const s = segs.map((x) => x.toLowerCase());
  // /r/{sub}/comments/{id}/… and /user/{name}/comments/{id}/… — a post, or a
  // comment when the permalink carries a comment id (the fetcher tells them apart).
  if (s[2] === "comments" && s[3] && (s[0] === "r" || s[0] === "user" || s[0] === "u")) {
    return { ok: true, url: raw, source: "reddit" };
  }
  if (s[0] === "comments" && s[1]) return { ok: true, url: raw, source: "reddit" };
  // Mobile share links (/r/{sub}/s/{token}) — resolved to the post when fetched.
  if (s[0] === "r" && s[2] === "s" && s[3]) return { ok: true, url: raw, source: "reddit" };
  if (s[0] === "gallery") return { ok: false, url: raw, reason: "Reddit image gallery — not until v4" };
  return { ok: false, url: raw, reason: "Reddit subreddit/user/listing, not a post" };
}

function checkStackExchange(raw: string, segs: string[]): CheckedUrl {
  const [a, b] = segs.map((s) => s.toLowerCase());
  if ((a === "questions" || a === "q" || a === "a") && NUMERIC.test(b ?? "")) {
    return { ok: true, url: raw, source: "stackexchange" };
  }
  return { ok: false, url: raw, reason: "Stack Exchange listing/profile, not a question" };
}

// First path segments on github.com that are site pages, not an owner.
const GITHUB_RESERVED = new Set([
  "search", "topics", "trending", "explore", "marketplace", "settings", "notifications",
  "orgs", "sponsors", "features", "pricing", "about", "new", "collections", "events",
  "codespaces", "pulls", "issues", "apps", "enterprise", "login", "signup", "dashboard",
]);
const GITHUB_ITEM_KINDS = new Set(["issues", "pull"]);

function checkGitHub(raw: string, segs: string[]): CheckedUrl {
  const s = segs.map((x) => x.toLowerCase());
  const reject: CheckedUrl = { ok: false, url: raw, reason: "GitHub profile/listing, not a repo, issue, or PR" };
  if (s.length < 2 || GITHUB_RESERVED.has(s[0])) return reject;
  if (s.length === 2) return { ok: true, url: raw, source: "github" }; // repo root → its README
  // No REST endpoint, and the rendered page carries every comment.
  if (s[2] === "discussions") return { ok: false, url: raw, reason: "GitHub discussions aren't supported yet" };
  if (GITHUB_ITEM_KINDS.has(s[2]) && NUMERIC.test(s[3] ?? "")) return { ok: true, url: raw, source: "github" };
  return reject;
}

const IG_POST_KINDS = new Set(["p", "reel", "reels", "tv"]);

function checkInstagram(raw: string, segs: string[]): CheckedUrl {
  const kind = segs[0]?.toLowerCase();
  if (!kind) return { ok: false, url: raw, reason: "Instagram home page, not a post" };
  if (kind === "stories") return { ok: false, url: raw, reason: "Instagram stories expire — can't fetch reliably" };
  if (!IG_POST_KINDS.has(kind)) return { ok: false, url: raw, reason: "Instagram profile/page, not a post" };
  if (segs.length < 2) return { ok: false, url: raw, reason: "Instagram post link is missing its id" };
  if (segs[2]?.toLowerCase() === "c") return { ok: false, url: raw, reason: "comment permalink, not the post itself" };
  return { ok: true, url: raw, source: "instagram" };
}

function checkYouTube(raw: string, u: URL, segs: string[]): CheckedUrl {
  const first = segs[0]?.toLowerCase();
  if (first === "watch") {
    return u.searchParams.get("v")
      ? { ok: true, url: raw, source: "youtube" }
      : { ok: false, url: raw, reason: "YouTube watch link has no video id" };
  }
  if ((first === "shorts" || first === "live") && segs.length >= 2) {
    return { ok: true, url: raw, source: "youtube" };
  }
  if (first === "playlist") return { ok: false, url: raw, reason: "YouTube playlist, not a single video" };
  return { ok: false, url: raw, reason: "YouTube channel/page, not a video" };
}
