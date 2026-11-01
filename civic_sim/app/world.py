"""Public city map: blocks, wards, arterials and the infrastructure dependency layers.

Everything here is what a city would have on file (pipe maps, collection routes, feeder circuits).
It contains no information about which asset is faulty. Built deterministically from config + seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.config import CivicConfig, LayerConfig

METERS_PER_DEG_LAT = 111_320.0


@dataclass
class Asset:
    index: int
    layer: str
    root: int                  # block where the asset sits (segment end, depot, transformer, premises)
    name: str


@dataclass
class Layer:
    cfg: LayerConfig
    assets: list[Asset]
    hops: np.ndarray           # [A, N] hop distance from the asset to each block in its zone, -1 outside
    parent: np.ndarray | None = None   # tree layers: parent block of each block (-1 at the root)

    @property
    def zone(self) -> np.ndarray:
        return self.hops >= 0


@dataclass
class CityMap:
    rows: int
    cols: int
    lat: np.ndarray
    lon: np.ndarray
    ward: np.ndarray
    arterial: np.ndarray       # bool [N]
    layers: dict[str, Layer] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return self.rows * self.cols

    def rc(self, node: int) -> tuple[int, int]:
        return divmod(node, self.cols)

    def node(self, r: int, c: int) -> int:
        return r * self.cols + c

    def block_name(self, node: int) -> str:
        r, c = self.rc(node)
        return f"B{r}{c}"

    def neighbours(self, node: int) -> list[int]:
        r, c = self.rc(node)
        out = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < self.rows and 0 <= cc < self.cols:
                out.append(self.node(rr, cc))
        return out

    def manhattan(self, a: int, b: int) -> int:
        (ra, ca), (rb, cb) = self.rc(a), self.rc(b)
        return abs(ra - rb) + abs(ca - cb)


def _random_spanning_tree(city: CityMap, root: int, rng: np.random.Generator) -> np.ndarray:
    """Randomised Prim-style growth: pops a random frontier edge, so branches are long and irregular like real networks."""
    parent = np.full(city.n, -1, dtype=int)
    seen = {root}
    frontier = [(root, nb) for nb in city.neighbours(root)]
    while frontier:
        i = int(rng.integers(len(frontier)))
        frm, to = frontier.pop(i)
        if to in seen:
            continue
        seen.add(to)
        parent[to] = frm
        frontier += [(to, nb) for nb in city.neighbours(to) if nb not in seen]
    return parent


def _subtree_hops(parent: np.ndarray, n: int) -> np.ndarray:
    """hops[a, v] = depth(v) - depth(a) if v is in a's subtree (a included), else -1."""
    hops = np.full((n, n), -1, dtype=int)
    for v in range(n):
        a, d = v, 0
        while a != -1:
            hops[a, v] = d
            a, d = int(parent[a]), d + 1
    return hops


def _partition(order: list[int], k: int) -> list[list[int]]:
    size = math.ceil(len(order) / k)
    return [order[i * size:(i + 1) * size] for i in range(k) if order[i * size:(i + 1) * size]]


def _build_layer(city: CityMap, lc: LayerConfig, rng: np.random.Generator) -> Layer:
    n = city.n
    if lc.kind == "tree":
        root = city.node(*lc.tree_root)
        parent = _random_spanning_tree(city, root, rng)
        hops = _subtree_hops(parent, n)
        assets = [Asset(v, lc.id, v, f"{lc.label} into {city.block_name(v)}") for v in range(n)]
        return Layer(lc, assets, hops, parent)
    if lc.kind in ("node", "radius"):
        hops = np.full((n, n), -1, dtype=int)
        for a in range(n):
            for v in range(n):
                d = city.manhattan(a, v)
                if d <= (lc.radius if lc.kind == "radius" else 0):
                    hops[a, v] = d
        assets = [Asset(v, lc.id, v, f"{lc.label} at {city.block_name(v)}") for v in range(n)]
        return Layer(lc, assets, hops)
    # route: snake order over rows; feeder: column bands. Different partitions so the layers overlap differently.
    if lc.kind == "route":
        order = [city.node(r, c) for r in range(city.rows)
                 for c in (range(city.cols) if r % 2 == 0 else reversed(range(city.cols)))]
    else:
        order = [city.node(r, c) for c in range(city.cols) for r in range(city.rows)]
    groups = _partition(order, lc.num_assets)
    hops = np.full((len(groups), n), -1, dtype=int)
    assets = []
    for i, g in enumerate(groups):
        root = g[len(g) // 2]
        for v in g:
            hops[i, v] = 0
        assets.append(Asset(i, lc.id, root, f"{lc.label} {i + 1}"))
    return Layer(lc, assets, hops)


def build_city(cfg: CivicConfig) -> CityMap:
    g = cfg.grid
    rng = np.random.default_rng(cfg.seed)
    rows, cols = g.rows, g.cols
    n = rows * cols
    r = np.arange(n) // cols
    c = np.arange(n) % cols
    dy = (r - (rows - 1) / 2) * g.spacing_m * -1     # row 0 is the north edge
    dx = (c - (cols - 1) / 2) * g.spacing_m
    lat = g.center_lat + dy / METERS_PER_DEG_LAT
    lon = g.center_lon + dx / (METERS_PER_DEG_LAT * math.cos(math.radians(g.center_lat)))
    wards_per_row = math.ceil(cols / g.ward_block)
    ward = (r // g.ward_block) * wards_per_row + (c // g.ward_block)
    arterial = np.isin(r, g.arterial_rows) | np.isin(c, g.arterial_cols)
    city = CityMap(rows, cols, lat, lon, ward, arterial)
    for lc in cfg.layers:
        city.layers[lc.id] = _build_layer(city, lc, rng)
    return city


def geometry(city: CityMap) -> dict:
    """JSON-ready map for a dashboard: blocks, wards, pipe trees, routes, feeders."""
    layers = {}
    for lid, layer in city.layers.items():
        entry: dict = {"label": layer.cfg.label, "kind": layer.cfg.kind, "department": layer.cfg.department}
        if layer.parent is not None:
            entry["edges"] = [[int(p), v] for v, p in enumerate(layer.parent) if p >= 0]
        if layer.cfg.kind in ("route", "feeder"):
            entry["groups"] = [{"asset": a.index, "name": a.name, "root": a.root,
                                "blocks": np.flatnonzero(layer.zone[a.index]).tolist()} for a in layer.assets]
        layers[lid] = entry
    return {
        "blocks": [{"id": v, "name": city.block_name(v), "lat": float(city.lat[v]), "lon": float(city.lon[v]),
                    "ward": int(city.ward[v]), "arterial": bool(city.arterial[v])} for v in range(city.n)],
        "layers": layers,
    }
