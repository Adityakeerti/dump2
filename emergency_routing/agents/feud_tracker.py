"""Feud Temporal Filter and Dispute Escalation Tracker."""

from datetime import datetime
from typing import Dict, Optional, Tuple
from config.settings import settings
from agents.state import FeudTrackingState, IncidentPayload


class FeudTracker:
    """Manages temporal sliding windows for public altercations and riots.

    Enforces the rule: Police should NOT be disturbed for brief arguments or
    instantaneous scuffles. Alerts are triggered ONLY when a feud persists for
    at least 60 seconds.
    """

    def __init__(self, min_duration_sec: float = None, cooldown_reset_sec: float = None):
        self.min_duration_sec = min_duration_sec or settings.FEUD_MIN_DURATION_SECONDS
        self.cooldown_reset_sec = cooldown_reset_sec or settings.FEUD_COOLDOWN_RESET_SECONDS
        self.tracked_cameras: Dict[str, FeudTrackingState] = {}

    def process_feud_detection(
        self, incident: IncidentPayload
    ) -> Tuple[bool, FeudTrackingState, str]:
        """Evaluates incoming feud detection against temporal thresholds.

        Returns:
            (should_alert_police, current_feud_state, explanation)
        """
        camera_id = incident.camera_id
        timestamp = incident.timestamp
        intensity = incident.severity

        tracker = self.tracked_cameras.get(camera_id)

        # Case 1: First time feud detected at this location
        if tracker is None or not tracker.is_active:
            tracker = FeudTrackingState(
                camera_id=camera_id,
                first_detected_at=timestamp,
                last_detected_at=timestamp,
                elapsed_duration_seconds=0.0,
                intensity_samples=[intensity],
                police_alerted=False,
                is_active=True,
            )
            self.tracked_cameras[camera_id] = tracker
            return (
                False,
                tracker,
                f"Dispute initiated at {camera_id}. Timer started. "
                f"Monitoring active; police not notified (duration: 0.0s / {self.min_duration_sec}s).",
            )

        # Case 2: Check if previous feud de-escalated (cooldown timeout exceeded)
        gap_seconds = (timestamp - tracker.last_detected_at).total_seconds()
        if gap_seconds > self.cooldown_reset_sec:
            # Previous dispute dissipated, reset for new altercation
            tracker = FeudTrackingState(
                camera_id=camera_id,
                first_detected_at=timestamp,
                last_detected_at=timestamp,
                elapsed_duration_seconds=0.0,
                intensity_samples=[intensity],
                police_alerted=False,
                is_active=True,
            )
            self.tracked_cameras[camera_id] = tracker
            return (
                False,
                tracker,
                f"Previous dispute ceased (> {self.cooldown_reset_sec}s ago). "
                f"New altercation detected at {camera_id}. Timer restarted.",
            )

        # Case 3: Continuous active feud
        tracker.last_detected_at = timestamp
        tracker.intensity_samples.append(intensity)
        tracker.elapsed_duration_seconds = (timestamp - tracker.first_detected_at).total_seconds()

        # Check threshold
        if tracker.elapsed_duration_seconds >= self.min_duration_sec:
            if not tracker.police_alerted:
                tracker.police_alerted = True
                avg_intensity = sum(tracker.intensity_samples) / len(tracker.intensity_samples)
                explanation = (
                    f"CRITICAL: Feud at {camera_id} has persisted continuously for "
                    f"{tracker.elapsed_duration_seconds:.1f}s (>= {self.min_duration_sec}s threshold). "
                    f"Average intensity: {avg_intensity:.2f}. ESCALATING TO POLICE AGENT."
                )
                return True, tracker, explanation
            else:
                return (
                    False,
                    tracker,
                    f"Feud continues ({tracker.elapsed_duration_seconds:.1f}s), "
                    f"but Police Agent was already alerted. Suppressing duplicate alert.",
                )
        else:
            remaining = self.min_duration_sec - tracker.elapsed_duration_seconds
            return (
                False,
                tracker,
                f"Feud ongoing for {tracker.elapsed_duration_seconds:.1f}s "
                f"(requires {remaining:.1f}s more continuous fighting before calling police).",
            )

    def mark_resolved(self, camera_id: str):
        """Clears feud tracker when camera footage confirms dispute has ended."""
        if camera_id in self.tracked_cameras:
            self.tracked_cameras[camera_id].is_active = False
