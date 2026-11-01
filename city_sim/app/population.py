"""Randomised population: neighbourhood clusters scattered over the locality with uneven (lognormal) sizes.

Clusters are placed at random points around the corridor's real geometry (within `spread_m` of any road cell,
never on the carriageway), sized from a lognormal distribution normalised to `total_population`, given a
persona drawn from weighted categories, and attached to the nearest trip entry point. Seeded, so the same
config always produces the same city.
"""

from __future__ import annotations

import math
import random
from typing import Any

from app.config import ClusterConfig, PopulationConfig

M_PER_DEG_LAT = 111_320.0


def _xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    return ((lon - lon0) * M_PER_DEG_LAT * math.cos(math.radians(lat0)), (lat - lat0) * M_PER_DEG_LAT)


def generate_clusters(pop: PopulationConfig, topology: dict[str, Any]) -> list[ClusterConfig]:
    rng = random.Random(pop.seed)
    geo = topology["geometry"]
    lat0, lon0 = geo["center"]
    road_pts = [_xy(p[0], p[1], lat0, lon0) for cell in geo["cells"] for p in cell["coords"]]
    sources = [(s["id"], _xy(s["lat"], s["lon"], lat0, lon0)) for s in geo["sources"]]
    xs, ys = [p[0] for p in road_pts], [p[1] for p in road_pts]
    box = (min(xs) - pop.spread_m, max(xs) + pop.spread_m, min(ys) - pop.spread_m, max(ys) + pop.spread_m)

    def road_dist(x: float, y: float) -> float:
        return min(math.hypot(x - px, y - py) for px, py in road_pts)

    points: list[tuple[float, float]] = []
    tries = 0
    while len(points) < pop.clusters and tries < pop.clusters * 400:
        tries += 1
        x, y = rng.uniform(box[0], box[1]), rng.uniform(box[2], box[3])
        d = road_dist(x, y)
        if not (pop.min_road_distance_m <= d <= pop.spread_m):
            continue
        if any(math.hypot(x - px, y - py) < pop.min_spacing_m for px, py in points):
            continue
        points.append((x, y))

    weights = [rng.lognormvariate(0.0, pop.size_sigma) for _ in points]
    total_w = sum(weights) or 1.0
    names = list(pop.names)
    rng.shuffle(names)
    personas = [p.text for p in pop.personas]
    p_weights = [p.weight for p in pop.personas]
    clusters: list[ClusterConfig] = []
    for i, ((x, y), w) in enumerate(zip(points, weights)):
        sid, (sx, sy) = min(sources, key=lambda s: math.hypot(x - s[1][0], y - s[1][1]))
        base = names[i % len(names)]
        name = base if i < len(names) else f"{base} {i // len(names) + 1}"
        clusters.append(ClusterConfig(
            id=f"n{i:02d}",
            name=name,
            persona=rng.choices(personas, weights=p_weights)[0],
            population=max(pop.min_population, int(round(pop.total_population * w / total_w))),
            source_id=int(sid),
            offset_m=(round(x - sx, 1), round(y - sy, 1)),
        ))
    return clusters
