"""Predictive Emergency Routing Engine with Historical Jam Clearance Analysis."""

from typing import List, Optional
from pydantic import BaseModel
from routing.graph import RoadGraph, PathResult, ActiveJam
from routing.traffic_history import TrafficHistoryDB


class JamEvaluation(BaseModel):
    segment_id: str
    ambulance_reach_time_minutes: float  # t_reach
    predicted_clearance_time_minutes: float  # t_clear
    will_clear_before_arrival: bool
    residual_delay_minutes: float
    explanation: str


class WeatherFloodEvaluation(BaseModel):
    segment_id: str
    flood_depth_cm: float
    rainfall_mm: float
    is_impassable: bool
    speed_penalty_percent: float
    explanation: str


class PredictiveRouteDecision(BaseModel):
    selected_path: PathResult
    rerouted: bool
    nominal_fastest_path: PathResult
    alternative_path: Optional[PathResult] = None
    reason: str
    jam_evaluations: List[JamEvaluation] = []
    weather_evaluations: List[WeatherFloodEvaluation] = []
    weather_rerouted: bool = False


class PredictiveRouter:
    """Evaluates routes and determines whether to preserve the fastest path or reroute."""

    def __init__(self, graph: RoadGraph, history_db: Optional[TrafficHistoryDB] = None):
        self.graph = graph
        self.history_db = history_db or TrafficHistoryDB()

    def _collect_weather_evaluations(self, paths: List[PathResult]) -> List[WeatherFloodEvaluation]:
        evaluations: List[WeatherFloodEvaluation] = []
        seen = set()
        for path in paths:
            for edge_id in path.edges:
                if edge_id in seen:
                    continue
                seen.add(edge_id)
                edge = self.graph.edges_by_id.get(edge_id)
                if not edge:
                    continue
                if edge.flood_depth_cm > 0.0 or edge.rainfall_intensity_mm >= 15.0 or edge.is_blocked:
                    impassable = edge.is_blocked or edge.flood_depth_cm >= 25.0
                    penalty = 100.0 if impassable else (60.0 if edge.flood_depth_cm >= 10.0 else 30.0)
                    if impassable:
                        expl = f"Segment '{edge_id}': Flood depth {edge.flood_depth_cm:.1f} cm (CRITICAL >= 25cm impassable). Blocked."
                    else:
                        expl = f"Segment '{edge_id}': Flood depth {edge.flood_depth_cm:.1f} cm, Rain {edge.rainfall_intensity_mm:.1f} mm/h. Speed penalized by {penalty:.0f}%."
                    evaluations.append(
                        WeatherFloodEvaluation(
                            segment_id=edge_id,
                            flood_depth_cm=round(edge.flood_depth_cm, 1),
                            rainfall_mm=round(edge.rainfall_intensity_mm, 1),
                            is_impassable=impassable,
                            speed_penalty_percent=penalty,
                            explanation=expl,
                        )
                    )
        return evaluations

    def plan_emergency_route(
        self, origin_node: str, destination_node: str
    ) -> Optional[PredictiveRouteDecision]:
        # 1. Compute dry nominal path (ignoring weather/flood)
        dry_nominal_path = self.graph.find_shortest_path(origin_node, destination_node, use_effective_time=False)
        if not dry_nominal_path:
            return None

        # 2. Compute effective path considering flood depth, closures, and weather slowdowns
        primary_path = self.graph.find_shortest_path(origin_node, destination_node, use_effective_time=True)
        if not primary_path:
            # Entire network is cut off by flood or road closures
            weather_evals = self._collect_weather_evaluations([dry_nominal_path])
            return PredictiveRouteDecision(
                selected_path=dry_nominal_path,
                rerouted=True,
                weather_rerouted=True,
                nominal_fastest_path=dry_nominal_path,
                reason="All viable routes between origin and destination are blocked by flooding or severe weather.",
                jam_evaluations=[],
                weather_evaluations=weather_evals,
            )

        weather_evals = self._collect_weather_evaluations([dry_nominal_path, primary_path])
        weather_rerouted = (primary_path.edges != dry_nominal_path.edges) and any(
            w.is_impassable for w in weather_evals
        )

        # 3. Check for active jams on the weather-viable path
        if not primary_path.jams_encountered:
            if weather_rerouted:
                blocked_segments = [w.segment_id for w in weather_evals if w.is_impassable]
                reason = (
                    f"Rerouting: Dry-weather fastest path bypassed due to flood/blockage on "
                    f"[{', '.join(blocked_segments)}]. Weather-safe route selected."
                )
                return PredictiveRouteDecision(
                    selected_path=primary_path,
                    rerouted=True,
                    weather_rerouted=True,
                    nominal_fastest_path=dry_nominal_path,
                    reason=reason,
                    jam_evaluations=[],
                    weather_evaluations=weather_evals,
                )
            return PredictiveRouteDecision(
                selected_path=primary_path,
                rerouted=False,
                weather_rerouted=False,
                nominal_fastest_path=primary_path,
                reason="Primary fastest path is completely clear of traffic jams.",
                jam_evaluations=[],
                weather_evaluations=weather_evals,
            )

        jam_evaluations: List[JamEvaluation] = []
        avoid_edges: List[str] = []
        total_unavoidable_delay = 0.0

        for jam in primary_path.jams_encountered:
            # Time for ambulance to reach the jam segment using weather-effective speeds
            t_reach = self.graph.estimate_travel_time_to_segment(primary_path, jam.segment_id, use_effective_time=True)

            # Historical clearance prediction
            t_clear = self.history_db.predict_clearance_time_from_now(
                segment_id=jam.segment_id,
                severity=jam.severity,
                started_minutes_ago=jam.started_minutes_ago,
            )

            # Core Decision Rule:
            # If ambulance arrives after or as jam clears (t_reach >= t_clear), DO NOT REROUTE
            if t_reach >= t_clear:
                will_clear = True
                residual_delay = 0.0
                explanation = (
                    f"Jam on '{jam.segment_id}' will clear in {t_clear:.1f} mins from now. "
                    f"Ambulance will arrive in {t_reach:.1f} mins. "
                    f"Traffic will be cleared by arrival -> PRESERVE PATH."
                )
            else:
                will_clear = False
                # Remaining delay ambulance will suffer
                residual_delay = min(jam.delay_minutes, max(1.0, t_clear - t_reach))
                total_unavoidable_delay += residual_delay
                avoid_edges.append(jam.segment_id)
                explanation = (
                    f"Jam on '{jam.segment_id}' will persist for {t_clear:.1f} mins. "
                    f"Ambulance will arrive in {t_reach:.1f} mins (before clearance). "
                    f"Estimated residual delay: {residual_delay:.1f} mins -> CANDIDATE FOR REROUTE."
                )

            jam_evaluations.append(
                JamEvaluation(
                    segment_id=jam.segment_id,
                    ambulance_reach_time_minutes=round(t_reach, 2),
                    predicted_clearance_time_minutes=round(t_clear, 2),
                    will_clear_before_arrival=will_clear,
                    residual_delay_minutes=round(residual_delay, 2),
                    explanation=explanation,
                )
            )

        # If all jams will clear before arrival, do not reroute for traffic
        if not avoid_edges:
            if weather_rerouted:
                reason = "Weather-safe path preserved. All jams on route predicted to clear before ambulance arrives."
                reroute_flag = True
            else:
                reason = "All jams on fastest path are predicted to clear before ambulance arrives. No reroute needed."
                reroute_flag = False

            return PredictiveRouteDecision(
                selected_path=primary_path,
                rerouted=reroute_flag,
                weather_rerouted=weather_rerouted,
                nominal_fastest_path=dry_nominal_path,
                reason=reason,
                jam_evaluations=jam_evaluations,
                weather_evaluations=weather_evals,
            )

        # 4. If there are persistent jams, compute alternative path avoiding them while also respecting weather
        alternative_path = self.graph.find_shortest_path(
            origin_node, destination_node, avoid_edges=avoid_edges, use_effective_time=True
        )

        effective_primary_time = primary_path.nominal_time_minutes + total_unavoidable_delay

        if alternative_path and alternative_path.nominal_time_minutes < effective_primary_time:
            reason = (
                f"Rerouting: Alternative path ({alternative_path.nominal_time_minutes:.1f} mins) "
                f"is faster than staying on primary path with persistent jam delay "
                f"({effective_primary_time:.1f} mins)."
            )
            return PredictiveRouteDecision(
                selected_path=alternative_path,
                rerouted=True,
                weather_rerouted=weather_rerouted,
                nominal_fastest_path=dry_nominal_path,
                alternative_path=alternative_path,
                reason=reason,
                jam_evaluations=jam_evaluations,
                weather_evaluations=weather_evals,
            )
        else:
            reason = (
                f"Staying on primary path: Even with persistent delay ({effective_primary_time:.1f} mins), "
                f"it remains optimal compared to alternatives."
            )
            return PredictiveRouteDecision(
                selected_path=primary_path,
                rerouted=weather_rerouted,
                weather_rerouted=weather_rerouted,
                nominal_fastest_path=dry_nominal_path,
                alternative_path=alternative_path,
                reason=reason,
                jam_evaluations=jam_evaluations,
                weather_evaluations=weather_evals,
            )
