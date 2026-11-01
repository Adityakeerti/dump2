import asyncio
import datetime
import os
import shutil
import uuid
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    Complaint,
    ComplaintCreateRequest,
    ComplaintStatus,
    ActorRole,
    TimelineEvent,
    LocationModel,
    ResolveRequest,
    WorkerModel,
)
from pydantic import BaseModel, Field
from .storage import store, UPLOADS_DIR, BASE_DIR
from . import pg_store
from .agents import intake_agent, coordinator_agent
from .llm_service import llm
from .notices import router as notices_router

app = FastAPI(
    title="CitySense Civic Complaint & Escalation Service (Member C)",
    version="1.0.0",
    description="Python civic complaint module with AI agents, multi-tier escalation ladder, and Spring Boot feed API."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Govt-portal notices (read by the citizen app's feed)
app.include_router(notices_router)

# Mount uploads directory
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _sniff_image(data: bytes):
    """(content_type, ext) from magic bytes; the client's filename and type are not trusted."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image/heic", "heic"
    return None


@app.get("/api/photos/{name}")
@app.get("/photos/{name}", include_in_schema=False)
def get_photo(name: str):
    """Complaint evidence stored in Postgres (civic_flow.photos)."""
    from fastapi.responses import Response

    found = pg_store.get_photo(name) if pg_store.enabled() else None
    if not found:
        raise HTTPException(status_code=404, detail="Photo not found")
    data, ctype = found
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "private, max-age=86400"})

# Background auto-tick state
SIMULATION_STATE = {
    "auto_tick_enabled": True,
    "tick_interval_seconds": 5,
    "task": None
}


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@app.on_event("startup")
async def startup_event():
    # Start background auto-escalation worker
    SIMULATION_STATE["task"] = asyncio.create_task(_auto_escalation_worker())


async def _auto_escalation_worker():
    while True:
        try:
            if SIMULATION_STATE["auto_tick_enabled"]:
                authorities = store.load_authorities()
                complaints = store.load_complaints()
                changed = False
                for c in complaints:
                    # Only escalate active unresolved complaints
                    if c.status not in [ComplaintStatus.RESOLVED]:
                        coordinator_agent.tick_escalation(c, authorities)
                        changed = True
                if changed:
                    store.save_complaints(complaints)
        except Exception as e:
            print(f"[Coordinator Auto-Tick Error]: {e}")
        await asyncio.sleep(SIMULATION_STATE["tick_interval_seconds"])


# --- UI Endpoint ---
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    ui_path = os.path.join(BASE_DIR, "static", "UI.html")
    if os.path.exists(ui_path):
        with open(ui_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        "<h2>CitySense Civic Complaint & SLA Escalation Service</h2>"
        "<p>Service is running. API docs: <a href='docs'>/docs</a> · feed: <a href='api/feed'>/api/feed</a></p>"
    )


# --- User & Authorities Profiles Endpoints ---
@app.get("/api/user")
def get_user_profile():
    """Returns the single citizen user account (no hardcoded data except this)."""
    return store.load_user_raw()


@app.get("/api/authorities")
def get_authorities():
    """Returns simulated profiles of higher authorities: Ward Officer, Municipal Commissioner, CM Portal."""
    return [a.model_dump() for a in store.load_authorities()]


@app.get("/api/workers")
def get_workers():
    """Returns simulated municipal field workers."""
    return store.load_workers()


# Human-readable ladder, in escalation order (index == escalation level).
LADDER_LABELS = {
    ComplaintStatus.FILED: "Filed",
    ComplaintStatus.WORKER_ASSIGNED: "Worker assigned",
    ComplaintStatus.WARNING_1: "Warning 1",
    ComplaintStatus.WARNING_2: "Warning 2",
    ComplaintStatus.WARNING_3: "Warning 3",
    ComplaintStatus.WARNING_4: "Warning 4",
    ComplaintStatus.WARNING_5: "Warning 5",
    ComplaintStatus.ESCALATED_WARD_OFFICER: "Ward officer",
    ComplaintStatus.ESCALATED_MUNICIPAL_COMMISSIONER: "Municipal commissioner",
    ComplaintStatus.ESCALATED_CM_PORTAL: "CM portal",
}


@app.get("/api/meta")
def get_meta():
    """Escalation ladder for clients (mobile app, govt portal): statuses[i] is escalation level i.
    RESOLVED is terminal and not a rung; clients keep the level the complaint was resolved at."""
    return {
        "statuses": [s.value for s in LADDER_LABELS],
        "escalationLadder": list(LADDER_LABELS.values()),
    }


# --- Complaints Endpoints ---
@app.get("/api/complaints", response_model=List[Complaint])
def list_complaints():
    """Returns all complaints in the system."""
    return store.load_complaints()


@app.get("/api/complaints/{tracking_id}", response_model=Complaint)
def get_complaint(tracking_id: str):
    c = store.get_complaint(tracking_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return c


@app.post("/api/complaints", response_model=Complaint)
async def create_complaint_form(
    title: str = Form(...),
    description: str = Form(...),
    category: Optional[str] = Form(None),
    address: str = Form("Rajpur Road, Ward 14, Dehradun"),
    lat: float = Form(30.3165),
    lng: float = Form(78.0322),
    photo: Optional[UploadFile] = File(None),
    sample_photo: Optional[str] = Form(None)
):
    """Citizen complaint creation endpoint with photo upload.
    Enforces Municipal Guardrails: Blocks gibberish (e.g. 'Kadu'), spam, or non-civic input."""
    # 1. Municipal Guardrail Validation
    guardrail_res = llm.evaluate_guardrail(title=title, description=description, address=address)
    if not guardrail_res.get("allowed", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "CIVIC_GUARDRAIL_BLOCKED",
                "message": guardrail_res.get("reason", "Submission rejected by Municipal Guardrail: Invalid civic issue."),
                "flag": guardrail_res.get("flag", "NON_CIVIC_OR_GIBBERISH"),
                "llm_powered": guardrail_res.get("llm_powered", False)
            }
        )

    photo_filename = ""
    if photo and photo.filename:
        data = await photo.read()
        kind = _sniff_image(data)
        if not data or len(data) > MAX_PHOTO_BYTES or not kind:
            raise HTTPException(status_code=415, detail="Photo must be a JPEG, PNG, WebP or HEIC image up to 10 MB")
        ctype, ext = kind
        unique_name = f"photo_{uuid.uuid4().hex[:10]}.{ext}"
        if pg_store.enabled():
            # Shared database: the photo survives container rebuilds and is served by /api/photos/{name}.
            pg_store.save_photo(unique_name, ctype, data)
            photo_filename = f"/api/photos/{unique_name}"
        else:
            with open(os.path.join(UPLOADS_DIR, unique_name), "wb") as buffer:
                buffer.write(data)
            photo_filename = f"/uploads/{unique_name}"
    elif sample_photo:
        photo_filename = sample_photo
    else:
        # Fallback to default photo placeholder
        photo_filename = "/uploads/sample_pothole.svg"

    tracking_id = f"CMP-2026-{uuid.uuid4().hex[:6].upper()}"
    citizen = store.load_user()
    now_str = _iso_now()

    clean_category = category.strip() if category and category.strip() else "Auto-Detecting..."

    # Initial Complaint entity
    complaint = Complaint(
        tracking_id=tracking_id,
        title=title,
        category=clean_category,
        description=description,
        photo_url=photo_filename,
        location=LocationModel(
            lat=lat,
            lng=lng,
            address=address,
            ward=citizen.ward
        ),
        citizen=citizen,
        status=ComplaintStatus.FILED,
        priority="MEDIUM",
        created_at=now_str,
        updated_at=now_str,
        sla_seconds=30,
        sla_remaining_seconds=30,
        timeline=[
            TimelineEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                timestamp=now_str,
                actor=ActorRole.CITIZEN,
                actor_name=citizen.name,
                action="COMPLAINT_FILED",
                message=f"Citizen uploaded photo evidence and registered civic grievance at {address}.",
                badge_type="info"
            )
        ]
    )

    # Step 2: Municipal Agent gets it and assigns a worker
    workers = store.load_workers()
    complaint = intake_agent.process_and_assign(complaint, workers)

    # Save to storage
    store.upsert_complaint(complaint)
    return complaint


@app.post("/api/complaints/{tracking_id}/escalate-tick", response_model=Complaint)
def manual_escalation_tick(tracking_id: str):
    """Force an escalation tick for a single complaint by the Municipal Coordinator Agent."""
    c = store.get_complaint(tracking_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if c.status == ComplaintStatus.RESOLVED:
        return c

    authorities = store.load_authorities()
    c = coordinator_agent.tick_escalation(c, authorities)
    store.upsert_complaint(c)
    return c


@app.post("/api/complaints/{tracking_id}/resolve", response_model=Complaint)
def resolve_complaint(tracking_id: str, req: ResolveRequest):
    """Worker resolves the task with notes and on-site evidence."""
    c = store.get_complaint(tracking_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")

    c = coordinator_agent.resolve(
        c,
        note=req.resolution_note,
        proof_photo_url=req.proof_photo_url,
        resolved_by=c.assigned_worker.name if c.assigned_worker else "Municipal Field Worker"
    )
    store.upsert_complaint(c)
    return c


class ReassignRequest(BaseModel):
    reason: str = Field(default="SLA stalled; reassigned to rapid action squad.", max_length=500)


@app.post("/api/complaints/{tracking_id}/reassign", response_model=Complaint)
def reassign_worker(tracking_id: str, req: Optional[ReassignRequest] = None):
    """Reallocate a stalled complaint to the department's rapid action squad (used by the citizen agent)."""
    req = req or ReassignRequest()
    c = store.get_complaint(tracking_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if c.status == ComplaintStatus.RESOLVED:
        raise HTTPException(status_code=409, detail="Complaint is already resolved")
    previous = c.assigned_worker
    department = previous.department if previous else "Municipal Operations"
    workers = [w for w in store.load_workers() if w.get("department") == department]
    alternative = next((w for w in workers if not previous or w["id"] != previous.id), None)
    if alternative:
        new_worker = WorkerModel(**{k: alternative[k] for k in ("id", "name", "team", "department", "phone")},
                                 rating=alternative.get("rating", 4.8))
    else:
        new_worker = WorkerModel(
            id=f"RAS-{uuid.uuid4().hex[:4].upper()}",
            name="Rapid Action Squad",
            team=f"{department} — Rapid Action Squad",
            department=department,
            phone="1800-180-4107",
        )
    now = _iso_now()
    c.assigned_worker = new_worker
    c.updated_at = now
    c.sla_remaining_seconds = c.sla_seconds
    c.timeline.append(TimelineEvent(
        id=f"evt-{uuid.uuid4().hex[:8]}",
        timestamp=now,
        actor=ActorRole.MUNICIPAL_COORDINATOR_AGENT,
        actor_name=c.coordinator_agent,
        action="WORKER_REASSIGNED",
        message=f"Reassigned from {previous.name if previous else 'unassigned'} to {new_worker.team}. Reason: {req.reason}",
        badge_type="warning",
    ))
    store.upsert_complaint(c)
    return c


# --- Feed API for Future Spring Boot Integration ---
@app.get("/api/feed")
def get_complaints_feed():
    """Feed API that serves all complaints formatted for future Spring Boot ingestion

    (com.citysense.civic module)."""
    complaints = store.load_complaints()
    authorities = store.load_authorities()

    total = len(complaints)
    active = sum(1 for c in complaints if c.status != ComplaintStatus.RESOLVED)
    resolved = sum(1 for c in complaints if c.status == ComplaintStatus.RESOLVED)

    feed_events = []
    for c in complaints:
        feed_events.append({
            "trackingId": c.tracking_id,
            "title": c.title,
            "category": c.category,
            "description": c.description,
            "photoUrl": c.photo_url,
            "status": c.status.value,
            "priority": c.priority,
            "escalationLadderStep": c.status.value,
            "warningsCount": c.warnings_count,
            "slaSeconds": c.sla_seconds,
            "slaRemainingSeconds": c.sla_remaining_seconds,
            "assignedWorker": c.assigned_worker.model_dump() if c.assigned_worker else None,
            "coordinatorAgent": c.coordinator_agent,
            "currentAuthority": c.current_authority.model_dump() if c.current_authority else None,
            "citizen": c.citizen.model_dump(),
            "location": c.location.model_dump(),
            "resolvedAtStage": c.resolved_at_stage,
            "timelineEventsCount": len(c.timeline),
            "timeline": [t.model_dump() for t in c.timeline],
            "resolutionNote": c.resolution_note,
            "citizenNotification": c.citizen_notification.model_dump() if c.citizen_notification else None,
            "llmReasoning": c.llm_reasoning,
            "escalationMemo": c.escalation_memo,
            "createdAt": c.created_at,
            "updatedAt": c.updated_at
        })

    return {
        "service": "CitySense Civic Complaint Subsystem (Member C)",
        "feed_timestamp": _iso_now(),
        "target_springboot_module": "com.citysense.civic",
        "target_entity": "com.citysense.civic.entity.Complaint",
        "spring_sync_ready": True,
        "summary": {
            "total_complaints": total,
            "active_unresolved": active,
            "resolved": resolved
        },
        "complaints": feed_events
    }


# --- Simulation Controls ---
@app.post("/api/simulation/toggle")
def toggle_auto_tick(enabled: Optional[bool] = None, interval: Optional[int] = None):
    """Toggle automated background escalation ticking and speed."""
    if enabled is not None:
        SIMULATION_STATE["auto_tick_enabled"] = enabled
    if interval is not None and interval >= 1:
        SIMULATION_STATE["tick_interval_seconds"] = interval
    return {
        "auto_tick_enabled": SIMULATION_STATE["auto_tick_enabled"],
        "tick_interval_seconds": SIMULATION_STATE["tick_interval_seconds"]
    }


@app.get("/api/simulation/status")
def get_simulation_status():
    return {
        "auto_tick_enabled": SIMULATION_STATE["auto_tick_enabled"],
        "tick_interval_seconds": SIMULATION_STATE["tick_interval_seconds"]
    }


@app.post("/api/simulation/reset")
def reset_simulation():
    """Clear all complaints to test fresh flows."""
    store.reset_complaints()
    return {"status": "success", "message": "All complaints cleared."}
