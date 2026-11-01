"""Historical Traffic Jam Database and Clearance Prediction Model."""

from typing import Dict, Optional
from pydantic import BaseModel


class SegmentHistoricalProfile(BaseModel):
    segment_id: str
    average_jam_duration_minutes: float
    clearance_rate_factor: float = 1.0  # Multiplier based on road capacity/dispersal
    typical_causes: str = "Congestion"


class TrafficHistoryDB:
    """Historical traffic analytics repository for estimating jam dissipation times."""

    def __init__(self):
        # Default segment historical statistics
        self.profiles: Dict[str, SegmentHistoricalProfile] = {
            "seg_main_blvd": SegmentHistoricalProfile(
                segment_id="seg_main_blvd",
                average_jam_duration_minutes=6.0,
                clearance_rate_factor=1.2,
                typical_causes="Traffic Light Bottleneck / Quick Dispersal",
            ),
            "seg_expressway_bridge": SegmentHistoricalProfile(
                segment_id="seg_expressway_bridge",
                average_jam_duration_minutes=35.0,
                clearance_rate_factor=0.7,
                typical_causes="Major Chokepoint / Slow Clearance",
            ),
            "seg_downtown_avenue": SegmentHistoricalProfile(
                segment_id="seg_downtown_avenue",
                average_jam_duration_minutes=8.0,
                clearance_rate_factor=1.0,
                typical_causes="Pedestrian Crossings / Moderate Clearance",
            ),
            "seg_ring_road": SegmentHistoricalProfile(
                segment_id="seg_ring_road",
                average_jam_duration_minutes=12.0,
                clearance_rate_factor=1.1,
                typical_causes="High Volume Interchange",
            ),
        }

    def register_profile(self, profile: SegmentHistoricalProfile):
        self.profiles[profile.segment_id] = profile

    def predict_clearance_time_from_now(
        self,
        segment_id: str,
        severity: float,
        started_minutes_ago: float = 0.0,
    ) -> float:
        """Estimates the remaining time (in minutes from now) until the traffic jam completely dissipates.

        Mathematical model:
        Expected Total Duration = Base Historical Average * (1.0 + severity * 0.8) / Clearance Rate Factor
        Remaining Clearance Time = max(0.5, Expected Total Duration - started_minutes_ago)
        """
        profile = self.profiles.get(segment_id)
        if profile is None:
            # Fallback default historical estimate
            base_duration = 10.0
            clearance_factor = 1.0
        else:
            base_duration = profile.average_jam_duration_minutes
            clearance_factor = profile.clearance_rate_factor

        expected_total_duration = (base_duration * (1.0 + severity * 0.8)) / clearance_factor
        remaining_time = max(0.5, expected_total_duration - started_minutes_ago)
        return round(remaining_time, 2)
