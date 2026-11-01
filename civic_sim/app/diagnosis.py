"""Root-cause reports built from PUBLIC evidence only: the work log, complaints and the city map.

A root cause is reported as CONFIRMED only when a field inspection or repair found the fault. For each one
the report answers: where (asset, block, ward, coordinates), when it started (CUSUM change point of primary-symptom
complaints in the asset's zone; when residents' reports rose above background, not the true onset), why (the layer's mechanism),
and how it spread (the symptom chain, including complaints that reached the other department).
Everything else is an unconfirmed, ranked HYPOTHESIS. Must not import app.causes or app.env.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from app.config import CivicConfig
from app.portal import Portal
from app.tracer import rank_hypotheses
from app.world import CityMap


def estimate_onset(cfg: CivicConfig, portal: Portal, zone: np.ndarray, cats: list[int], upto: int) -> int | None:
    """CUSUM change point on the zone's primary-symptom complaints per tick.

    Background = median block's rate for these categories so far (most blocks are unaffected) x zone size.
    S_t = max(0, S_{t-1} + c_t - k * background); the first alarm (S_t >= h) dates the change to the tick after the
    last time S was zero. Returns None if the zone never rose clearly above background.
    """
    d = cfg.diagnosis
    counts = portal.counts[: upto + 1][:, :, cats].sum(axis=2)          # [T, N]
    per_block = counts.sum(axis=0) / (upto + 1)
    background = max(float(np.median(per_block)), d.background_floor) * float(zone.sum())
    series = counts[:, zone].sum(axis=1)
    s, last_zero = 0.0, 0
    for t, c in enumerate(series):
        s = max(0.0, s + float(c) - d.cusum_k * background)
        if s == 0.0:
            last_zero = t + 1
        elif s >= d.cusum_h:
            return min(last_zero, t)
    return None


def _evidence(cfg: CivicConfig, city: CityMap, portal: Portal, layer_id: str, asset: int, upto: int) -> dict:
    layer = city.layers[layer_id]
    zone = set(np.flatnonzero(layer.zone[asset]).tolist())
    ci = cfg.category_index()
    match = {ci[c] for c in layer.cfg.match}
    hits = [c for c in portal.complaints if c.tick <= upto and c.block in zone and c.category in match]
    by_cat: dict[str, dict] = {}
    for c in hits:
        cid = cfg.categories[c.category].id
        e = by_cat.setdefault(cid, {"category": cid, "label": cfg.categories[c.category].label, "count": 0,
                                    "first_tick": c.tick, "first_block": city.block_name(c.block),
                                    "routed_to": c.department, "unit": c.unit})
        e["count"] += 1
    chain = sorted(by_cat.values(), key=lambda e: (e["first_tick"], -e["count"]))
    for e in chain:
        e["first_seen"] = cfg.clock(e["first_tick"])
    primary = {ci[c] for c in layer.cfg.primary}
    onset = estimate_onset(cfg, portal, layer.zone[asset], sorted(primary), upto)
    prim_hits = [c for c in hits if c.category in primary and onset is not None and c.tick >= onset]
    first = min(prim_hits, key=lambda c: (c.tick, c.id)) if prim_hits else None
    return {"complaints": len(hits), "chain": chain, "first": first, "onset": onset,
            "sample_ids": [c.id for c in sorted(hits, key=lambda c: (c.tick, c.id))[:8]],
            "blocks": len({c.block for c in hits}),
            "wards": sorted({int(city.ward[c.block]) + 1 for c in hits})}


def root_cause_reports(cfg: CivicConfig, city: CityMap, portal: Portal, tick: int, hypotheses: int = 5) -> dict:
    roots = cfg.root_cause_layers()
    confirmed: dict[tuple[str, int], dict] = {}
    for w in portal.work:
        if w.layer not in roots or not w.found_fault:
            continue
        key = (w.layer, w.asset)
        rec = confirmed.setdefault(key, {"confirmed_tick": w.tick, "confirmed_by": f"{w.department}:{w.action}",
                                         "policy": w.policy, "fixed_tick": None})
        if w.action == "repair" and rec["fixed_tick"] is None:
            rec["fixed_tick"] = w.tick
    reports = []
    for (lid, a), rec in sorted(confirmed.items(), key=lambda kv: kv[1]["confirmed_tick"]):
        lc = cfg.layer(lid)
        asset = city.layers[lid].assets[a]
        ev = _evidence(cfg, city, portal, lid, a, rec["confirmed_tick"])
        other = [e for e in ev["chain"] if e["routed_to"] != lc.department]
        first = ev["first"]
        reports.append({
            "status": "FIXED" if rec["fixed_tick"] is not None else "CONFIRMED",
            "simulated": True,
            "where": {"layer": lid, "asset": asset.name, "block": city.block_name(asset.root),
                      "ward": int(city.ward[asset.root]) + 1,
                      "lat": round(float(city.lat[asset.root]), 6), "lon": round(float(city.lon[asset.root]), 6)},
            "responsible_department": lc.department,
            "why": lc.mechanism,
            "started": None if ev["onset"] is None else {
                "estimated": cfg.clock(ev["onset"]),
                "first_noticed_block": None if first is None else city.block_name(first.block),
                "method": "CUSUM change point on primary-symptom complaints in the affected zone vs the city background",
                "note": "when residents' complaints rose above background; the fault itself may have started earlier"},
            "symptom_chain": ev["chain"],
            "affected": {"complaints": ev["complaints"], "blocks": ev["blocks"], "wards": ev["wards"]},
            "cross_department": [f"{e['count']} '{e['label']}' complaints went to {e['unit']} ({e['routed_to']}); "
                                 f"their likely cause is this {lc.department} asset" for e in other],
            "confirmed": {"at": cfg.clock(rec["confirmed_tick"]), "by": rec["confirmed_by"], "policy": rec["policy"],
                          "method": lc.inspect_label if rec["confirmed_by"].endswith("inspect") else lc.repair_label},
            "fixed_at": None if rec["fixed_tick"] is None else cfg.clock(rec["fixed_tick"]),
            "evidence_ids": ev["sample_ids"],
            "zone": [city.block_name(b) for b in np.flatnonzero(city.layers[lid].zone[a])],
        })
    hyps = [h for h in rank_hypotheses(cfg, city, portal, tick, hypotheses * 2)
            if (h["layer"], h["asset"]) not in confirmed and h["layer"] in roots][:hypotheses]
    for h in hyps:
        layer = city.layers[h["layer"]]
        h["block"] = city.block_name(layer.assets[h["asset"]].root)
        h["zone"] = [city.block_name(b) for b in np.flatnonzero(layer.zone[h["asset"]])]
        h["status"] = "HYPOTHESIS"
        h["why_if_true"] = cfg.layer(h["layer"]).mechanism
        h["next_step"] = cfg.layer(h["layer"]).inspect_label
    return {"tick": tick, "clock": cfg.clock(tick), "simulated": True, "root_causes": reports, "hypotheses": hyps,
            "symptom_work": dict(Counter(f"{w.layer}:{w.action}" for w in portal.work if w.layer not in roots))}
