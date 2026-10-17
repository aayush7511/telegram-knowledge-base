// Integration tests for POST /retry (specs/youtube-home-worker.md test 16):
// Worker 2 rebuilds the job's queue message from its D1 row and puts it back
// on kb-jobs with a delay. Runs on the real queue in workerd — the consumer
// delivers it to the fake Cloud Run, which records what it received.
import { SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { seedJob, getRow, youtubeJob } from "./fixtures";

const SECRET = "test-worker2-secret";
const JOBS_LOG = "https://fake-cloud-run.test/__jobs";

function postRetry(body: unknown, secret: string | null = SECRET): Promise<Response> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (secret !== null) headers["X-KB-Secret"] = secret;
  return SELF.fetch("https://kb-forward.test/retry", {
    method: "POST",
    headers,
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function deliveredJobs(job_id: string): Promise<Record<string, unknown>[]> {
  const all = (await (await fetch(JOBS_LOG)).json()) as Record<string, unknown>[];
  return all.filter((j) => j.job_id === job_id);
}

async function waitForDelivery(job_id: string, timeoutMs = 5000): Promise<Record<string, unknown>[]> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const jobs = await deliveredJobs(job_id);
    if (jobs.length > 0) return jobs;
    await new Promise((r) => setTimeout(r, 100));
  }
  return [];
}

beforeEach(async () => {
  await fetch(JOBS_LOG, { method: "DELETE" });
});

describe("auth & validation", () => {
  it("rejects a wrong secret with 401 and enqueues nothing", async () => {
    await seedJob(youtubeJob("y1"), "retrying");
    const res = await postRetry({ job_id: "y1", delay_seconds: 0 }, "wrong");
    expect(res.status).toBe(401);
    expect((await getRow("y1"))!.retry_count).toBe(0);
    await new Promise((r) => setTimeout(r, 500));
    expect(await deliveredJobs("y1")).toEqual([]);
  });

  it("rejects a missing secret with 401", async () => {
    const res = await postRetry({ job_id: "y1", delay_seconds: 0 }, null);
    expect(res.status).toBe(401);
  });

  it("404s an unknown job", async () => {
    const res = await postRetry({ job_id: "nope", delay_seconds: 0 });
    expect(res.status).toBe(404);
  });

  it.each([
    [{ delay_seconds: 0 }],
    [{ job_id: "y1" }],
    [{ job_id: "y1", delay_seconds: -1 }],
    [{ job_id: "y1", delay_seconds: "soon" }],
  ])("400s a bad body %j", async (body) => {
    await seedJob(youtubeJob("y1"), "retrying");
    const res = await postRetry(body);
    expect(res.status).toBe(400);
    expect((await getRow("y1"))!.retry_count).toBe(0);
  });
});

describe("re-enqueue", () => {
  it("rebuilds the message from the D1 row, with the retry count, and enqueues it", async () => {
    await seedJob(youtubeJob("y1"), "retrying");
    const res = await postRetry({ job_id: "y1", delay_seconds: 0 });
    expect(res.status).toBe(200);
    expect((await getRow("y1"))!.retry_count).toBe(1);

    const [job] = await waitForDelivery("y1");
    expect(job).toMatchObject({
      job_id: "y1",
      group_id: null,
      chat_id: 12345,
      message_id: 2,
      time_received: "2026-10-10T15:00:00.000Z",
      content_type: "url",
      url: "https://youtu.be/zjkBMFhNj_g",
      url_source: "youtube",
      retry_count: 1,
    });
  });

  it("increments the count on each retry", async () => {
    await seedJob(youtubeJob("y1"), "retrying", null, 2);
    await postRetry({ job_id: "y1", delay_seconds: 0 });
    expect((await getRow("y1"))!.retry_count).toBe(3);
    const [job] = await waitForDelivery("y1");
    expect(job.retry_count).toBe(3);
  });

  it("holds the message back for delay_seconds", async () => {
    await seedJob(youtubeJob("y1"), "retrying");
    await postRetry({ job_id: "y1", delay_seconds: 2 });
    await new Promise((r) => setTimeout(r, 1000));
    expect(await deliveredJobs("y1")).toEqual([]);
    expect(await waitForDelivery("y1", 5000)).toHaveLength(1);
  });
});
