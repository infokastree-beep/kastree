/**
 * Browser → FastAPI helper.
 *
 * Calls go to NEXT_PUBLIC_API_BASE_URL with Clerk Bearer tokens.
 * CORS must allow the frontend origin on the API (see backend CORSMiddleware).
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

export function getApiBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!base) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not set. Copy frontend/.env.example to .env.local.",
    );
  }
  return base.replace(/\/$/, "");
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
  if (getApiBaseUrl().includes("ngrok")) {
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
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
        ? (body as { detail: string }).detail
        : `API ${response.status}`;
    throw new ApiError(detail, response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
