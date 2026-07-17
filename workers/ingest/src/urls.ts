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

// Layer-1 validation: reject on URL shape alone (profiles, channels, playlists,
// comment permalinks). /p/ is ambiguous (image vs video vs carousel) — accepted
// here, resolved at fetch time on the Pi (Layer 2).
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

  if (IG_HOSTS.has(host)) return checkInstagram(raw, segs);
  if (YT_HOSTS.has(host)) return checkYouTube(raw, u, segs);
  if (host === "youtu.be") {
    return segs.length >= 1
      ? { ok: true, url: raw, source: "youtube" }
      : { ok: false, url: raw, reason: "YouTube link has no video id" };
  }
  return { ok: true, url: raw, source: "blog" };
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
