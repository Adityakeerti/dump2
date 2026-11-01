"""Road Network Graph and Pathfinding Utilities for Emergency Routing."""

from typing import Dict, List, Optional, Tuple
import heapq
import math
from pydantic import BaseModel


class RoadNode(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float


class ActiveJam(BaseModel):
    segment_id: str
    start_node: str
    end_node: str
    severity: float  # 0.0 (light slowdown) to 1.0 (deadlock)
    delay_minutes: float  # Current observed delay
    started_minutes_ago: float = 0.0


class RoadEdge(BaseModel):
    id: str
    start_node: str
    end_node: str
    distance_km: float
    speed_limit_kmh: float = 60.0
    active_jam: Optional[ActiveJam] = None
    flood_depth_cm: float = 0.0
    rainfall_intensity_mm: float = 0.0
    is_blocked: bool = False
    block_reason: Optional[str] = None

    @property
    def nominal_travel_time_minutes(self) -> float:
        return (self.distance_km / self.speed_limit_kmh) * 60.0

    @property
    def effective_travel_time_minutes(self) -> float:
        if self.is_blocked or self.flood_depth_cm >= 25.0:
            return float("inf")
        speed = self.speed_limit_kmh
        # Moderate flood water slows traffic down
        if self.flood_depth_cm >= 10.0:
            speed = max(10.0, speed * 0.4)
        elif self.flood_depth_cm > 0.0 or self.rainfall_intensity_mm >= 15.0:
            speed = max(20.0, speed * 0.7)
        return (self.distance_km / speed) * 60.0


class PathResult(BaseModel):
    nodes: List[str]
    edges: List[str]
    total_distance_km: float
    nominal_time_minutes: float
    effective_time_minutes: float = 0.0
    jams_encountered: List[ActiveJam]
    flooded_segments: List[str] = []
    weather_impacted: bool = False


class RoadGraph:
    """Graph representation of the city road network with dynamic traffic conditions."""

    def __init__(self):
        self.nodes: Dict[str, RoadNode] = {}
        self.adjacency: Dict[str, List[RoadEdge]] = {}
        self.edges_by_id: Dict[str, RoadEdge] = {}

    def add_node(self, node_id: str, name: str, latitude: float, longitude: float) -> RoadNode:
        node = RoadNode(id=node_id, name=name, latitude=latitude, longitude=longitude)
        self.nodes[node_id] = node
        if node_id not in self.adjacency:
            self.adjacency[node_id] = []
        return node

    def add_edge(
        self,
        edge_id: str,
        start_node: str,
        end_node: str,
        distance_km: float,
        speed_limit_kmh: float = 60.0,
        bidirectional: bool = True,
    ):
        edge1 = RoadEdge(
            id=edge_id,
            start_node=start_node,
            end_node=end_node,
            distance_km=distance_km,
            speed_limit_kmh=speed_limit_kmh,
        )
        self.adjacency[start_node].append(edge1)
        self.edges_by_id[edge_id] = edge1

        if bidirectional:
            edge_id_rev = f"{edge_id}_rev"
            edge2 = RoadEdge(
                id=edge_id_rev,
                start_node=end_node,
                end_node=start_node,
                distance_km=distance_km,
                speed_limit_kmh=speed_limit_kmh,
            )
            self.adjacency[end_node].append(edge2)
            self.edges_by_id[edge_id_rev] = edge2

    def set_jam(
        self,
        edge_id: str,
        severity: float,
        delay_minutes: float,
        started_minutes_ago: float = 0.0,
    ):
        """Inject or update a real-time traffic jam on a road segment."""
        edge = self.edges_by_id.get(edge_id)
        if edge:
            edge.active_jam = ActiveJam(
                segment_id=edge_id,
                start_node=edge.start_node,
                end_node=edge.end_node,
                severity=severity,
                delay_minutes=delay_minutes,
                started_minutes_ago=started_minutes_ago,
            )

    def clear_jam(self, edge_id: str):
        edge = self.edges_by_id.get(edge_id)
        if edge:
            edge.active_jam = None

    def set_weather_condition(
        self,
        edge_id: str,
        rainfall_mm: float = 0.0,
        flood_depth_cm: float = 0.0,
        is_blocked: bool = False,
        block_reason: Optional[str] = None,
    ):
        """Update rainfall and flood depth conditions on an edge and its reverse if present."""
        edge = self.edges_by_id.get(edge_id)
        if edge:
            edge.rainfall_intensity_mm = rainfall_mm
            edge.flood_depth_cm = flood_depth_cm
            edge.is_blocked = is_blocked
            edge.block_reason = block_reason

        rev_id = f"{edge_id}_rev" if not edge_id.endswith("_rev") else edge_id[:-4]
        rev_edge = self.edges_by_id.get(rev_id)
        if rev_edge:
            rev_edge.rainfall_intensity_mm = rainfall_mm
            rev_edge.flood_depth_cm = flood_depth_cm
            rev_edge.is_blocked = is_blocked
            rev_edge.block_reason = block_reason

    def clear_weather_conditions(self):
        """Reset all weather and flood conditions across the network."""
        for edge in self.edges_by_id.values():
            edge.rainfall_intensity_mm = 0.0
            edge.flood_depth_cm = 0.0
            edge.is_blocked = False
            edge.block_reason = None

    def find_shortest_path(
        self,
        start_node: str,
        target_node: str,
        avoid_edges: Optional[List[str]] = None,
        use_effective_time: bool = True,
    ) -> Optional[PathResult]:
        """Finds the fastest path using Dijkstra's algorithm.
        
        When use_effective_time is True, takes into account weather, rainfall slowdown,
        and treats flood depth >= 25cm or is_blocked as impassable.
        """
        if start_node not in self.nodes or target_node not in self.nodes:
            return None

        avoid = set(avoid_edges or [])
        # Priority queue stores (cumulative_minutes, current_node, path_nodes, path_edges)
        pq: List[Tuple[float, str, List[str], List[str]]] = [(0.0, start_node, [start_node], [])]
        min_time: Dict[str, float] = {start_node: 0.0}

        while pq:
            current_time, u, path_nodes, path_edges = heapq.heappop(pq)

            if u == target_node:
                total_dist = 0.0
                nominal_time = 0.0
                effective_time = 0.0
                jams: List[ActiveJam] = []
                flooded: List[str] = []
                weather_hit = False

                for e_id in path_edges:
                    edge = self.edges_by_id[e_id]
                    total_dist += edge.distance_km
                    nominal_time += edge.nominal_travel_time_minutes
                    eff = edge.effective_travel_time_minutes
                    effective_time += eff if not math.isinf(eff) else edge.nominal_travel_time_minutes

                    if edge.active_jam:
                        jams.append(edge.active_jam)
                    if edge.flood_depth_cm > 0.0 or edge.rainfall_intensity_mm >= 15.0 or edge.is_blocked:
                        flooded.append(e_id)
                        weather_hit = True

                return PathResult(
                    nodes=path_nodes,
                    edges=path_edges,
                    total_distance_km=round(total_dist, 2),
                    nominal_time_minutes=round(nominal_time, 2),
                    effective_time_minutes=round(effective_time, 2),
                    jams_encountered=jams,
                    flooded_segments=flooded,
                    weather_impacted=weather_hit,
                )

            if current_time > min_time.get(u, float("inf")):
                continue

            for edge in self.adjacency.get(u, []):
                if edge.id in avoid:
                    continue

                # If evaluating with effective time, check if impassable
                if use_effective_time:
                    if edge.is_blocked or edge.flood_depth_cm >= 25.0:
                        continue
                    cost = edge.effective_travel_time_minutes
                    if math.isinf(cost):
                        continue
                else:
                    cost = edge.nominal_travel_time_minutes

                v = edge.end_node
                tentative_time = current_time + cost

                if tentative_time < min_time.get(v, float("inf")):
                    min_time[v] = tentative_time
                    heapq.heappush(
                        pq,
                        (tentative_time, v, path_nodes + [v], path_edges + [edge.id]),
                    )

        return None

    def estimate_travel_time_to_segment(
        self, path_result: PathResult, target_segment_id: str, use_effective_time: bool = True
    ) -> float:
        """Computes the travel time (in minutes) from path start until reaching a specific segment."""
        time_elapsed = 0.0
        for edge_id in path_result.edges:
            if edge_id == target_segment_id:
                break
            edge = self.edges_by_id[edge_id]
            if use_effective_time:
                eff = edge.effective_travel_time_minutes
                time_elapsed += eff if not math.isinf(eff) else edge.nominal_travel_time_minutes
            else:
                time_elapsed += edge.nominal_travel_time_minutes
        return time_elapsed
