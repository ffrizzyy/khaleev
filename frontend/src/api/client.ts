/**
 * The one `fetch` wrapper every API module goes through.
 *
 * It owns the `/api` base URL (so the Vite dev proxy and the production
 * same-origin server both work unchanged), JSON encoding, and the conversion of
 * a failed response into a typed {@link ApiError} the UI can render instead of
 * an unhandled rejection.
 *
 * Multipart uploads pass a `FormData` body and deliberately never set
 * `Content-Type`: the browser has to add the multipart boundary itself, and
 * setting the header manually breaks the upload inside FastAPI.
 */

export const API_BASE_URL = "/api";

/** A non-2xx response, carrying what the UI needs to explain it. */
export class ApiError extends Error {
  /** The HTTP status code, e.g. 400, 404, 422 or 503. */
  readonly status: number;
  /** A human-readable detail; FastAPI's `detail` field, flattened if necessary. */
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Narrow an unknown rejected value to {@link ApiError}. */
export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiRequestOptions {
  method?: HttpMethod;
  /** JSON request body; serialised and labelled `application/json`. */
  json?: unknown;
  /** Multipart request body; sent as-is with no `Content-Type` header. */
  formData?: FormData;
  headers?: HeadersInit;
  signal?: AbortSignal;
}

/**
 * Send one request and parse its JSON response.
 *
 * @throws {ApiError} when the response status is not 2xx.
 * @throws {TypeError} when both `json` and `formData` are supplied.
 */
export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = "GET", json, formData, headers: extraHeaders, signal } = options;
  if (json !== undefined && formData !== undefined) {
    throw new TypeError("apiRequest: pass either `json` or `formData`, never both");
  }

  const headers = new Headers(extraHeaders);
  let body: BodyInit | undefined;
  if (formData !== undefined) {
    body = formData;
  } else if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }

  const response = await fetch(urlFor(path), { method, headers, body, signal });
  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function urlFor(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

async function toApiError(response: Response): Promise<ApiError> {
  const fallback = `Request failed with status ${response.status}`;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return new ApiError(response.status, fallback);
  }
  return new ApiError(response.status, describeDetail(payload) ?? fallback);
}

/**
 * FastAPI sends `detail` as a string for domain errors (400/404/503) and as a
 * list of validation objects for 422. Flatten both shapes into one sentence.
 */
function describeDetail(payload: unknown): string | null {
  if (typeof payload === "string") {
    const trimmed = payload.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (Array.isArray(payload)) {
    const messages = payload
      .map((item) => describeDetail(item))
      .filter((message): message is string => message !== null);
    return messages.length > 0 ? Array.from(new Set(messages)).join("; ") : null;
  }
  if (typeof payload === "object" && payload !== null) {
    const record = payload as Record<string, unknown>;
    if ("detail" in record) {
      const nested = describeDetail(record.detail);
      if (nested !== null) {
        return nested;
      }
    }
    if (typeof record.msg === "string" && record.msg.trim().length > 0) {
      return record.msg;
    }
  }
  return null;
}
