"""CivicEnv: the city, its residents, the complaint portal and two department agents acting on it.

One step = one tick (config.tick_hours). Each department picks one candidate from its observation:
inspect an asset, repair an asset, or wait. The world then advances one tick: causes emit symptoms,
potholes open, residents report, the portal routes complaints. The reward is shared by both departments
(the city's cost of unresolved problems, crew costs, and bonuses for confirming and removing root causes).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.causes import HiddenCause, emission_intensity, ground_truth, pothole_spawn_rate, sample_causes
from app.citizens import Population, Report
from app.config import CivicConfig
from app.portal import Portal, WorkOrder
from app.tracer import Candidate, Observation, observe
from app.world import CityMap, build_city


@dataclass
class EpisodeStats:
    complaints: int = 0
    weighted_complaints: float = 0.0
    inspections: int = 0
    repairs: int = 0
    false_repairs: int = 0
    symptom_actions: int = 0
    waits: int = 0
    reward: float = 0.0
    by_department: dict[str, dict[str, int]] = field(default_factory=dict)


class CivicEnv:
    def __init__(self, cfg: CivicConfig, city: CityMap | None = None) -> None:
        self.cfg = cfg
        self.city = city or build_city(cfg)
        self.departments = [d.id for d in cfg.departments]
        self.ci = cfg.category_index()
        self.severity = np.array([c.severity for c in cfg.categories])
        self.noise = np.array([c.noise_rate for c in cfg.categories])
        self.layer_cats = {l.id: [self.ci[c] for c in l.match] for l in cfg.layers}
        self.relief_cats = {l.id: [self.ci[c] for c in l.relief_categories] for l in cfg.layers}
        self.last_reports: list[Report] = []
        self.symptom_layers = {l.id for l in cfg.layers} - cfg.root_cause_layers()   # actions there only treat symptoms

    # ---------------------------------------------------------------- lifecycle
    def reset(self, seed: int, scenario: list[str] | None = None) -> dict[str, Observation]:
        n, c = self.city.n, len(self.cfg.categories)
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.population = Population(self.cfg, self.city, self.rng)
        self._causes: list[HiddenCause] = sample_causes(self.cfg, self.city, self.rng, scenario)
        self.potholes = np.zeros(n, dtype=int)
        self.relief_until = np.zeros((n, c), dtype=int)
        self.portal = Portal(self.cfg, n, self.cfg.horizon_ticks)
        self.stats = EpisodeStats(by_department={d: {"inspect": 0, "repair": 0, "wait": 0} for d in self.departments})
        self._advance()
        self.obs = self.observe()
        return self.obs

    def observe(self) -> dict[str, Observation]:
        return {d: observe(self.cfg, self.city, self.portal, d, self.tick) for d in self.departments}

    @property
    def done(self) -> bool:
        return self.tick >= self.cfg.horizon_ticks

    def step(self, choices: dict[str, int], policy: str = "unknown") -> tuple[dict[str, Observation], float, bool, dict]:
        rw = self.cfg.reward
        reward = 0.0
        executed = []
        for dept in self.departments:
            cand = self.obs[dept].candidates[choices.get(dept, len(self.obs[dept].candidates) - 1)]
            r, outcome = self._execute(cand, policy)
            reward += r
            executed.append({"department": dept, "action": cand.action, "layer": cand.layer, "asset": cand.asset,
                             **outcome})
        self.tick += 1
        weighted = self._advance()
        reward -= rw.complaint_weight * weighted
        self.stats.reward += reward
        self.obs = self.observe()
        return self.obs, reward, self.done, {"actions": executed, "new_complaints": len(self.last_reports)}

    # ---------------------------------------------------------------- actions
    def _fault(self, layer: str, asset: int) -> HiddenCause | None:
        return next((h for h in self._causes if h.layer == layer and h.asset == asset and h.active(self.tick)), None)

    def _execute(self, cand: Candidate, policy: str) -> tuple[float, dict]:
        rw, st = self.cfg.reward, self.stats
        if cand.action == "wait":
            st.waits += 1
            st.by_department[cand.department]["wait"] += 1
            return 0.0, {"found_fault": False}
        layer = self.city.layers[cand.layer]
        asset = layer.assets[cand.asset]
        zone_blocks = np.flatnonzero(layer.zone[cand.asset])
        st.by_department[cand.department][cand.action] += 1
        reward, found, bonus = 0.0, False, ""

        if cand.layer in self.symptom_layers:
            found = bool(self.potholes[zone_blocks].sum() > 0)
            if cand.action == "inspect":
                st.inspections += 1
                reward -= rw.inspect_cost
            else:
                st.repairs += 1
                st.symptom_actions += 1
                reward -= rw.repair_cost
                if "pothole" in self.cfg.layer(cand.layer).primary:     # road crew patches the potholes
                    self.potholes[zone_blocks] = 0
                    if not found:
                        st.false_repairs += 1
                        reward -= rw.false_repair_penalty
                self._relieve(cand.layer, cand.asset)
                self.portal.address(zone_blocks, self.layer_cats[cand.layer])
        else:
            hc = self._fault(cand.layer, cand.asset)
            miss = self.cfg.layer(cand.layer).inspect_miss_prob
            if cand.action == "inspect":
                st.inspections += 1
                reward -= rw.inspect_cost
                found = hc is not None and self.rng.random() >= miss
            else:
                st.repairs += 1
                reward -= rw.repair_cost
                found = hc is not None
                if found:
                    hc.fixed_tick = self.tick + 1
                    reward += rw.fix_bonus
                    bonus = "fixed"
                else:
                    st.false_repairs += 1
                    reward -= rw.false_repair_penalty
                    self._relieve(cand.layer, cand.asset)
                self.portal.address(zone_blocks, self.layer_cats[cand.layer])
            if found and hc.identified_tick is None:
                hc.identified_tick = self.tick
                reward += rw.identify_bonus
                bonus = bonus or "identified"
        self.portal.log(WorkOrder(self.tick, cand.department, cand.layer, cand.asset, cand.action, found, policy))
        return reward, {"found_fault": found, "asset_name": asset.name, "bonus": bonus, "block": asset.root}

    def _relieve(self, layer_id: str, asset: int) -> None:
        cats = self.relief_cats[layer_id]
        if not cats:
            return
        lc = self.cfg.layer(layer_id)
        hops = self.city.layers[layer_id].hops[asset]
        blocks = np.flatnonzero((hops >= 0) & (hops <= lc.relief_hops))
        until = self.tick + 1 + self.cfg.episode.relief_ticks
        for c in cats:
            self.relief_until[blocks, c] = np.maximum(self.relief_until[blocks, c], until)

    # ---------------------------------------------------------------- world dynamics
    def intensity(self) -> np.ndarray:
        rd = self.cfg.roads
        t = self.tick
        inten = np.tile(self.noise, (self.city.n, 1))
        inten += emission_intensity(self.cfg, self.city, self._causes, t)
        inten[:, self.ci["pothole"]] += self.potholes * rd.pothole_intensity
        inten[:, self.ci["traffic_jam"]] += self.potholes * rd.traffic_per_pothole * self.city.arterial
        inten[self.relief_until > t] = 0.0
        return inten

    def _advance(self) -> float:
        rd = self.cfg.roads
        new = (self.rng.random(self.city.n) < rd.random_pothole_prob).astype(int)
        new += self.rng.poisson(pothole_spawn_rate(self.cfg, self.city, self._causes, self.tick))
        self.potholes = np.minimum(self.potholes + new, rd.max_potholes_per_block)
        reports = self.population.report(self.intensity(), self.rng)
        for r in reports:
            self.portal.file(self.tick, r.citizen, r.block, r.category, r.text)
        self.last_reports = reports
        weighted = float(sum(self.severity[r.category] for r in reports))
        self.stats.complaints += len(reports)
        self.stats.weighted_complaints += weighted
        return weighted

    # ---------------------------------------------------------------- evaluation only
    def ground_truth(self) -> list[dict]:
        """For evaluation and the demo's reveal. Policies and the tracer never call this."""
        return ground_truth(self._causes, self.city)

    def episode_metrics(self) -> dict:
        st = self.stats
        causes = self._causes
        started = [h for h in causes if h.onset_tick < self.cfg.horizon_ticks]
        ident = [h for h in started if h.identified_tick is not None]
        return {
            "causes": len(started),
            "identified": len(ident),
            "fixed": sum(h.fixed_tick is not None for h in started),
            "ticks_to_identify": [h.identified_tick - h.onset_tick for h in ident],
            "complaints": st.complaints,
            "weighted_complaints": round(st.weighted_complaints, 2),
            "inspections": st.inspections,
            "repairs": st.repairs,
            "false_repairs": st.false_repairs,
            "symptom_actions": st.symptom_actions,
            "reward": round(st.reward, 3),
        }
