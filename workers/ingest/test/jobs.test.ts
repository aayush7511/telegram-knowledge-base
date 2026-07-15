import { describe, expect, it } from "vitest";
import { buildMediaJob, buildTextMessageJobs } from "../src/jobs";
import { idFactory, message, textMessage, OWNER_CHAT_ID } from "./fixtures";

const NOW = "2026-07-15T12:00:00.000Z";

describe("buildTextMessageJobs", () => {
  it("plain text → one inline text job, no group", () => {
    const msg = textMessage("remember: graphiti uses falkordb");
    const { jobs, rejected } = buildTextMessageJobs(msg, { now: NOW, makeId: idFactory() });

    expect(rejected).toEqual([]);
    expect(jobs).toHaveLength(1);
    expect(jobs[0]).toMatchObject({
      content_type: "text",
      text: "remember: graphiti uses falkordb",
      group_id: null,
      chat_id: OWNER_CHAT_ID,
      message_id: msg.message_id,
      time_received: NOW,
    });
  });

  it("single bare URL → one url job, no group, no caption", () => {
    const msg = textMessage("https://youtu.be/dQw4w9WgXcQ");
    const { jobs } = buildTextMessageJobs(msg, { now: NOW, makeId: idFactory() });

    expect(jobs).toHaveLength(1);
    expect(jobs[0]).toMatchObject({
      content_type: "url",
      url: "https://youtu.be/dQw4w9WgXcQ",
      url_source: "youtube",
      group_id: null,
    });
    expect(jobs[0].caption).toBeUndefined();
  });

  it("multiple URLs with prose → fan-out sharing a group_id, caption = full text", () => {
    const text =
      "two good ones: https://youtu.be/abc123 and https://www.instagram.com/reel/Cxyz1234abc/ watch later";
    const { jobs, rejected } = buildTextMessageJobs(textMessage(text), { now: NOW, makeId: idFactory() });

    expect(rejected).toEqual([]);
    expect(jobs).toHaveLength(2);
    expect(jobs[0].group_id).not.toBeNull();
    expect(jobs[0].group_id).toBe(jobs[1].group_id);
    expect(jobs[0].job_id).not.toBe(jobs[1].job_id);
    expect(jobs.map((j) => j.url_source)).toEqual(["youtube", "instagram"]);
    expect(jobs[0].caption).toBe(text);
  });

  it("mixed valid/invalid URLs → jobs only for valid, rejects reported", () => {
    const text = "https://youtu.be/abc123 https://www.instagram.com/natgeo/";
    const { jobs, rejected } = buildTextMessageJobs(textMessage(text), { now: NOW, makeId: idFactory() });

    expect(jobs).toHaveLength(1);
    expect(jobs[0].url).toBe("https://youtu.be/abc123");
    expect(rejected).toHaveLength(1);
    expect(rejected[0].url).toBe("https://www.instagram.com/natgeo/");
  });

  it("all URLs invalid → no jobs, all rejected", () => {
    const { jobs, rejected } = buildTextMessageJobs(textMessage("https://www.youtube.com/@mkbhd"), {
      now: NOW,
      makeId: idFactory(),
    });
    expect(jobs).toHaveLength(0);
    expect(rejected).toHaveLength(1);
  });
});

describe("buildMediaJob", () => {
  it("carries media info, caption, and album media_group_id through", () => {
    const msg = message({ media_group_id: "album-7", caption: "trip photos" });
    const job = buildMediaJob(
      msg,
      "photo",
      { r2_key: "raw-media/j1.jpg", mime_type: "image/jpeg", size_bytes: 150_000, duration_seconds: null },
      { now: NOW, job_id: "j1" },
    );

    expect(job).toMatchObject({
      job_id: "j1",
      group_id: "album-7",
      content_type: "photo",
      caption: "trip photos",
      media: { r2_key: "raw-media/j1.jpg", mime_type: "image/jpeg", size_bytes: 150_000 },
    });
  });

  it("group_id is null outside albums", () => {
    const job = buildMediaJob(
      message(),
      "voice",
      { r2_key: "raw-media/j2.ogg", mime_type: "audio/ogg", size_bytes: 9_000, duration_seconds: 12 },
      { now: NOW, job_id: "j2" },
    );
    expect(job.group_id).toBeNull();
    expect(job.caption).toBeUndefined();
  });
});
