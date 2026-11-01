"""FastAPI Backend Server bridging UI Dashboard to LangGraph Emergency Agent."""

import os
import math
import base64
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
from services.hospital_service import HospitalService
from services.weather_service import WeatherService, WeatherCondition
from routing.predictive_router import PredictiveRouter
from agents.ambulance_agent import AmbulanceAgent
from agents.feud_tracker import FeudTracker
from agents.police_interface import MockPoliceAgent
from agents.emergency_agent import EmergencyAgent
from models.llm_classifier import LLMClassifier
from models.vision_llm import VisionLLM
from models.vision_pipeline import VisionPipeline, CameraMetadata
from simulation.synthetic_scenarios import (
    build_demo_city_network,
    get_scenario_accident_clearing_jam,
    get_scenario_accident_persistent_jam,
    get_scenario_feud_timeline,
)

app = FastAPI(title="Emergency Agent OS Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core Component Initialization ─────────────────────────────────────────────
graph, history = build_demo_city_network()
hospital_service = HospitalService()
router = PredictiveRouter(graph=graph, history_db=history)
ambulance_agent = AmbulanceAgent(hospital_service=hospital_service, predictive_router=router)
police_agent = MockPoliceAgent()
feud_tracker = FeudTracker(min_duration_sec=settings.FEUD_MIN_DURATION_SECONDS)
llm_classifier = LLMClassifier()
vision_llm = VisionLLM()
vision_pipeline = VisionPipeline()

emergency_agent = EmergencyAgent(
    ambulance_agent=ambulance_agent,
    police_agent=police_agent,
    feud_tracker=feud_tracker,
    llm_classifier=llm_classifier,
    vision_llm=vision_llm,
)

BASE_DIR = Path(__file__).parent.resolve()
SAMPLE_VIDEOS_DIR = BASE_DIR / "data" / "sample_videos"
SAMPLE_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/videos", StaticFiles(directory=str(SAMPLE_VIDEOS_DIR)), name="videos")

# Agent-facing dispatch / corridor / incident-feed API (see dispatch_api.py)
from dispatch_api import build_dispatch_router, IncidentRecord  # noqa: E402

dispatch_router = build_dispatch_router(hospital_service, router, graph)
app.include_router(dispatch_router)
_record_incident = dispatch_router.record_incident


# ── UI ─────────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    ui_path = BASE_DIR / "ui.html"
    if ui_path.exists():
        return ui_path.read_text(encoding="utf-8")
    return (
        "<h1>CitySense Emergency Routing</h1><p>Service is running. API docs: "
        "<a href='docs'>/docs</a> · health: <a href='api/health'>/api/health</a></p>"
    )


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health_check():
    return {
        "status": "ONLINE",
        "version": "2.0.0",
        "orchestrator": "LangGraph StateGraph",
        "active_hospitals": len(hospital_service.hospitals),
        "tracked_cameras": len(feud_tracker.tracked_cameras),
        "llm_enabled": True,
        "vision_enabled": True,
        "llm_primary_model": settings.LLM_CLASSIFIER_PRIMARY,
        "vision_primary_model": settings.VISION_PRIMARY_MODEL,
        "vision_primary_provider": settings.VISION_PRIMARY_PROVIDER,
    }


# ── Model Status ───────────────────────────────────────────────────────────────
@app.get("/api/model-status")
def model_status():
    """Returns the confirmed-working free model lineup from live checks."""
    return {
        "vision_models": [
            {
                "model": "gemma4:31b",
                "provider": "Ollama Cloud",
                "status": "FREE + VISION",
                "priority": 1,
                "confirmed": True,
            },
            {
                "model": "gemma4:31b-cloud",
                "provider": "Ollama Cloud",
                "status": "FREE + VISION",
                "priority": 2,
                "confirmed": True,
            },
            {
                "model": "qwen/qwen3.8-27b",
                "provider": "Groq",
                "status": "FREE + VISION",
                "priority": 3,
                "confirmed": True,
            },
        ],
        "text_models": [
            {"model": "openai/gpt-oss-120b", "provider": "Groq", "status": "FREE", "priority": 1},
            {"model": "openai/gpt-oss-20b", "provider": "Groq", "status": "FREE", "priority": 2},
            {"model": "nemotron-3-ultra", "provider": "Ollama Cloud", "status": "FREE", "priority": 3},
            {"model": "nemotron-3-super", "provider": "Ollama Cloud", "status": "FREE", "priority": 4},
            {"model": "gpt-oss:120b", "provider": "Ollama Cloud", "status": "FREE", "priority": 5},
        ],
        "last_checked": "2026-10-30T21:34:00+05:30",
    }


# ── Scenario Runner ────────────────────────────────────────────────────────────
@app.get("/api/run-scenario/{scenario_name}")
def run_scenario(scenario_name: str):
    """Triggers full LangGraph + LLM orchestration on selected scenario."""
    if scenario_name == "accident-clearing-jam":
        incident, g, h = get_scenario_accident_clearing_jam()
        temp_router = PredictiveRouter(graph=g, history_db=h)
        temp_amb = AmbulanceAgent(hospital_service=hospital_service, predictive_router=temp_router)
        agent = EmergencyAgent(
            ambulance_agent=temp_amb, police_agent=police_agent,
            llm_classifier=llm_classifier, vision_llm=vision_llm,
        )
        state = agent.process_incident(incident)
        return state.model_dump()

    elif scenario_name == "accident-persistent-jam":
        incident, g, h = get_scenario_accident_persistent_jam()
        temp_router = PredictiveRouter(graph=g, history_db=h)
        temp_amb = AmbulanceAgent(hospital_service=hospital_service, predictive_router=temp_router)
        agent = EmergencyAgent(
            ambulance_agent=temp_amb, police_agent=police_agent,
            llm_classifier=llm_classifier, vision_llm=vision_llm,
        )
        state = agent.process_incident(incident)
        return state.model_dump()

    elif scenario_name == "feud":
        events = get_scenario_feud_timeline()
        results = []
        tracker = FeudTracker(min_duration_sec=settings.FEUD_MIN_DURATION_SECONDS)
        agent = EmergencyAgent(
            ambulance_agent=ambulance_agent,
            police_agent=police_agent,
            feud_tracker=tracker,
            llm_classifier=llm_classifier,
            vision_llm=vision_llm,
        )
        for ev in events:
            st = agent.process_incident(ev)
            results.append(st.model_dump())
        return {"timeline_results": results}

    raise HTTPException(status_code=404, detail="Scenario not found. Valid: accident-clearing-jam, accident-persistent-jam, feud")


# ── Video Stream Ingestion & Processing ────────────────────────────────────────
@app.get("/api/process-video/{video_name}")
@app.post("/api/process-video/{video_name}")
def process_video_feed(video_name: str):
    """Processes a CCTV sample video from data/sample_videos.
    Extracts frames via OpenCV, passes key frame to Vision LLM (Ollama Gemma / Groq Qwen),
    and executes the full LangGraph Emergency Agent pipeline.
    """
    video_path = SAMPLE_VIDEOS_DIR / video_name
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Sample video '{video_name}' not found in {SAMPLE_VIDEOS_DIR}")

    incident, frame_b64, video_meta = vision_pipeline.process_video_file(str(video_path))
    state = emergency_agent.process_incident(incident)
    if incident.incident_type != "NONE":
        # Surface detections to the citizen agent's get_cctv_incident_feed tool.
        _record_incident(IncidentRecord(
            camera_id=incident.camera_id,
            incident_type=incident.incident_type.lower(),
            confidence=max(0.0, min(1.0, incident.confidence)),
            location_label=incident.address,
            latitude=incident.latitude,
            longitude=incident.longitude,
            summary=f"Detected in {video_name}",
        ))

    return {
        "video_name": video_name,
        "video_url": f"/videos/{video_name}",
        "video_meta": video_meta,
        "frame_b64": frame_b64,
        "state": state.model_dump(),
    }


# ── Image Analysis Endpoint ────────────────────────────────────────────────────
class ImageAnalysisRequest(BaseModel):
    image_b64: Optional[str] = None
    cv_context: Optional[str] = None   # For text-only mode
    incident_type: str = "UNKNOWN"
    confidence: float = 0.5
    severity: float = 0.5
    address: str = "Unknown Location"
    camera_id: str = "CAM-UPLOAD"


@app.post("/api/analyze-image")
async def analyze_image(request: ImageAnalysisRequest):
    """Runs vision LLM analysis on an uploaded base64 image or CV context string."""
    vision_result = None

    if request.image_b64:
        vision_result = vision_llm.analyze_image(
            request.image_b64,
            cv_context=f"Type={request.incident_type}, Conf={request.confidence}, Sev={request.severity}",
        )
    elif request.cv_context:
        vision_result = vision_llm.analyze_cv_outputs(request.cv_context)
    else:
        raise HTTPException(status_code=400, detail="Provide either image_b64 or cv_context")

    # Also run LLM classifier
    llm_result = llm_classifier.classify_incident(
        incident_type=request.incident_type or (vision_result.detected_type if vision_result else "UNKNOWN"),
        confidence=request.confidence,
        severity=request.severity,
        address=request.address,
        camera_id=request.camera_id,
        image_description=vision_result.description if vision_result else None,
    )

    return {
        "vision_analysis": vision_result.model_dump() if vision_result else None,
        "llm_classification": llm_result.model_dump(),
    }


@app.post("/api/upload-image-analyze")
async def upload_image_analyze(
    file: UploadFile = File(...),
    incident_type: str = Form("UNKNOWN"),
    confidence: float = Form(0.5),
    severity: float = Form(0.5),
    address: str = Form("Unknown Location"),
    camera_id: str = Form("CAM-UPLOAD"),
):
    """Accepts a multipart file upload, runs vision + LLM analysis."""
    contents = await file.read()
    image_b64 = base64.b64encode(contents).decode("utf-8")

    vision_result = vision_llm.analyze_image(
        image_b64,
        cv_context=f"Type={incident_type}, Conf={confidence}, Sev={severity}",
    )
    llm_result = llm_classifier.classify_incident(
        incident_type=incident_type or vision_result.detected_type,
        confidence=confidence,
        severity=severity,
        address=address,
        camera_id=camera_id,
        image_description=vision_result.description,
    )

    return {
        "filename": file.filename,
        "vision_analysis": vision_result.model_dump(),
        "llm_classification": llm_result.model_dump(),
    }


# ── Videos List ───────────────────────────────────────────────────────────────
@app.get("/api/videos-list")
def list_sample_videos():
    videos = []
    if SAMPLE_VIDEOS_DIR.exists():
        for f in SAMPLE_VIDEOS_DIR.glob("*.mp4"):
            videos.append({
                "name": f.name,
                "url": f"/videos/{f.name}",
                "size_mb": round(f.stat().st_size / 1024 / 1024, 2),
            })
    return {"videos": videos}


# ── Hospitals ─────────────────────────────────────────────────────────────────
@app.get("/api/hospitals")
def get_hospitals():
    return {
        "hospitals": [
            {
                "id": h.id,
                "name": h.name,
                "road_node_id": h.road_node_id,
                "latitude": h.latitude,
                "longitude": h.longitude,
                "er_beds_available": h.er_beds_available,
                "trauma_level": h.trauma_level,
                "ambulances": [
                    {"id": a.id, "status": a.status} for a in h.ambulances
                ],
            }
            for h in hospital_service.hospitals.values()
        ]
    }


# ── Weather & Inundation Routing Endpoints ────────────────────────────────────
class WeatherConditionUpdate(BaseModel):
    segment_id: str
    rainfall_mm: float = 0.0
    flood_depth_cm: float = 0.0
    is_blocked: bool = False
    block_reason: Optional[str] = None


class RouteSyncRequest(BaseModel):
    origin_node: str
    destination_node: str
    city: str = "Dehradun"
    apply_live_weather: bool = True
    simulated_flood_edge: Optional[str] = None
    simulated_flood_depth_cm: Optional[float] = None


@app.get("/api/weather/current")
def get_current_weather(
    city: str = "Dehradun",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
):
    """Fetches real-time weather & flood depth analytics via Open-Meteo free API."""
    if lat is not None and lon is not None:
        weather = WeatherService.get_weather_for_location(lat, lon, city_label=city)
    else:
        weather = WeatherService.get_city_weather(city)
    return weather.model_dump()


@app.post("/api/weather/apply-conditions")
def apply_weather_condition(update: WeatherConditionUpdate):
    """Sets weather or flood water depth on a specific road segment."""
    edge = graph.edges_by_id.get(update.segment_id)
    if not edge:
        raise HTTPException(status_code=404, detail=f"Edge '{update.segment_id}' not found in road network")

    graph.set_weather_condition(
        edge_id=update.segment_id,
        rainfall_mm=update.rainfall_mm,
        flood_depth_cm=update.flood_depth_cm,
        is_blocked=update.is_blocked,
        block_reason=update.block_reason,
    )
    eff_time = edge.effective_travel_time_minutes
    return {
        "status": "UPDATED",
        "segment_id": update.segment_id,
        "rainfall_mm": update.rainfall_mm,
        "flood_depth_cm": update.flood_depth_cm,
        "effective_travel_time_minutes": round(eff_time, 2) if not math.isinf(eff_time) else None,
        "is_blocked": edge.is_blocked,
    }


@app.post("/api/weather/sync-route")
def sync_weather_and_route(request: RouteSyncRequest):
    """Combines live Open-Meteo weather with road network flood conditions,
    computes predictive emergency route, and generates citizen notifications.
    """
    # 1. Fetch live weather
    weather = WeatherService.get_city_weather(request.city)

    # 2. Optionally inject simulated waterlogging on an underpass / road
    if request.simulated_flood_edge and request.simulated_flood_depth_cm is not None:
        graph.set_weather_condition(
            request.simulated_flood_edge,
            rainfall_mm=weather.rain_mm or 25.0,
            flood_depth_cm=request.simulated_flood_depth_cm,
            is_blocked=request.simulated_flood_depth_cm >= 25.0,
            block_reason=f"Waterlogged underpass ({request.simulated_flood_depth_cm}cm)",
        )

    # 3. Plan predictive route
    decision = router.plan_emergency_route(request.origin_node, request.destination_node)
    if not decision:
        raise HTTPException(
            status_code=400,
            detail=f"No route found between {request.origin_node} and {request.destination_node}",
        )

    # 4. Generate citizen proximity notifications
    citizen_notifications = []
    if decision.weather_rerouted:
        blocked_nodes = [w.segment_id for w in decision.weather_evaluations if w.is_impassable]
        citizen_notifications.append({
            "target_area": f"{request.city} - {', '.join(blocked_nodes) if blocked_nodes else 'Low-lying sectors'}",
            "severity": "CRITICAL",
            "title": "Severe Waterlogging Road Closure",
            "message": (
                f"⚠️ ADVISORY: Flash inundation observed ({decision.weather_evaluations[0].flood_depth_cm if decision.weather_evaluations else '25+'}cm). "
                f"Emergency bypass activated. Citizens are advised to avoid {blocked_nodes}."
            ),
            "suggested_bypass": decision.selected_path.edges,
            "timestamp": weather.observed_at,
        })
    elif weather.water_depth_cm_estimate > 5.0 or weather.precipitation_mm > 10.0:
        citizen_notifications.append({
            "target_area": f"{request.city} Urban Corridors",
            "severity": "WARNING",
            "title": "Wet Weather Driving Advisory",
            "message": f"Rainfall: {weather.precipitation_mm}mm. Minor surface pooling. Drive with caution.",
            "suggested_bypass": [],
            "timestamp": weather.observed_at,
        })

    return {
        "weather": weather.model_dump(),
        "route_decision": decision.model_dump(),
        "citizen_notifications": citizen_notifications,
    }


@app.get("/api/network/graph")
def get_network_graph():
    """Returns road network nodes, edges, flood status, and speed limits."""
    nodes = [{"id": n.id, "name": n.name, "latitude": n.latitude, "longitude": n.longitude} for n in graph.nodes.values()]
    edges = [
        {
            "id": e.id,
            "start_node": e.start_node,
            "end_node": e.end_node,
            "distance_km": e.distance_km,
            "speed_limit_kmh": e.speed_limit_kmh,
            "nominal_travel_time_minutes": round(e.nominal_travel_time_minutes, 2),
            "effective_travel_time_minutes": round(e.effective_travel_time_minutes, 2) if not math.isinf(e.effective_travel_time_minutes) else 999.0,
            "flood_depth_cm": e.flood_depth_cm,
            "rainfall_intensity_mm": e.rainfall_intensity_mm,
            "is_blocked": e.is_blocked,
            "block_reason": e.block_reason,
            "has_jam": e.active_jam is not None,
        }
        for e in graph.edges_by_id.values()
    ]
    return {"nodes": nodes, "edges": edges}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8002")))
