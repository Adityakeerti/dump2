from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.agent.subagents.base import SubAgentResult
from src.agent.subagents.city_pulse_agent import CityPulseSpecialist
from src.agent.subagents.complaint_agent import CivicComplaintSpecialist
from src.agent.subagents.emergency_agent import EmergencySpecialist
from src.agent.subagents.knowledge_agent import KnowledgeSpecialist
from src.agent.tools import (
    CorridorArgs,
    DensityArgs,
    TOOL_MODELS,
    UserArgs,
    execute_complaint,
    read_tool,
    tool_schemas,
)
from src.auth.schemas import Principal
from src.knowledge.retrieval import RetrievalHit


@pytest.fixture
def principal():
    return Principal(user_id="test-citizen-001", role="citizen")


# ============================================================================
# CivicComplaintSpecialist Tests
# ============================================================================

async def test_complaint_specialist_clarification_on_missing_location(principal):
    agent = CivicComplaintSpecialist()
    # Message provides category and description, but completely misses location
    result = await agent.execute(
        session=None,
        principal=principal,
        message="There is a broken pothole damaging car tires",
        language="en",
    )
    assert isinstance(result, SubAgentResult)
    assert result.status == "CLARIFICATION_REQUIRED"
    assert result.execution_steps == ["parse_and_validate", "clarify_missing_fields"]
    assert result.cta == "provide_details"
    assert "location" in result.metadata["missing_fields"]
    assert "location" in result.response_text.lower() or "landmark" in result.response_text.lower()


async def test_complaint_specialist_clarification_on_missing_category_and_location(principal):
    agent = CivicComplaintSpecialist()
    result = await agent.execute(
        session=None,
        principal=principal,
        message="Help me",
        language="en",
    )
    assert result.status == "CLARIFICATION_REQUIRED"
    assert result.execution_steps == ["parse_and_validate", "clarify_missing_fields"]
    assert "description" in result.metadata["missing_fields"]


async def test_complaint_specialist_complete_proposal(principal):
    agent = CivicComplaintSpecialist()
    message = "There is a massive pothole on Rajpur Road near Clock Tower causing severe traffic bottlenecks and damage."
    result = await agent.execute(
        session=None,
        principal=principal,
        message=message,
        language="en",
    )
    assert result.status == "ACTION_PENDING"
    assert result.execution_steps == ["parse_and_validate", "deduplication_check", "propose_action"]
    assert result.cta == "confirm_complaint"
    assert result.action is not None
    assert result.action["action_type"] == "create_complaint"
    assert result.action["tool"] == "create_complaint"
    assert result.action["args"]["category"] == "Potholes and Road Damage"
    assert "Clock Tower" in result.action["args"]["location"] or "Rajpur Road" in result.action["args"]["location"]
    assert result.action["token"]
    assert "confirm" in result.response_text.lower()


async def test_complaint_specialist_deduplication(principal):
    agent = CivicComplaintSpecialist()
    # Subhash Road near Clock Tower has an existing mock complaint NND-2026-0841
    message = "Deep pothole crater on Subhash Road near Clock Tower causing road accidents."
    result = await agent.execute(
        session=None,
        principal=principal,
        message=message,
        language="en",
    )
    assert result.status == "ACTION_PENDING"
    assert result.execution_steps == ["parse_and_validate", "deduplication_check", "propose_action"]
    assert result.metadata["duplicate_found"] is True
    assert result.metadata["duplicate_tracking_id"] == "NND-2026-0841"
    assert "NND-2026-0841" in result.response_text


async def test_complaint_specialist_hindi(principal):
    agent = CivicComplaintSpecialist()
    message = "पलटन बाजार में कचरा और कूड़ेदान का ढेर लगा हुआ है, सफाई करवाएं।"
    result = await agent.execute(
        session=None,
        principal=principal,
        message=message,
        language="hi",
    )
    assert result.status == "ACTION_PENDING"
    assert result.execution_steps == ["parse_and_validate", "deduplication_check", "propose_action"]
    assert result.action is not None
    assert "देहरादून नगर निगम" in result.response_text


# ============================================================================
# EmergencySpecialist Tests
# ============================================================================

async def test_emergency_specialist_critical_ambulance(principal):
    agent = EmergencySpecialist()
    message = "Emergency! Major accident on Rajpur Road near Jakhan, ambulance trapped in jam from Clock Tower to Max Hospital."
    result = await agent.execute(
        session=None,
        principal=principal,
        message=message,
        language="en",
    )
    assert result.status == "ACTION_PENDING"
    assert result.execution_steps == [
        "triage_severity", "dispatch_unit", "query_corridor", "preempt_signals", "generate_guidance"
    ]
    assert result.metadata["severity"] == "CRITICAL"
    assert result.cta == "dispatch_emergency"
    assert result.action is not None
    assert result.action["action_type"] == "emergency_dispatch"
    assert result.action["vehicle_type"] == "ambulance"
    assert "112" in result.response_text
    assert "Green Wave" in result.response_text or "GREEN WAVE" in result.response_text.upper()


async def test_emergency_specialist_critical_fire_truck(principal):
    agent = EmergencySpecialist()
    message = "Urgent: massive fire reported in commercial shop near Clock Tower, fire truck en route."
    result = await agent.execute(
        session=None,
        principal=principal,
        message=message,
        language="en",
    )
    assert result.status == "ACTION_PENDING"
    assert result.execution_steps == [
        "triage_severity", "dispatch_unit", "query_corridor", "preempt_signals", "generate_guidance"
    ]
    assert result.metadata["severity"] == "CRITICAL"
    assert result.action["vehicle_type"] == "fire_truck"


async def test_emergency_specialist_advisory_traffic(principal):
    agent = EmergencySpecialist()
    message = "Is there a heavy traffic delay on Rajpur Road right now?"
    result = await agent.execute(
        session=None,
        principal=principal,
        message=message,
        language="en",
    )
    assert result.status == "ANSWERED"
    # Congestion data belongs to CityPulse; the emergency specialist only checks its CCTV feed.
    assert result.execution_steps == ["triage_severity", "check_incident_feed", "generate_guidance"]
    assert result.metadata["severity"] == "ADVISORY"
    assert result.action is None
    assert result.cta == "view_alternate_routes"
    assert "TRAFFIC" in result.response_text


async def test_emergency_question_does_not_dispatch(principal):
    agent = EmergencySpecialist()
    result = await agent.execute(
        session=None, principal=principal, message="Is there an accident on Rajpur Road?", language="en"
    )
    assert result.action is None
    assert "dispatch_unit" not in result.execution_steps


# ============================================================================
# KnowledgeSpecialist Tests
# ============================================================================

async def test_knowledge_specialist_verified_with_mock_hits(principal, monkeypatch):
    agent = KnowledgeSpecialist()
    doc_id = uuid4()
    chunk_id = uuid4()

    mock_hit = RetrievalHit(
        chunk_id=chunk_id,
        doc_id=doc_id,
        tenant_id="municipal",
        text="Property tax in Nagar Nigam Dehradun can be paid online via the municipal web portal with a 10% early rebate.",
        section=None,
        vector_score=0.92,
        vector_rank=1,
        lexical_rank=1,
        fused_score=0.95,
        jurisdiction="dehradun",
        verified=True,
        expires_at=None,
        title="NND Property Tax Guidelines",
        source_url="https://nagarnigamdehradun.com/tax",
        fetched_at=datetime.now(timezone.utc),
    )

    mock_retrieve = AsyncMock(return_value=[mock_hit])
    monkeypatch.setattr("src.agent.subagents.knowledge_agent.retrieve", mock_retrieve)

    mock_session = AsyncMock()
    result = await agent.execute(
        session=mock_session,
        principal=principal,
        message="How to pay property tax online in Dehradun?",
        language="en",
    )
    assert result.status == "ANSWERED"
    assert result.execution_steps == ["retrieve_evidence", "validate_evidence", "synthesize_or_abstain"]
    assert len(result.sources) >= 1
    assert result.sources[0]["title"] == "NND Property Tax Guidelines"
    assert "property tax" in result.response_text.lower()


async def test_knowledge_specialist_abstains_on_unverified_evidence(principal, monkeypatch):
    agent = KnowledgeSpecialist()
    # Mock retrieve returns a hit with very low vector score (< 0.70 threshold)
    low_score_hit = RetrievalHit(
        chunk_id=uuid4(),
        doc_id=uuid4(),
        tenant_id="municipal",
        text="Unverified hearsay about foreign city.",
        section=None,
        vector_score=0.35,
        vector_rank=1,
        lexical_rank=1,
        fused_score=0.35,
        jurisdiction="unknown",
        verified=True,
        expires_at=None,
        title="Unknown Document",
        source_url=None,
        fetched_at=datetime.now(timezone.utc),
    )

    mock_retrieve = AsyncMock(return_value=[low_score_hit])
    monkeypatch.setattr("src.agent.subagents.knowledge_agent.retrieve", mock_retrieve)

    mock_session = AsyncMock()
    result = await agent.execute(
        session=mock_session,
        principal=principal,
        message="What is the capital of Mars?",
        language="en",
    )
    assert result.status == "ABSTAINED"
    assert result.execution_steps == ["retrieve_evidence", "validate_evidence", "synthesize_or_abstain"]
    assert result.cta == "file_complaint"
    assert result.sources == []
    assert "verified" in result.response_text.lower()


async def test_knowledge_specialist_offline_corpus_search(principal):
    # Tests knowledge specialist running offline against actual corpus
    agent = KnowledgeSpecialist()
    result = await agent.execute(
        session=None,
        principal=principal,
        message="What are the rules for birth certificate or death registration in Dehradun?",
        language="en",
    )
    assert result.execution_steps == ["retrieve_evidence", "validate_evidence", "synthesize_or_abstain"]
    assert result.status in {"ANSWERED", "ABSTAINED"}


# ============================================================================
# CityPulseSpecialist Tests
# ============================================================================

async def test_city_pulse_specialist_briefing(principal):
    agent = CityPulseSpecialist()
    result = await agent.execute(
        session=None,
        principal=principal,
        message="What are today's city alerts and events?",
        language="en",
    )
    assert result.status == "ANSWERED"
    assert result.execution_steps == ["fetch_city_data", "format_briefing"]
    assert result.metadata["alerts_count"] >= 1
    assert result.metadata["events_count"] >= 1
    assert "Active City Alerts" in result.response_text
    assert "Upcoming Civic" in result.response_text
    assert result.cta == "view_alerts"


async def test_city_pulse_specialist_hindi(principal):
    agent = CityPulseSpecialist()
    result = await agent.execute(
        session=None,
        principal=principal,
        message="आज शहर के अलर्ट और कार्यक्रम क्या हैं?",
        language="hi",
    )
    assert result.status == "ANSWERED"
    assert result.execution_steps == ["fetch_city_data", "format_briefing"]
    assert "सक्रिय नागरिक चेतावनियाँ" in result.response_text
    assert "आगामी सार्वजनिक" in result.response_text


# ============================================================================
# App Data Tools & Schemas Tests
# ============================================================================

def test_tool_schemas_and_models():
    allowed = [
        "create_complaint",
        "get_complaint_status",
        "get_events",
        "get_active_alerts",
        "get_traffic_density",
        "get_emergency_corridor",
        "list_user_complaints",
        "ask_clarification",
    ]
    schemas = tool_schemas(allowed)
    assert len(schemas) == len(allowed)
    names = {s["function"]["name"] for s in schemas}
    assert names == set(allowed)


async def test_read_tool_density_and_corridor():
    # Density tool test
    density = await read_tool("get_traffic_density", {"junction_id": "Clock Tower", "corridor_id": "Rajpur Road"})
    assert density["served"] == "fallback"
    assert density["simulated"] is True
    assert density["density_level"] in {"LOW", "MODERATE", "HIGH"}
    assert "average_speed_kmh" in density

    # Emergency corridor tool test
    corridor = await read_tool(
        "get_emergency_corridor",
        {"origin": "Clock Tower", "destination": "Max Hospital", "vehicle_type": "ambulance"},
    )
    assert corridor["served"] == "fallback"
    assert corridor["green_wave_active"] is True
    assert corridor["status"] == "ACTIVE_CLEAR"
    assert len(corridor["signals_cleared"]) >= 1


async def test_read_tool_user_complaints_and_status():
    user_complaints = await read_tool("list_user_complaints", {"user_id": "citizen_42"})
    assert user_complaints["served"] == "fallback"
    assert len(user_complaints["complaints"]) >= 1

    status_found = await read_tool("get_complaint_status", {"tracking_id": "NND-2026-0841"})
    assert status_found["status"] == "IN_PROGRESS"
    assert status_found["data"]["assigned_worker"]

    status_not_found = await read_tool("get_complaint_status", {"tracking_id": "UNKNOWN-99999"})
    assert status_not_found["status"] == "not_found"


async def test_execute_complaint_idempotency():
    token = "test-token-idempotency-12345"
    args = {
        "category": "Potholes and Road Damage",
        "location": "Subhash Road near Clock Tower",
        "description": "Deep asphalt crater causing traffic bottleneck and accident risk.",
    }
    res1 = await execute_complaint(args, token, "user_1")
    res2 = await execute_complaint(args, token, "user_1")
    assert res1["trackingId"] == res2["trackingId"]
    assert res1["trackingId"].startswith("MOCK-")
