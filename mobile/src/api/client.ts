import { config } from "../config";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields?: Record<string, string>,
  ) {
    super(message);
  }
}

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

/** Registered by the auth provider so an expired session signs the user out. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

type Query = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, query?: Query, baseUrl = config.apiBaseUrl) {
  const url = `${baseUrl}${path}`;
  if (!query) return url;
  const params = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return params ? `${url}?${params}` : url;
}

export async function request<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  // baseUrl: another CitySense service (e.g. the complaint module); defaults to core.
  opts: { body?: unknown; query?: Query; auth?: boolean; timeoutMs?: number; baseUrl?: string } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? config.apiTimeoutMs);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false && authToken) headers.Authorization = `Bearer ${authToken}`;

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query, opts.baseUrl), {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    const aborted = e instanceof Error && e.name === "AbortError";
    throw new ApiError(0, aborted ? "The server took too long to respond" : "Can't reach the CitySense server");
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  const data = text ? safeJson(text) : undefined;
  if (!res.ok) {
    if (res.status === 401 && opts.auth !== false && authToken) onUnauthorized?.();
    const problem = (data ?? {}) as { fields?: Record<string, string> };
    const fieldMsg = problem.fields ? Object.values(problem.fields)[0] : undefined;
    throw new ApiError(res.status, fieldMsg ?? problemMessage(data, res.status), problem.fields);
  }
  return data as T;
}

/**
 * Multipart upload (voice notes, complaint photos). Same auth, timeout and error mapping as `request`.
 *
 * Uses React Native's XMLHttpRequest, not fetch: Expo SDK 58 replaces the global fetch with
 * `expo/fetch`, whose FormData converter rejects React Native file parts (`{ uri, name, type }`) with
 * "Unsupported FormDataPart implementation" before anything is sent (node_modules/expo/src/winter/
 * fetch/convertFormData.ts). RN's XHR hands the parts to the native networking module, which streams
 * the file from disk.
 */
export function requestForm<T>(
  path: string,
  form: FormData,
  opts: { timeoutMs?: number; baseUrl?: string; auth?: boolean } = {},
): Promise<T> {
  const sendAuth = opts.auth !== false && !!authToken;
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", buildUrl(path, undefined, opts.baseUrl));
    xhr.timeout = opts.timeoutMs ?? 45000;
    xhr.setRequestHeader("Accept", "application/json");
    if (sendAuth) xhr.setRequestHeader("Authorization", `Bearer ${authToken}`);
    xhr.onload = () => {
      const data = xhr.responseText ? safeJson(xhr.responseText) : undefined;
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as T);
        return;
      }
      if (xhr.status === 401 && sendAuth) onUnauthorized?.();
      reject(new ApiError(xhr.status, problemMessage(data, xhr.status)));
    };
    xhr.ontimeout = () => reject(new ApiError(0, "The server took too long to respond"));
    xhr.onerror = () => reject(new ApiError(0, "Can't reach the CitySense server (upload failed)"));
    try {
      xhr.send(form);
    } catch (e) {
      // Surface the real reason instead of a generic "can't reach" so device issues are diagnosable.
      reject(new ApiError(0, `Upload could not start: ${e instanceof Error ? e.message : String(e)}`));
    }
  });
}

/**
 * Human message from an error body. Core sends RFC 7807 `{ detail: string }`; the Python services send
 * FastAPI's `{ detail: string | { message } | [{ msg }] }` (e.g. the complaint guardrail rejection).
 */
function problemMessage(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  if (detail && typeof (detail as { message?: unknown }).message === "string") return (detail as { message: string }).message;
  return `Request failed (${status})`;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}
