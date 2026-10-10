/**
 * Queues a composed Word file and downloads it when the job is ready.
 * The browser calls `/backend-api/...` with the Clerk bearer token.
 */

import { getApiBaseUrl } from "@/lib/api";
import {
  DRAFT_WORD_FILENAME,
  wordProgressLabel,
} from "@/lib/draft-word-status";
import { messageFromPdfBody } from "@/lib/workspace-load-error";

export {
  DRAFT_WORD_FILENAME,
  WORD_DOWNLOAD_LABEL,
  WORD_PROGRESS_LABEL,
  wordProgressLabel,
} from "@/lib/draft-word-status";

const WORD_FAILED = "The Word file could not be prepared.";
const DOCX_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

type TokenGetter = () => Promise<string | null>;

type WordJob = {
  job_id: string;
  status: "pending" | "running" | "ready" | "failed";
  error_message: string | null;
};

function draftWordBase(yearEndId: string, draftId: string): string {
  return `/year-ends/${yearEndId}/drafts/${draftId}`;
}

async function authed(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<Response> {
  try {
    return await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
}

async function readJob(response: Response): Promise<WordJob> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new Error(messageFromPdfBody(body) ?? WORD_FAILED);
  }
  if (
    typeof body !== "object" ||
    body === null ||
    !("job_id" in body) ||
    !("status" in body)
  ) {
    throw new Error(WORD_FAILED);
  }
  const record = body as {
    job_id: unknown;
    status: unknown;
    error_message?: unknown;
  };
  if (typeof record.job_id !== "string" || typeof record.status !== "string") {
    throw new Error(WORD_FAILED);
  }
  if (
    record.status !== "pending" &&
    record.status !== "running" &&
    record.status !== "ready" &&
    record.status !== "failed"
  ) {
    throw new Error(WORD_FAILED);
  }
  return {
    job_id: record.job_id,
    status: record.status,
    error_message:
      typeof record.error_message === "string" ? record.error_message : null,
  };
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadDraftWord(
  yearEndId: string,
  draftId: string,
  getToken: TokenGetter,
): Promise<void> {
  const token = await getToken();
  if (!token) {
    throw new Error("Sign in to download the Word file.");
  }
  const base = draftWordBase(yearEndId, draftId);
  const created = await authed(`${base}/document.docx`, token, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  let job = await readJob(created);
  for (let attempt = 0; attempt < 40 && wordProgressLabel(job.status); attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    const polled = await authed(`${base}/render-jobs/${job.job_id}`, token);
    job = await readJob(polled);
  }
  if (job.status === "failed") {
    throw new Error(job.error_message ?? WORD_FAILED);
  }
  if (job.status !== "ready") {
    throw new Error(WORD_FAILED);
  }
  const download = await authed(
    `${base}/render-jobs/${job.job_id}/download`,
    token,
  );
  if (!download.ok) {
    let body: unknown = null;
    try {
      body = await download.json();
    } catch {
      body = null;
    }
    throw new Error(messageFromPdfBody(body) ?? WORD_FAILED);
  }
  const type = download.headers.get("content-type") ?? "";
  if (!type.includes(DOCX_TYPE)) {
    throw new Error(WORD_FAILED);
  }
  const filename = download.headers.get("content-disposition")?.includes("final")
    ? "statutory-statements-final.docx"
    : DRAFT_WORD_FILENAME;
  saveBlob(await download.blob(), filename);
}
