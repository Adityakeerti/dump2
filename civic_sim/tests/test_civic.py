"""Civic simulator: config validation, world construction, env dynamics, ground-truth isolation, DQN, agents."""

import ast
import asyncio
import copy
import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from app.config import CivicConfig, load_config
from app.diagnosis import root_cause_reports
from app.dqn import MLP, CandidateDQN
from app.env import CivicEnv
from app.evaluate import run_episode
from app.policies import build_policy, make_tracer_policy
from app.tracer import feature_names, max_candidates
from app.world import build_city

ROOT = Path(__file__).resolve().parent.parent
CFG = load_config()
RAW = yaml.safe_load((ROOT / "config.yaml").read_text())


def cfg_with(**edits) -> CivicConfig:
    raw = copy.deepcopy(RAW)
    for path, value in edits.items():
        node = raw
        keys = path.split("__")
        for k in keys[:-1]:
            node = node[int(k)] if k.isdigit() else node[k]
        node[keys[-1]] = value
    return CivicConfig.model_validate(raw)


# ---------------------------------------------------------------- config
def test_config_loads_and_hash_is_stable():
    assert CFG.config_hash() == load_config().config_hash()
    assert cfg_with(seed=CFG.seed + 1).config_hash() != CFG.config_hash()


@pytest.mark.parametrize("edits", [
    {"surprise_key": 1},
    {"layers__0__match": {"not_a_category": 1.0}},
    {"causes__0__layer": "no_such_layer"},
    {"episode__onset_max_tick": 10_000},
    {"departments__1__layers": ["crime"]},              # traffic layer left without a department
])
def test_invalid_configs_rejected(edits):
    with pytest.raises(ValidationError):
        cfg_with(**edits)


# ---------------------------------------------------------------- world
def test_city_is_deterministic_and_trees_span():
    a, b = build_city(CFG), build_city(CFG)
    for lid, layer in a.layers.items():
        assert np.array_equal(layer.hops, b.layers[lid].hops)
        if layer.parent is not None:
            assert (layer.parent < 0).sum() == 1                        # exactly one root
            root = int(np.flatnonzero(layer.parent < 0)[0])
            assert layer.zone[root].all()                               # the root's subtree is the whole city
    for lid in ("waste", "streetlight"):
        zone = a.layers[lid].zone
        assert (zone.sum(axis=0) == 1).all()                            # partitions cover each block exactly once


# ---------------------------------------------------------------- env
def run(policy: str, seed: int, scenario=None) -> dict:
    env = CivicEnv(CFG)
    pol = {d: build_policy(policy, CFG, None, seed + i) for i, d in enumerate(env.departments)}
    return run_episode(env, pol, seed, scenario, policy)


def test_same_seed_same_episode():
    assert run("tracer", 3) == run("tracer", 3)
    assert run("random", 3) == run("random", 3)


def test_control_scenario_has_no_causes():
    env = CivicEnv(CFG)
    env.reset(seed=1, scenario=[])
    assert env.ground_truth() == []


def test_sewer_symptoms_appear_upstream_not_at_blockage():
    env = CivicEnv(CFG)
    env.reset(seed=2, scenario=["sewer_blockage"])
    hc = env._causes[0]
    env.tick = hc.onset_tick + CFG.horizon_ticks // 2
    inten = env.intensity() - np.array([c.noise_rate for c in CFG.categories])
    d = CFG.category_index()["drainage"]
    hops = env.city.layers["sewer"].hops[hc.asset]
    assert inten[hc.root_block, d] == pytest.approx(0.0)              # min_hop 1: nothing at the blocked segment
    assert inten[(hops == 1), d].min() > 0                             # first upstream blocks overflow
    assert (inten[hops < 0, d] == 0).all()                             # nothing outside the zone


def test_repairing_the_true_fault_stops_its_symptoms_and_wrong_repair_is_penalised():
    env = CivicEnv(CFG)
    env.reset(seed=4, scenario=["missed_waste_route"])
    hc = env._causes[0]
    env.tick = hc.onset_tick
    from app.tracer import Candidate
    wrong = (hc.asset + 1) % len(env.city.layers["waste"].assets)
    r_wrong, out_wrong = env._execute(Candidate("municipal", "waste", wrong, "repair", {}), "test")
    assert not out_wrong["found_fault"] and env.stats.false_repairs == 1
    r_right, out_right = env._execute(Candidate("municipal", "waste", hc.asset, "repair", {}), "test")
    assert out_right["found_fault"] and r_right > r_wrong
    env.tick += 1
    from app.causes import emission_intensity
    assert emission_intensity(CFG, env.city, env._causes, env.tick).sum() == 0


# ---------------------------------------------------------------- isolation
PUBLIC_MODULES = ["tracer", "policies", "diagnosis", "dqn", "portal", "world", "citizens", "agents"]


@pytest.mark.parametrize("module", PUBLIC_MODULES)
def test_public_modules_never_import_hidden_state(module):
    tree = ast.parse((ROOT / "app" / f"{module}.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    assert not imported & {"app.causes", "app.env"}, f"{module} imports hidden state"


def test_observation_depends_only_on_portal_evidence():
    """Two worlds with different hidden causes but the same complaint log must give identical features."""
    a, b = CivicEnv(CFG), CivicEnv(CFG)
    a.reset(seed=5, scenario=["water_main_leak"])
    b.reset(seed=6, scenario=["crime_hotspot"])
    b.portal = copy.deepcopy(a.portal)
    b.tick = a.tick
    oa, ob = a.observe(), b.observe()
    for d in a.departments:
        assert np.array_equal(oa[d].feats, ob[d].feats)


def test_diagnosis_reports_only_confirmed_and_never_cause_type():
    env = CivicEnv(CFG)
    pol = {d: make_tracer_policy(CFG) for d in env.departments}
    obs = env.reset(seed=8, scenario=["streetlight_feeder_fault"])
    while not env.done:
        obs, *_ = env.step({d: pol[d](obs[d]) for d in env.departments}, policy="tracer")
    rep = root_cause_reports(CFG, env.city, env.portal, env.tick)
    blob = json.dumps(rep)
    assert "streetlight_feeder_fault" not in blob                       # cause-type id lives only in ground truth
    for r in rep["root_causes"]:
        assert r["status"] in ("CONFIRMED", "FIXED") and r["simulated"]
        assert r["where"]["block"] and r["why"] and r["symptom_chain"]
    for h in rep["hypotheses"]:
        assert h["status"] == "HYPOTHESIS"
    truth = env.ground_truth()[0]
    if truth["identified_tick"] is not None:
        assert any(r["where"]["asset"] == truth["asset_name"] for r in rep["root_causes"])


# ---------------------------------------------------------------- DQN
def test_mlp_gradient_matches_finite_difference():
    rng = np.random.default_rng(0)
    net = MLP([5, 7, 1], rng, lr=1e-3)
    x = rng.normal(size=(4, 5))
    out = net.forward(x, keep=True)
    grads = net.backward(np.ones_like(out))                             # d(sum of outputs)/d(params)
    eps = 1e-6
    for p, g in zip(net.params(), grads):
        idx = tuple(rng.integers(s) for s in p.shape)
        old = p[idx]
        p[idx] = old + eps
        up = net.forward(x).sum()
        p[idx] = old - eps
        down = net.forward(x).sum()
        p[idx] = old
        assert (up - down) / (2 * eps) == pytest.approx(g[idx], rel=1e-4, abs=1e-6)


def test_tiny_training_run_saves_and_reloads_identical_actions(tmp_path):
    from app.train import train
    agent, hist = train(CFG, episodes=3, verbose=False)
    assert len(hist) == 3 and agent.buffer.n > 0
    meta = {"config_hash": CFG.config_hash()}
    path = agent.save(tmp_path / "ckpt.npz", meta)
    other = CandidateDQN(CFG.rl, len(feature_names(CFG)), max_candidates(CFG), seed=999)
    assert other.load(path) == meta
    obs = CivicEnv(CFG).reset(seed=77)
    for d, o in obs.items():
        assert agent.act(o.feats, o.mask, 0.0) == other.act(o.feats, o.mask, 0.0)


# ---------------------------------------------------------------- citizen agent (LangGraph)
def run_citizen(reply):
    from app.agents import build_citizen_graph

    async def llm(_):
        if isinstance(reply, Exception):
            raise reply
        return reply

    g = build_citizen_graph(llm)
    state = {"citizen": {"persona": "shopkeeper"}, "incident": {"label": "Pothole", "template": "Big pothole here."}, "steps": []}
    return asyncio.run(g.ainvoke(state))


def test_citizen_agent_uses_llm_text_when_valid():
    out = run_citizen(json.dumps({"title": "Pothole outside my shop", "description": "There is a deep pothole outside my shop and scooters keep slipping."}))
    assert out["written_by"] == "llm"


@pytest.mark.parametrize("reply", [
    json.dumps({"title": "Pothole", "description": "There are 3 potholes since 12 May near house 44."}),   # invented numbers
    "not json",
    ConnectionError("llama-server down"),
])
def test_citizen_agent_falls_back_to_template(reply):
    out = run_citizen(reply)
    assert out["written_by"] == "template" and out["text"]["description"] == "Big pothole here."


def test_symptom_layers_offer_no_inspection():
    """Road and traffic carry no hidden fault: inspecting them would be a costed no-op the policy could exploit."""
    obs = CivicEnv(CFG).reset(seed=12, scenario=["water_main_leak"])
    roots = CFG.root_cause_layers()
    for o in obs.values():
        for c in o.candidates:
            if c.layer is not None and c.layer not in roots:
                assert c.action == "repair"


def test_onset_estimate_tracks_true_start():
    """The CUSUM start estimate should land near the planted onset for most identified causes (tolerance: 2 ticks)."""
    from app.evaluate import onset_errors
    env = CivicEnv(CFG)
    errs = []
    for i in range(12):
        run_episode(env, {d: make_tracer_policy(CFG) for d in env.departments}, 500 + i, ["sewer_blockage"], "tracer")
        errs += onset_errors(env)
    assert len(errs) >= 8
    assert np.median(np.abs(errs)) <= 2
