// Integration tests for the queue consumer: batches are delivered straight to
// worker.queue() in workerd; outbound Cloud Run calls hit the fake in
// vitest.config.ts (job ids containing "boom" get a 500).
import {
  createExecutionContext,
  createMessageBatch,
  env,
  getQueueResult,
  waitOnExecutionContext,
} from "cloudflare:test";
import { describe, expect, it } from "vitest";
import worker from "../src/index";
import type { JobDescriptor } from "../src/types";
import { seedJob, textJob, getRow } from "./fixtures";

async function deliver(jobs: JobDescriptor[]) {
  const batch = createMessageBatch<JobDescriptor>(
    "kb-jobs",
    jobs.map((body) => ({
      id: `msg-${body.job_id}`,
      timestamp: new Date(),
      body,
      attempts: 1,
    })),
  );
  const ctx = createExecutionContext();
  await worker.queue(batch, env, ctx);
  await waitOnExecutionContext(ctx);
  return getQueueResult(batch, ctx);
}

describe("queue consumer", () => {
  it("forwards a job to Cloud Run, marks it forwarded, and acks", async () => {
    const job = textJob("j1");
    await seedJob(job);
    const result = await deliver([job]);
    expect(result.explicitAcks).toEqual(["msg-j1"]);
    expect(result.retryMessages).toEqual([]);
    expect((await getRow("j1"))!.state).toBe("forwarded");
  });

  it("retries on a Cloud Run 500 and leaves the row queued", async () => {
    const job = textJob("boom-1");
    await seedJob(job);
    const result = await deliver([job]);
    expect(result.explicitAcks).toEqual([]);
    expect(result.retryMessages.map((m: { msgId: string }) => m.msgId)).toEqual(["msg-boom-1"]);
    expect((await getRow("boom-1"))!.state).toBe("queued");
  });

  it("isolates failures within a batch: good jobs ack, bad ones retry", async () => {
    const good1 = textJob("j1");
    const bad = textJob("boom-2");
    const good2 = textJob("j2");
    await Promise.all([seedJob(good1), seedJob(bad), seedJob(good2)]);

    const result = await deliver([good1, bad, good2]);
    expect(result.explicitAcks.sort()).toEqual(["msg-j1", "msg-j2"]);
    expect(result.retryMessages.map((m: { msgId: string }) => m.msgId)).toEqual(["msg-boom-2"]);
    expect((await getRow("j1"))!.state).toBe("forwarded");
    expect((await getRow("j2"))!.state).toBe("forwarded");
    expect((await getRow("boom-2"))!.state).toBe("queued");
  });

  it("does not regress a job whose status already advanced past forwarded", async () => {
    // Cloud Run's status callback can land before its /jobs response does —
    // the stub does exactly this. forwarded must only apply to queued rows.
    const job = textJob("j1");
    await seedJob(job, "summarizing");
    const result = await deliver([job]);
    expect(result.explicitAcks).toEqual(["msg-j1"]);
    expect((await getRow("j1"))!.state).toBe("summarizing");
  });

  it("sends the full descriptor and the shared secret (fake 401s otherwise)", async () => {
    // The fake Cloud Run rejects wrong/missing secrets with 401, which would
    // surface here as a retry instead of an ack.
    const job = textJob("j1", { caption: "with caption" });
    await seedJob(job);
    const result = await deliver([job]);
    expect(result.explicitAcks).toEqual(["msg-j1"]);
  });
});
