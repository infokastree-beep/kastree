/**
 * Browser → FastAPI helper.
 *
 * In the browser, calls stay on this site at `/backend-api`. Next rewrites that
 * prefix to NEXT_PUBLIC_API_BASE_URL, so a privacy setting that blocks
 * cross-site requests to the Railway host still lets Clients and Upload load.
 * Server-side calls use the upstream URL directly.
 *
 * Clerk Bearer tokens are sent on both paths.
 */

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** Pull a human-readable message from FastAPI `detail` (string or object). */
function extractErrorDetail(body: unknown, status: number): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return `API ${status}`;
  }
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (typeof detail === "object" && detail !== null) {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.detail === "string") {
      return obj.detail;
    }
    if (typeof obj.message === "string") {
      return obj.message;
    }
  }
  return `API ${status}`;
}

/** Best-effort existing_tb_id from a 409 upload conflict body. */
export function existingTbIdFromConflict(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return null;
  }
  const body = error.body;
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return null;
  }
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail !== "object" || detail === null) {
    return null;
  }
  const id = (detail as { existing_tb_id?: unknown }).existing_tb_id;
  return typeof id === "string" && id.length > 0 ? id : null;
}

/** Best-effort existing_status from a 409 upload conflict body. */
export function existingTbStatusFromConflict(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return null;
  }
  const body = error.body;
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return null;
  }
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail !== "object" || detail === null) {
    return null;
  }
  const statusValue = (detail as { existing_status?: unknown }).existing_status;
  return typeof statusValue === "string" && statusValue.length > 0
    ? statusValue
    : null;
}

/** Same-origin prefix. next.config.mjs rewrites this to the upstream API. */
export const SAME_ORIGIN_API_PREFIX = "/backend-api";

function upstreamApiBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!base) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not set. Copy frontend/.env.example to .env.local.",
    );
  }
  return base.replace(/\/$/, "");
}

export function getApiBaseUrl(): string {
  const upstream = upstreamApiBaseUrl();
  if (typeof window !== "undefined") {
    return SAME_ORIGIN_API_PREFIX;
  }
  return upstream;
}

type TokenGetter = () => Promise<string | null>;

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { getToken?: TokenGetter } = {},
): Promise<T> {
  const { getToken, ...init } = options;
  const headers = new Headers(init.headers);
  if (getToken) {
    const token = await getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // ngrok free tier serves an HTML interstitial to browser cross-origin requests unless
  // this header is present (ERR_NGROK_6024). Harmless on non-ngrok backends.
  if (upstreamApiBaseUrl().includes("ngrok")) {
    headers.set("ngrok-skip-browser-warning", "true");
  }

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers,
    });
  } catch {
    throw new ApiError(
      "Could not reach the server. Check your connection and try again.",
      0,
      null,
    );
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = await response.text().catch(() => null);
    }
    const detail = extractErrorDetail(body, response.status);
    throw new ApiError(detail, response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
