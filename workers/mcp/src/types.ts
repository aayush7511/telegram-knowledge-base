import type { OAuthHelpers } from "@cloudflare/workers-oauth-provider";

// Worker 1's save entrypoint (workers/ingest/src/index.ts, IngestRpc). The
// workers are deliberately self-contained, so its shape is restated here.
export interface SaveResult {
  jobs: { job_id: string; url: string | null }[]; // url null → saved as a note
  rejected: { url: string; reason: string }[];
}

export interface IngestRpc {
  createJobs(content: string, clientName: string): Promise<SaveResult>;
}

export interface Env {
  OAUTH_KV: KVNamespace;
  OAUTH_PROVIDER: OAuthHelpers; // injected by OAuthProvider
  DB: D1Database;
  INGEST: IngestRpc;
  CLOUD_RUN_URL: string;
  CLOUD_RUN_SECRET: string;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  OWNER_GOOGLE_SUB: string; // the owner's Google account id; empty until first sign-in shows it
}

/** Stored (encrypted) with each grant at sign-in; the MCP handler gets it back as ctx.props. */
export interface Props {
  clientName: string;
}
