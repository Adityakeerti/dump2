import { config, noticesUrl } from "../config";
import { request, requestForm } from "./client";
import { type FlowComplaint, newestFirst, toComplaint } from "./complaintFlow";
import type {
  AgentReply,
  AudioPreference,
  Avatar,
  AirQuality,
  AvatarChatResponse,
  Business,
  CityWeather,
  WeatherForecast,
  ConfirmResult,
  ChatIntent,
  CityEvent,
  Complaint,
  ComplaintMeta,
  Incident,
  MapConfig,
  Notice,
  OtpSentResponse,
  Place,
  ToggleResponse,
  TokenResponse,
  User,
} from "./types";

export const authApi = {
  login: (email: string, password: string) =>
    request<TokenResponse>("POST", "/api/auth/login", { body: { email, password }, auth: false }),
  register: (body: { email: string; password: string; fullName: string; language?: string }) =>
    request<TokenResponse>("POST", "/api/auth/register", { body, auth: false }),
  sendOtp: (email: string) => request<OtpSentResponse>("POST", "/api/auth/otp/send", { body: { email }, auth: false }),
  verifyOtp: (email: string, code: string) =>
    request<TokenResponse>("POST", "/api/auth/otp/verify", { body: { email, code }, auth: false }),
  me: () => request<User>("GET", "/api/auth/me"),
  forgotPassword: (email: string) =>
    request<OtpSentResponse>("POST", "/api/auth/password/forgot", { body: { email }, auth: false }),
  resetPassword: (email: string, code: string, newPassword: string) =>
    request<TokenResponse>("POST", "/api/auth/password/reset", { body: { email, code, newPassword }, auth: false }),
};

export const geoApi = {
  config: () => request<MapConfig>("GET", "/api/geo/config", { auth: false }),
  geocode: (q: string, near?: { lat: number; lng: number }) =>
    request<{ places: Place[] }>("GET", "/api/geo/geocode", { query: { q, limit: 5, lat: near?.lat, lng: near?.lng } }),
  reverse: (lat: number, lng: number) => request<Place>("GET", "/api/geo/reverse", { query: { lat, lng } }),
};

export const avatarApi = {
  nearby: (lat: number, lng: number, radiusMeters: number) =>
    request<Avatar[]>("GET", "/api/avatars", { query: { lat, lng, radiusMeters } }),
  search: (q: string, near?: { lat: number; lng: number }) =>
    request<Avatar[]>("GET", "/api/avatars", { query: { q, lat: near?.lat, lng: near?.lng, radiusMeters: near ? 50000 : undefined } }),
  get: (id: string) => request<Avatar>("GET", `/api/avatars/${id}`),
  saved: () => request<Avatar[]>("GET", "/api/avatars/saved"),
  setSaved: (id: string, on: boolean) => request<ToggleResponse>(on ? "PUT" : "DELETE", `/api/avatars/${id}/save`),
  setLiked: (id: string, on: boolean) => request<ToggleResponse>(on ? "PUT" : "DELETE", `/api/avatars/${id}/like`),
  chat: (
    id: string,
    body: { message?: string; intent?: ChatIntent; language?: string; sessionId?: string; latitude?: number; longitude?: number },
  ) =>
    // The agent may plan several steps (geocode, dispatch, draft a complaint): allow more than the default timeout.
    request<AvatarChatResponse>("POST", `/api/avatars/${id}/chat`, { body, timeoutMs: 45000 }),
};

/** Voice agent: speech-to-text, text-to-speech clips, action confirmation, speaker preference. */
export const agentApi = {
  transcribe: (form: FormData) => requestForm<{ text: string; lang: string | null }>("/api/agent/voice", form),
  speak: (text: string, language: string) =>
    request<{ clipId: string; url: string }>("POST", "/api/agent/tts/clips", { body: { text, language }, timeoutMs: 30000 }),
  confirm: (token: string) =>
    request<ConfirmResult>("POST", `/api/agent/actions/${encodeURIComponent(token)}/confirm`, { timeoutMs: 30000 }),
  /** Attach a camera photo (stored server-side in the database) to a drafted complaint before confirming. */
  attachPhoto: (token: string, uri: string) => {
    const form = new FormData();
    form.append("file", { uri, name: "evidence.jpg", type: "image/jpeg" } as unknown as Blob);
    return requestForm<{ mediaId: string; contentType: string; sizeBytes: number }>(
      `/api/agent/actions/${encodeURIComponent(token)}/photo`,
      form,
      { timeoutMs: 60000 },
    );
  },
  cancel: (token: string) => request<ConfirmResult>("POST", `/api/agent/actions/${encodeURIComponent(token)}/cancel`),
  /** The main agent (assistant island): full hierarchy, can also drive the app via clientActions. */
  assistant: (body: {
    message: string;
    sessionId?: string;
    language?: "hi" | "en";
    latitude?: number;
    longitude?: number;
    screen?: string;
  }) => request<AgentReply>("POST", "/api/agent/assistant", { body, timeoutMs: 60000 }),
  /** Main agent about a tapped map point; pass `question` (+ sessionId) for follow-ups through the full hierarchy. */
  place: (body: {
    latitude: number;
    longitude: number;
    label?: string;
    question?: string;
    sessionId?: string;
    language?: "hi" | "en";
  }) => request<AgentReply>("POST", "/api/agent/place", { body, timeoutMs: 60000 }),
  audioPreference: () => request<AudioPreference>("GET", "/api/agent/preferences/audio"),
  setAudioPreference: (pref: AudioPreference) =>
    request<AudioPreference>("PUT", "/api/agent/preferences/audio", { body: pref }),
};

/** Complaint module: no database, one demo citizen; the core JWT is not sent there. */
const flow = { baseUrl: config.complaintServiceUrl, auth: false } as const;

let metaCache: Promise<ComplaintMeta> | null = null;
/** The escalation ladder rarely changes: fetch once per app run (retried after a failure). */
function complaintMeta(): Promise<ComplaintMeta> {
  metaCache ??= request<ComplaintMeta>("GET", "/api/meta", flow).catch((e) => {
    metaCache = null;
    throw e;
  });
  return metaCache;
}

export const civicApi = {
  meta: complaintMeta,
  /** Every complaint in the module belongs to its single demo citizen, so "mine" is the whole list. */
  mine: async (): Promise<Complaint[]> => {
    const [list, meta] = await Promise.all([request<FlowComplaint[]>("GET", "/api/complaints", flow), complaintMeta()]);
    return list.map((c) => toComplaint(c, meta.statuses)).sort(newestFirst);
  },
  track: async (trackingId: string): Promise<Complaint> => {
    const [c, meta] = await Promise.all([
      request<FlowComplaint>("GET", `/api/complaints/${encodeURIComponent(trackingId)}`, flow),
      complaintMeta(),
    ]);
    return toComplaint(c, meta.statuses);
  },
  /** Department, category and priority are assigned by the module's intake agent. */
  file: async (body: { title: string; description: string; latitude: number; longitude: number; address?: string; photoUri?: string }) => {
    const form = new FormData();
    form.append("title", body.title);
    form.append("description", body.description);
    form.append("lat", String(body.latitude));
    form.append("lng", String(body.longitude));
    if (body.address) form.append("address", body.address);
    // Evidence photo: the module stores it in Postgres (civic_flow.photos).
    if (body.photoUri) form.append("photo", { uri: body.photoUri, name: "evidence.jpg", type: "image/jpeg" } as unknown as Blob);
    // Intake runs the guardrail + LLM classification before answering.
    const [c, meta] = await Promise.all([
      requestForm<FlowComplaint>("/api/complaints", form, { ...flow, timeoutMs: body.photoUri ? 60000 : 45000 }),
      complaintMeta(),
    ]);
    return toComplaint(c, meta.statuses);
  },
  events: () => request<CityEvent[]>("GET", "/api/city-events"),
};

const time = (iso?: string | null) => {
  const t = iso ? Date.parse(iso) : NaN;
  return Number.isNaN(t) ? 0 : t;
};

/** The portal's JSON is hand-maintained: fill gaps instead of letting one odd record break the feed. */
function toNotice(raw: Partial<Notice>, i: number): Notice | null {
  if (!raw || typeof raw.title !== "string" || !raw.title.trim()) return null;
  return {
    id: String(raw.id ?? raw.referenceNumber ?? `notice-${i}`),
    referenceNumber: raw.referenceNumber ?? "",
    title: raw.title.trim(),
    hindiTitle: raw.hindiTitle,
    department: raw.department ?? "Govt. of Uttarakhand",
    category: raw.category ?? "Notice",
    priority: raw.priority ?? "Standard",
    signatory: raw.signatory ?? "Competent Authority",
    summary: raw.summary ?? "",
    body: raw.body ?? "",
    publishDate: raw.publishDate ?? "",
    expiryDate: raw.expiryDate ?? null,
    isPinned: Boolean(raw.isPinned),
    tags: Array.isArray(raw.tags) ? raw.tags : [],
  };
}

/**
 * Notices published on the state govt portal: the same list its /notices page shows.
 * The feed may be a static JSON file (no server-side limit or filtering), so expiry, order and limit
 * are applied here: active only, pinned first, then newest.
 */
export const noticesApi = {
  latest: async (limit = 20): Promise<Notice[]> => {
    const data = await request<unknown>("GET", "", { baseUrl: noticesUrl, auth: false, query: { limit } });
    // Accept a bare array or a { notices: [...] } envelope (the portal's database.json shape).
    const list = Array.isArray(data) ? data : ((data as { notices?: unknown })?.notices ?? []);
    if (!Array.isArray(list)) return [];
    const now = Date.now();
    return list
      .map((n, i) => toNotice(n as Partial<Notice>, i))
      .filter((n): n is Notice => n !== null && (!n.expiryDate || time(n.expiryDate) === 0 || time(n.expiryDate) > now))
      .sort((a, b) => Number(b.isPinned) - Number(a.isPinned) || time(b.publishDate) - time(a.publishDate))
      .slice(0, limit);
  },
};

export const businessApi = {
  /** Popular businesses, nearest first when a location is given. */
  list: (near?: { lat: number; lng: number }, limit = 20) =>
    request<Business[]>("GET", "/api/businesses", { query: { lat: near?.lat, lng: near?.lng, limit } }),
};

export const incidentApi = {
  list: () => request<Incident[]>("GET", "/api/incidents"),
};

/** Weather: live city conditions from core; forecast and air quality straight from Open-Meteo (no key). */
export const weatherApi = {
  current: (lat?: number, lng?: number) =>
    request<CityWeather>("GET", "/api/weather/current", { query: { city: "Dehradun", latitude: lat, longitude: lng }, auth: false }),
  forecast: (lat: number, lng: number) =>
    request<WeatherForecast>("GET", "/v1/forecast", {
      baseUrl: "https://api.open-meteo.com",
      auth: false,
      query: {
        latitude: lat,
        longitude: lng,
        current: "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        hourly: "temperature_2m,weather_code,precipitation_probability",
        daily: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
        timezone: "Asia/Kolkata",
        forecast_days: 6,
        forecast_hours: 12,
      },
    }),
  air: (lat: number, lng: number) =>
    request<AirQuality>("GET", "/v1/air-quality", {
      baseUrl: "https://air-quality-api.open-meteo.com",
      auth: false,
      query: { latitude: lat, longitude: lng, current: "us_aqi,pm2_5,pm10" },
    }),
};
