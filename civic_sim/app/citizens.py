"""Residents: everyone lives in a block, sees what happens there and may report it to the complaint portal.

Reporting is stochastic and uneven on purpose: personas differ in propensity, and whole wards under-report
(ward factor drawn per episode). A block with a problem but quiet residents produces little evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import CivicConfig
from app.world import CityMap


@dataclass
class Report:
    citizen: int
    block: int
    category: int
    text: str


class Population:
    def __init__(self, cfg: CivicConfig, city: CityMap, rng: np.random.Generator) -> None:
        cc = cfg.citizens
        self.cfg = cfg
        n_cit = city.n * cc.per_block
        self.home = np.repeat(np.arange(city.n), cc.per_block)
        w = np.array([p.weight for p in cc.personas], dtype=float)
        self.persona = rng.choice(len(cc.personas), size=n_cit, p=w / w.sum())
        n_wards = int(city.ward.max()) + 1
        lo, hi = cc.ward_factor_range
        self.ward_factor = rng.uniform(lo, hi, size=n_wards)
        prop = np.array([p.propensity for p in cc.personas])[self.persona]
        self.rate = prop * self.ward_factor[city.ward[self.home]] * cc.report_scale
        self.cat_ids = [c.id for c in cfg.categories]

    def __len__(self) -> int:
        return len(self.home)

    def describe(self, citizen: int, city: CityMap) -> dict:
        p = self.cfg.citizens.personas[int(self.persona[citizen])]
        b = int(self.home[citizen])
        return {"id": f"R{citizen:04d}", "persona": p.label, "block": city.block_name(b), "ward": int(city.ward[b]) + 1}

    def report(self, intensity: np.ndarray, rng: np.random.Generator) -> list[Report]:
        """intensity [N, C] -> each resident reports each category at most once per tick."""
        lam = self.rate[:, None] * intensity[self.home]          # [R, C]
        p = 1.0 - np.exp(-lam)
        hit = rng.random(p.shape) < p
        out = []
        for r, c in zip(*np.nonzero(hit)):
            texts = self.cfg.citizens.templates[self.cat_ids[c]]
            out.append(Report(int(r), int(self.home[r]), int(c), texts[int(rng.integers(len(texts)))]))
        return out
