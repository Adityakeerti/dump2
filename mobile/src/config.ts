/**
 * Runtime configuration. EXPO_PUBLIC_* variables are inlined at build time from mobile/.env
 * (see .env.example). Nothing environment-specific is hard-coded in the app.
 */
const rawBase = process.env.EXPO_PUBLIC_API_BASE_URL ?? "";
const apiBaseUrl = rawBase.replace(/\/+$/, "");

export const config = {
  apiBaseUrl,
  apiTimeoutMs: Number(process.env.EXPO_PUBLIC_API_TIMEOUT_MS ?? 15000),
  /**
   * Complaint module (no DB, JSON-backed): complaints, escalation ladder and govt-portal notices.
   * Unset = the reverse proxy route on the API base (Caddy maps /api/complaint-flow/* to it).
   */
  complaintServiceUrl: (process.env.EXPO_PUBLIC_COMPLAINT_SERVICE_URL || `${apiBaseUrl}/api/complaint-flow`).replace(/\/+$/, ""),
};

/**
 * Government notices feed: the JSON the govt portal publishes (e.g. https://govtwebsite.vercel.app/api/notices,
 * which serves the portal's data/notices.json). Unset = the complaint module's /api/notices.
 */
export const noticesUrl = (process.env.EXPO_PUBLIC_NOTICES_URL || `${config.complaintServiceUrl}/api/notices`).replace(/\/+$/, "");

export const isConfigured = /^https?:\/\//.test(config.apiBaseUrl);

/** Resolves a server-relative path (e.g. "/avatars/amit.png") against the API base URL. */
export function absoluteUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${config.apiBaseUrl}${path.startsWith("/") ? "" : "/"}${path}`;
}

/** STOMP endpoint derived from the API base (http -> ws, https -> wss). */
export function websocketUrl(path = "/ws"): string {
  return config.apiBaseUrl.replace(/^http/, "ws") + path;
}
