export type Role = "CITIZEN" | "ADMIN" | "CREW";

export interface User {
  id: string;
  email: string;
  fullName: string;
  role: Role;
  language: string;
  emailVerified: boolean;
}

export interface TokenResponse {
  accessToken: string;
  tokenType: string;
  expiresIn: number;
  user: User;
}

export interface OtpSentResponse {
  email: string;
  codeLength: number;
  expiresInSeconds: number;
  resendAfterSeconds: number;
}

export interface MapConfig {
  styleUrl: string;
  defaultLatitude: number;
  defaultLongitude: number;
  defaultZoom: number;
  minZoom: number;
  maxZoom: number;
  geofenceRadiusMeters: number;
  attribution: string;
}

export interface Place {
  name: string;
  displayName: string;
  latitude: number;
  longitude: number;
  type?: string;
}

export interface Avatar {
  id: string;
  handle: string;
  name: string;
  title: string;
  category: string;
  persona: string;
  intro: string;
  pricing?: string;
  websiteUrl?: string;
  socials: { instagram?: string; threads?: string; x?: string };
  pinImageUrl: string;
  heroImageUrl: string;
  rating: number;
  reviewCount: number;
  likeCount: number;
  latitude: number;
  longitude: number;
  distanceMeters?: number;
  saved: boolean;
  liked: boolean;
}

export type ChatIntent = "INTRO" | "PRICING" | "WEBSITE";

/** One step of the main voice agent's execution plan (who ran what). */
export interface PlanStep {
  id: number;
  executor: string;
  action: string;
  tools: string[];
  status: "planned" | "running" | "completed" | "failed" | "skipped";
  detail?: string | null;
}

/** An action the agent proposed that the citizen must confirm (e.g. a drafted complaint). */
export interface PendingAgentAction {
  token: string;
  summary: string;
  expiresAt: string;
  action_type?: string;
  /** A photo would help the field crew (sewage, garbage, potholes…). */
  photoSuggested?: boolean;
}

export interface AvatarChatResponse {
  sessionId: string;
  reply: string;
  intent?: ChatIntent;
  link?: string;
  sources?: string[];
  timestamp: string;
  status?: string;
  plan?: PlanStep[] | null;
  pendingAction?: PendingAgentAction | null;
  actionData?: Record<string, any> | null;
}

/** A main-agent reply (map-tap briefing or follow-up), straight from agent_service. */
export interface AgentReply {
  sessionId: string;
  status: string;
  answer: string;
  plan?: PlanStep[] | null;
  sources?: { title: string; url?: string | null }[];
  actionData?: Record<string, any> | null;
  pendingAction?: PendingAgentAction | null;
  /** Instructions from the main agent for the app: navigate, focus_map, set_preference. */
  clientActions?: ClientAction[] | null;
  toolCalls?: { tool: string; caller: string; served: string }[] | null;
}

export type ClientAction =
  | { type: "navigate"; screen: string; id?: string }
  | { type: "focus_map"; latitude: number; longitude: number; label?: string }
  | { type: "set_preference"; language?: "hi" | "en"; voiceAutoPlay?: boolean };

export interface ConfirmResult {
  status: "executed" | "failed" | "rejected" | "cancelled";
  result?: { trackingId?: string; assignedWorker?: string; [k: string]: unknown } | null;
  detail?: string | null;
}

export interface AudioPreference {
  auto_play: boolean;
  preferred_speaker: string;
}

export interface ToggleResponse {
  avatarId: string;
  active: boolean;
  count: number;
}

export interface Complaint {
  id: string;
  trackingId: string;
  citizenName?: string;
  title: string;
  description: string;
  category: string;
  department: string;
  priority: string;
  status: string;
  latitude: number;
  longitude: number;
  escalationLevel: number;
  assignedWorker?: string;
  resolutionNotes?: string;
  resolvedAt?: string;
  createdAt: string;
  updatedAt: string;
  /** Evidence photo path on the complaint module (e.g. /photos/photo_ab12.jpg). */
  photoUrl?: string;
}

export interface CityEvent {
  id: string;
  title: string;
  description?: string;
  category: string;
  severity: string;
  latitude: number;
  longitude: number;
  startsAt: string;
  endsAt?: string;
  createdAt: string;
  venue?: string | null;
  organizer?: string | null;
  /** Where the listing came from (organiser page, ticketing site, holiday list). */
  sourceUrl?: string | null;
}

/** A popular local business (curated directory in core; agents recommend from the same list). */
export interface Business {
  id: string;
  name: string;
  category: string;
  locality: string;
  description: string;
  latitude: number;
  longitude: number;
  /** "approximate" = locality/junction centre, not the shop door. */
  coordsPrecision: "exact" | "approximate";
  sourceUrl?: string | null;
  distanceMeters?: number | null;
}

export interface Incident {
  id: string;
  type: string;
  title: string;
  summary?: string;
  severity: number;
  urgencyScore: number;
  latitude: number;
  longitude: number;
  status: string;
  observationCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface LiveMessage {
  type: string;
  entityId: string;
  data: unknown;
  timestamp: string;
}

/** A notice published from the state govt portal (served by the complaint module). */
export interface Notice {
  id: string;
  referenceNumber: string;
  title: string;
  hindiTitle?: string;
  department: string;
  category: string;
  priority: string;
  signatory: string;
  summary: string;
  body: string;
  publishDate: string;
  expiryDate?: string | null;
  isPinned: boolean;
  tags: string[];
}

/** Escalation ladder from the complaint module: statuses[i] is escalation level i. */
export interface ComplaintMeta {
  statuses: string[];
  escalationLadder: string[];
}

/** Live city weather from core (Open-Meteo + flood-depth estimate). */
export interface CityWeather {
  city: string;
  latitude: number;
  longitude: number;
  temperatureC: number;
  relativeHumidity: number;
  precipitationMm: number;
  rainMm: number;
  floodDepthCm: number;
  riskLevel: string;
  conditionText: string;
  source: string;
  observedAt: string;
}

/** Open-Meteo forecast (public, keyless), Asia/Kolkata times. */
export interface WeatherForecast {
  current: { temperature_2m: number; apparent_temperature: number; weather_code: number; wind_speed_10m: number; relative_humidity_2m: number };
  hourly: { time: string[]; temperature_2m: number[]; weather_code: number[]; precipitation_probability: number[] };
  daily: {
    time: string[];
    weather_code: number[];
    temperature_2m_max: number[];
    temperature_2m_min: number[];
    precipitation_probability_max: number[];
    sunrise: string[];
    sunset: string[];
  };
}

export interface AirQuality {
  current: { us_aqi: number; pm2_5: number; pm10: number };
}
