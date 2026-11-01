"""HIDDEN world state: planted root causes and how they turn into symptoms.

Only env.py may import this module. The tracer, policies and diagnosis see complaints, inspection
results and repair outcomes, never these objects (enforced by tests/test_isolation.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from app.config import CauseConfig, CivicConfig
from app.world import CityMap


@dataclass
class HiddenCause:
    cause_type: str
    layer: str
    asset: int
    root_block: int
    onset_tick: int
    fixed_tick: int | None = None
    identified_tick: int | None = None

    def active(self, tick: int) -> bool:
        return tick >= self.onset_tick and (self.fixed_tick is None or tick < self.fixed_tick)


def sample_causes(cfg: CivicConfig, city: CityMap, rng: np.random.Generator,
                  force: list[str] | None = None) -> list[HiddenCause]:
    """Draw the episode's root causes. `force` lists cause types to plant (scenario); [] means a control episode."""
    by_id = {c.id: c for c in cfg.causes}
    if force is None:
        k = int(rng.integers(cfg.episode.min_causes, cfg.episode.max_causes + 1))
        w = np.array([c.weight for c in cfg.causes], dtype=float)
        picks = rng.choice(len(cfg.causes), size=min(k, len(cfg.causes)), replace=False, p=w / w.sum())
        types = [cfg.causes[int(i)].id for i in picks]
    else:
        types = list(force)
    out: list[HiddenCause] = []
    used: set[tuple[str, int]] = set()
    for t in types:
        cc = by_id[t]
        layer = city.layers[cc.layer]
        choices = [a.index for a in layer.assets if (cc.layer, a.index) not in used
                   and layer.zone[a.index].sum() >= cc.min_zone_blocks]
        asset = int(rng.choice(choices))
        used.add((cc.layer, asset))
        onset = int(rng.integers(0, cfg.episode.onset_max_tick + 1))
        out.append(HiddenCause(t, cc.layer, asset, layer.assets[asset].root, onset))
    return out


def emission_intensity(cfg: CivicConfig, city: CityMap, causes: list[HiddenCause], tick: int) -> np.ndarray:
    """[N, C] complaint intensity produced by active causes at this tick."""
    ci = cfg.category_index()
    by_id = {c.id: c for c in cfg.causes}
    out = np.zeros((city.n, len(cfg.categories)))
    for hc in causes:
        if not hc.active(tick):
            continue
        hops = city.layers[hc.layer].hops[hc.asset]
        age = tick - hc.onset_tick
        for e in by_id[hc.cause_type].emissions:
            on = (hops >= e.min_hop) & (age >= e.delay_ticks + hops * e.spread_ticks_per_hop)
            out[on, ci[e.category]] += e.rate * e.hop_factor ** hops[on]
    return out


def pothole_spawn_rate(cfg: CivicConfig, city: CityMap, causes: list[HiddenCause], tick: int) -> np.ndarray:
    """[N] expected new potholes per block this tick from active causes (e.g. a leak washing out the road bed)."""
    by_id: dict[str, CauseConfig] = {c.id: c for c in cfg.causes}
    rate = np.zeros(city.n)
    for hc in causes:
        cc = by_id[hc.cause_type]
        if not hc.active(tick) or cc.pothole_spawn <= 0:
            continue
        hops = city.layers[hc.layer].hops[hc.asset]
        near = (hops >= 0) & (hops <= cc.pothole_hops)
        rate[near] += cc.pothole_spawn
    return rate


def ground_truth(causes: list[HiddenCause], city: CityMap) -> list[dict]:
    return [{**asdict(c), "root_block_name": city.block_name(c.root_block),
             "asset_name": city.layers[c.layer].assets[c.asset].name} for c in causes]
