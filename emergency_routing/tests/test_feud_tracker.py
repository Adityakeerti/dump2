"""Unit tests for the 60-Second Feud Persistence Gate."""

from datetime import datetime, timedelta
import pytest
from agents.feud_tracker import FeudTracker
from agents.state import IncidentPayload


@pytest.fixture
def feud_tracker():
    return FeudTracker(min_duration_sec=60.0, cooldown_reset_sec=45.0)


def create_feud_event(camera_id: str, timestamp: datetime, intensity: float = 0.75):
    return IncidentPayload(
        incident_id=f"TEST-{timestamp.timestamp()}",
        incident_type="FEUD",
        camera_id=camera_id,
        location_node_id="test_node",
        latitude=28.6,
        longitude=77.2,
        address="Test Square",
        confidence=0.9,
        severity=intensity,
        timestamp=timestamp,
    )


def test_feud_below_60_seconds_does_not_alert_police(feud_tracker):
    base_time = datetime(2026, 1, 1, 12, 0, 0)
    e1 = create_feud_event("CAM-01", base_time)
    should_alert, state, _ = feud_tracker.process_feud_detection(e1)

    assert not should_alert
    assert state.elapsed_duration_seconds == 0.0
    assert not state.police_alerted

    # 30 seconds later
    e2 = create_feud_event("CAM-01", base_time + timedelta(seconds=30))
    should_alert, state, _ = feud_tracker.process_feud_detection(e2)

    assert not should_alert
    assert state.elapsed_duration_seconds == 30.0
    assert not state.police_alerted


def test_feud_persisting_60_seconds_triggers_police(feud_tracker):
    base_time = datetime(2026, 1, 1, 12, 0, 0)
    e1 = create_feud_event("CAM-02", base_time, intensity=0.8)
    feud_tracker.process_feud_detection(e1)

    # Intermediate frame at 30s confirms ongoing altercation
    e_mid = create_feud_event("CAM-02", base_time + timedelta(seconds=30), intensity=0.85)
    feud_tracker.process_feud_detection(e_mid)

    # 62 seconds later (elapsed >= 60s)
    e2 = create_feud_event("CAM-02", base_time + timedelta(seconds=62), intensity=0.9)
    should_alert, state, msg = feud_tracker.process_feud_detection(e2)

    assert should_alert
    assert state.police_alerted
    assert state.elapsed_duration_seconds == 62.0
    assert "ESCALATING TO POLICE AGENT" in msg

    # Next frame at 70s should NOT trigger duplicate alert
    e3 = create_feud_event("CAM-02", base_time + timedelta(seconds=70), intensity=0.9)
    should_alert2, state2, msg2 = feud_tracker.process_feud_detection(e3)
    assert not should_alert2
    assert "already alerted" in msg2.lower()


def test_feud_cooldown_resets_after_gap(feud_tracker):
    base_time = datetime(2026, 1, 1, 12, 0, 0)
    e1 = create_feud_event("CAM-03", base_time)
    feud_tracker.process_feud_detection(e1)

    # 50 seconds of silence (gap > cooldown_reset_sec of 45s)
    e2 = create_feud_event("CAM-03", base_time + timedelta(seconds=50))
    should_alert, state, msg = feud_tracker.process_feud_detection(e2)

    assert not should_alert
    assert state.elapsed_duration_seconds == 0.0
    assert "ceased" in msg.lower()
