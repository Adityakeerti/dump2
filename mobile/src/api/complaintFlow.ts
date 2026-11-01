import type { Complaint } from "./types";

/** Complaint as stored by the complaint module (snake_case, see complaint_module/app/models.py). */
export interface FlowComplaint {
  tracking_id: string;
  title: string;
  category: string;
  description: string;
  photo_url: string;
  location: { lat: number; lng: number; address: string; ward: string };
  citizen: { user_id: string; name: string };
  status: string;
  priority: string;
  assigned_worker?: { name: string; team: string; department: string } | null;
  resolution_note?: string | null;
  resolution_time?: string | null;
  resolved_at_stage?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Maps a complaint-module record to the app's Complaint. `statuses` is the ladder from /api/meta;
 * a resolved complaint keeps the rung it was resolved at.
 */
export function toComplaint(c: FlowComplaint, statuses: string[]): Complaint {
  const rung = c.status === "RESOLVED" ? (c.resolved_at_stage ?? "") : c.status;
  return {
    id: c.tracking_id,
    trackingId: c.tracking_id,
    citizenName: c.citizen?.name,
    title: c.title,
    description: c.description,
    category: c.category,
    department: c.assigned_worker?.department ?? "Municipal intake",
    priority: c.priority,
    status: c.status,
    latitude: c.location?.lat,
    longitude: c.location?.lng,
    escalationLevel: Math.max(0, statuses.indexOf(rung)),
    assignedWorker: c.assigned_worker ? `${c.assigned_worker.name} (${c.assigned_worker.team})` : undefined,
    resolutionNotes: c.resolution_note ?? undefined,
    resolvedAt: c.resolution_time ?? undefined,
    createdAt: c.created_at,
    updatedAt: c.updated_at,
    // Placeholder art (sample_*.svg) is not the citizen's evidence.
    photoUrl: c.photo_url && !/sample_/.test(c.photo_url) ? c.photo_url : undefined,
  };
}

export const newestFirst = (a: Complaint, b: Complaint) => Date.parse(b.createdAt) - Date.parse(a.createdAt);
