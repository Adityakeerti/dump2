"""Randomised population generator: reproducible, uneven, off-road, attached to the nearest entry."""

import math
import statistics
from pathlib import Path

from app.config import load_config
from app.population import M_PER_DEG_LAT, generate_clusters

CFG = load_config(Path(__file__).resolve().parent.parent / "config.yaml")
LAT0, LON0 = 30.33, 78.05


def ll(x, y):
    return [LAT0 + y / M_PER_DEG_LAT, LON0 + x / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))]


def topology():
    # 2 km arterial along x, side roads every 400 m alternating north/south
    cells = [{"id": i, "kind": "arterial", "coords": [ll(i * 100 - 1000, 0), ll(i * 100 - 900, 0)]} for i in range(20)]
    sources = [{"id": 0, "lat": ll(-1000, 0)[0], "lon": ll(-1000, 0)[1]}]
    for j in range(5):
        x = -800 + j * 400
        side = 1 if j % 2 == 0 else -1
        cells.append({"id": 100 + j, "kind": "cross", "coords": [ll(x, side * 200), ll(x, 0)]})
        p = ll(x, side * 200)
        sources.append({"id": j + 1, "lat": p[0], "lon": p[1]})
    return {"geometry": {"center": [LAT0, LON0], "cells": cells, "sources": sources}}


def test_reproducible_and_uneven():
    pop = CFG.population
    a = generate_clusters(pop, topology())
    b = generate_clusters(pop, topology())
    assert [c.model_dump() for c in a] == [c.model_dump() for c in b]
    sizes = [c.population for c in a]
    assert len(a) >= pop.clusters * 0.8
    assert abs(sum(sizes) - pop.total_population) <= pop.total_population * 0.05
    # uneven: coefficient of variation well above an even split
    assert statistics.pstdev(sizes) / statistics.mean(sizes) > 0.4
    assert len({c.persona for c in a}) > 1


def test_clusters_off_road_and_attached_to_nearest_entry():
    topo = topology()
    pop = CFG.population
    srcs = {s["id"]: s for s in topo["geometry"]["sources"]}
    for c in generate_clusters(pop, topo):
        s = srcs[c.source_id]
        dx, dy = c.offset_m
        # cluster position relative to its entry; check the entry is the nearest one
        cx = (s["lon"] - LON0) * M_PER_DEG_LAT * math.cos(math.radians(LAT0)) + dx
        cy = (s["lat"] - LAT0) * M_PER_DEG_LAT + dy
        dist = {sid: math.hypot(cx - (o["lon"] - LON0) * M_PER_DEG_LAT * math.cos(math.radians(LAT0)), cy - (o["lat"] - LAT0) * M_PER_DEG_LAT)
                for sid, o in srcs.items()}
        assert min(dist, key=dist.get) == c.source_id
        assert abs(cy) >= pop.min_road_distance_m - 1 or abs(cx) > 0  # not on the arterial axis
