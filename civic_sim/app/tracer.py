"""Deterministic tracer: turns portal evidence into candidate actions with explainable features.

Inputs are PUBLIC only: the city map (pipe trees, routes, feeders), the mechanism table in config, the
complaint counts and the work log. This module must not import app.causes or app.env (see tests).

For every asset of a department's layers it measures how well the asset's zone explains recent complaints:
  coverage  = share of all matching complaints that fall inside the zone
  lift      = complaint density inside the zone relative to the city average
  root_first= the asset's own block reported first (where the problem started)
Top assets per layer become candidates, each with an `inspect` and a `repair` action, plus one `wait`.
The RL policy scores these candidates; the tracer baseline ranks them with a fixed formula.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import CivicConfig
from app.portal import Portal
from app.world import CityMap

BASE_FEATURES = [
    "mass_primary", "mass_secondary", "cov_primary", "cov_secondary", "lift", "zone_frac", "local",
    "onset_age", "root_first", "trend", "insp_pos", "insp_neg", "since_insp", "repaired_recent",
    "repair_failed", "repair_fixed", "score",
]
ACTIONS = ("inspect", "repair")
EPS = 1e-6


def feature_names(cfg: CivicConfig) -> list[str]:
    return (BASE_FEATURES + [f"act_{a}" for a in ACTIONS] + [f"layer_{l.id}" for l in cfg.layers]
            + [f"dept_{d.id}" for d in cfg.departments] + ["time_frac", "is_wait"])


def max_candidates(cfg: CivicConfig) -> int:
    per_layer_assets = 3 * cfg.tracer.candidates_per_layer + 1      # top-k mass, lift, score + best confirmed
    return max(len(d.layers) for d in cfg.departments) * per_layer_assets * len(ACTIONS) + 1


@dataclass
class Candidate:
    department: str
    layer: str | None
    asset: int | None
    action: str                  # inspect | repair | wait
    features: dict[str, float]


@dataclass
class Observation:
    """Per-department padded candidate matrix for the policy."""
    department: str
    feats: np.ndarray            # [K, D]
    mask: np.ndarray             # [K] bool
    candidates: list[Candidate]


def layer_evidence(cfg: CivicConfig, city: CityMap, portal: Portal, layer_id: str, tick: int) -> dict[str, np.ndarray]:
    """Vectorised per-asset evidence for one layer at `tick`."""
    tc = cfg.tracer
    layer = city.layers[layer_id]
    ci = cfg.category_index()
    n_cat = len(cfg.categories)
    m_p, m_s = np.zeros(n_cat), np.zeros(n_cat)
    for cat, w in layer.cfg.match.items():
        (m_p if cat in layer.cfg.primary else m_s)[ci[cat]] = w

    win = portal.window(tick, tc.window_ticks)                       # [N, C]
    x_p, x_s = win @ m_p, win @ m_s
    zone = layer.zone.astype(float)                                  # [A, N]
    size = zone.sum(axis=1)
    mass_p, mass_s = zone @ x_p, zone @ x_s
    cov_p = mass_p / (x_p.sum() + EPS)
    cov_s = mass_s / (x_s.sum() + EPS)
    city_density = (x_p.sum() + x_s.sum()) / city.n
    lift = (mass_p + mass_s) / np.maximum(size, 1) / (city_density + EPS)
    roots = np.array([a.root for a in layer.assets])
    local = (x_p + x_s)[roots]

    half = max(1, tc.window_ticks // 2)
    recent = portal.window(tick, half) @ (m_p + m_s)
    older = (portal.window(tick - half, half) @ (m_p + m_s)) if tick - half >= 0 else np.zeros(city.n)
    trend = zone @ (recent - older)

    ft = portal.first_tick[:, m_p > 0].astype(float)                # first primary complaint per block
    ft[ft < 0] = np.inf
    first_p = ft.min(axis=1) if ft.shape[1] else np.full(city.n, np.inf)
    zone_first = np.where(layer.zone, first_p[None, :], np.inf).min(axis=1)
    near = (layer.hops >= 0) & (layer.hops <= 1)                     # the asset's block and its first hop
    near_first = np.where(near, first_p[None, :], np.inf).min(axis=1)
    root_first = (np.isfinite(near_first) & (near_first <= zone_first)).astype(float)
    onset_age = np.where(np.isfinite(zone_first), (tick - zone_first) / cfg.horizon_ticks, 0.0)

    score = ((cov_p + tc.score_secondary_weight * cov_s) * np.minimum(lift / tc.lift_norm, 1.0)
             + tc.score_root_first_bonus * root_first * (mass_p > 0))
    return {
        "mass_primary": mass_p / tc.count_norm, "mass_secondary": mass_s / tc.count_norm,
        "cov_primary": cov_p, "cov_secondary": cov_s, "lift": np.minimum(lift / tc.lift_norm, 2.0),
        "zone_frac": size / city.n, "local": local / tc.count_norm, "onset_age": onset_age,
        "root_first": root_first, "trend": trend / tc.count_norm, "score": score,
        "_mass": mass_p + mass_s, "_lift": lift, "_zone_first": zone_first,
    }


def _work_features(cfg: CivicConfig, portal: Portal, layer_id: str, asset: int, tick: int) -> dict[str, float]:
    insp = portal.inspected.get((layer_id, asset))
    rep = portal.repaired.get((layer_id, asset))
    w = cfg.tracer.window_ticks
    return {
        "insp_pos": float(bool(insp and insp[1])),
        "insp_neg": float(bool(insp and not insp[1])),
        "since_insp": min((tick - insp[0]) / w, 2.0) if insp else 2.0,
        "repaired_recent": float(bool(rep and tick - rep[0] < w)),
        "repair_failed": float(bool(rep and not rep[1])),
        "repair_fixed": float(bool(rep and rep[1])),
    }


def select_assets(cfg: CivicConfig, portal: Portal, layer_id: str, ev: dict[str, np.ndarray], tick: int) -> list[int]:
    k = cfg.tracer.candidates_per_layer
    has = ev["_mass"] > 0
    by_mass = [int(a) for a in np.argsort(-ev["_mass"], kind="stable") if has[a]][:k]
    by_lift = [int(a) for a in np.argsort(-ev["_lift"], kind="stable") if has[a]][:k]

    def recently_cleared(a: int) -> bool:
        insp = portal.inspected.get((layer_id, a))
        rep = portal.repaired.get((layer_id, a))
        return bool((insp and not insp[1] and tick - insp[0] < cfg.tracer.reinspect_after_ticks) or (rep and rep[1]))

    by_score = [int(a) for a in np.argsort(-ev["score"], kind="stable") if has[a] and not recently_cleared(int(a))][:k]
    confirmed = [a for (l, a), (_, pos) in portal.inspected.items()
                 if l == layer_id and pos and not portal.repaired.get((l, a), (0, False))[1]]
    out: list[int] = []
    for a in by_mass + by_lift + by_score + sorted(confirmed, key=lambda a: -ev["score"][a])[:1]:
        if a not in out:
            out.append(a)
    return out


def observe(cfg: CivicConfig, city: CityMap, portal: Portal, department: str, tick: int) -> Observation:
    names = feature_names(cfg)
    idx = {n: i for i, n in enumerate(names)}
    kmax = max_candidates(cfg)
    feats = np.zeros((kmax, len(names)), dtype=np.float32)
    mask = np.zeros(kmax, dtype=bool)
    cands: list[Candidate] = []
    dept = next(d for d in cfg.departments if d.id == department)
    time_frac = tick / cfg.horizon_ticks

    def put(c: Candidate) -> None:
        row = len(cands)
        for k, v in c.features.items():
            feats[row, idx[k]] = v
        mask[row] = True
        cands.append(c)

    roots = cfg.root_cause_layers()
    for lid in dept.layers:
        ev = layer_evidence(cfg, city, portal, lid, tick)
        # symptom-only layers (road, traffic) get no `inspect`: there is no hidden fault to find, only symptoms to treat
        actions = ACTIONS if lid in roots else ("repair",)
        for a in select_assets(cfg, portal, lid, ev, tick):
            base = {k: float(ev[k][a]) for k in BASE_FEATURES if k in ev}
            base.update(_work_features(cfg, portal, lid, a, tick))
            base.update({f"layer_{lid}": 1.0, f"dept_{department}": 1.0, "time_frac": time_frac})
            for act in actions:
                put(Candidate(department, lid, a, act, {**base, f"act_{act}": 1.0}))
    put(Candidate(department, None, None, "wait", {"is_wait": 1.0, f"dept_{department}": 1.0, "time_frac": time_frac}))
    return Observation(department, feats, mask, cands)


def rank_hypotheses(cfg: CivicConfig, city: CityMap, portal: Portal, tick: int, top: int) -> list[dict]:
    """Deterministic ranking of unconfirmed hypotheses across all layers (labelled hypotheses, never causes)."""
    out = []
    for layer in cfg.layers:
        ev = layer_evidence(cfg, city, portal, layer.id, tick)
        for a in np.argsort(-ev["score"], kind="stable")[:top]:
            if ev["score"][a] <= cfg.tracer.min_score:
                continue
            asset = city.layers[layer.id].assets[int(a)]
            out.append({"layer": layer.id, "asset": int(a), "asset_name": asset.name, "department": layer.department,
                        "score": round(float(ev["score"][a]), 3), "coverage": round(float(ev["cov_primary"][a]), 3),
                        "lift": round(float(ev["_lift"][a]), 2), "root_first": bool(ev["root_first"][a])})
    return sorted(out, key=lambda h: -h["score"])[:top]
