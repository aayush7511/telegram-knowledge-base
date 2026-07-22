// Integration tests for POST /status — Cloud Run's D1 proxy. Runs against the
// real Worker in workerd with a miniflare-backed D1.
import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { seedJob, textJob, getRow } from "./fixtures";

const SECRET = "test-worker2-secret";

function post(body: unknown, secret: string | null = SECRET): Promise<Response> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (secret !== null) headers["X-KB-Secret"] = secret;
  return SELF.fetch("https://kb-forward.test/status", {
    method: "POST",
    headers,
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

describe("auth & routing", () => {
  it("rejects a wrong secret with 401", async () => {
    await seedJob(textJob("j1"));
    const res = await post({ job_id: "j1", state: "saved" }, "wrong");
    expect(res.status).toBe(401);
    expect((await getRow("j1"))!.state).toBe("queued");
  });

  it("rejects a missing secret with 401", async () => {
    const res = await post({ job_id: "j1", state: "saved" }, null);
    expect(res.status).toBe(401);
  });

  it("404s other paths and methods", async () => {
    expect((await SELF.fetch("https://kb-forward.test/", { method: "GET" })).status).toBe(404);
    expect((await SELF.fetch("https://kb-forward.test/status", { method: "GET" })).status).toBe(404);
  });
});

describe("validation", () => {
  it("400s on malformed JSON", async () => {
    const res = await post("{not json");
    expect(res.status).toBe(400);
  });

  it("400s on missing job_id", async () => {
    const res = await post({ state: "saved" });
    expect(res.status).toBe(400);
  });

  it.each(["received", "queued", "forwarded", "garbage", ""])(
    "400s on non-reportable state %j",
    async (state) => {
      await seedJob(textJob("j1"));
      const res = await post({ job_id: "j1", state });
      expect(res.status).toBe(400);
      expect((await getRow("j1"))!.state).toBe("queued");
    },
  );

  it("404s on unknown job_id", async () => {
    const res = await post({ job_id: "nope", state: "saved" });
    expect(res.status).toBe(404);
  });
});

describe("state updates", () => {
  it("updates state and updated_at", async () => {
    await seedJob(textJob("j1"));
    const before = (await getRow("j1"))!;
    const res = await post({ job_id: "j1", state: "transcribing" });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    const after = (await getRow("j1"))!;
    expect(after.state).toBe("transcribing");
    expect(after.updated_at).not.toBe(before.updated_at);
  });

  it("keeps existing r2_key when the update omits it", async () => {
    await seedJob(textJob("j1"), "fetching", "raw-media/j1.mp3");
    await post({ job_id: "j1", state: "transcribing" });
    expect((await getRow("j1"))!.r2_key).toBe("raw-media/j1.mp3");
  });

  it("sets r2_key when provided (Pi fetch fills it in)", async () => {
    await seedJob(textJob("j1"), "fetching", null);
    await post({ job_id: "j1", state: "transcribing", r2_key: "raw-media/j1.mp3" });
    expect((await getRow("j1"))!.r2_key).toBe("raw-media/j1.mp3");
  });

  it("stores error on failed", async () => {
    await seedJob(textJob("j1"));
    await post({ job_id: "j1", state: "failed", error: "yt-dlp: video unavailable" });
    const row = (await getRow("j1"))!;
    expect(row.state).toBe("failed");
    expect(row.error).toBe("yt-dlp: video unavailable");
  });

  it("clears a stale error on a recovery update", async () => {
    await seedJob(textJob("j1"));
    await post({ job_id: "j1", state: "failed", error: "transient" });
    await post({ job_id: "j1", state: "transcribing" });
    const row = (await getRow("j1"))!;
    expect(row.state).toBe("transcribing");
    expect(row.error).toBeNull();
  });
});
