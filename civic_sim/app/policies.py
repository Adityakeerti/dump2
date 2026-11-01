"""Department policies: the learned RL policy and three baselines, all choosing from the same candidates.

* complaint_count: today's practice. Send a crew to repair whatever has the most complaints on its own block
  (symptom chasing). Never inspects.
* tracer: deterministic root-cause ranking. Repair anything an inspection confirmed; otherwise take the
  highest-scoring of (inspect a root-cause asset not recently cleared, treat a symptom-only block not recently
  treated); otherwise wait.
* random: uniform over valid candidates.
* rl: argmax of the trained candidate-scoring Q network.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from app.config import CivicConfig
from app.dqn import CandidateDQN
from app.tracer import Observation

Policy = Callable[[Observation], int]


def _wait(obs: Observation) -> int:
    return next(i for i, c in enumerate(obs.candidates) if c.action == "wait")


def complaint_count_policy(obs: Observation) -> int:
    best, best_v = _wait(obs), 0.0
    for i, c in enumerate(obs.candidates):
        if c.action == "repair" and c.features.get("local", 0.0) > best_v:
            best, best_v = i, c.features["local"]
    return best


def make_tracer_policy(cfg: CivicConfig) -> Policy:
    tc = cfg.tracer
    recheck = tc.reinspect_after_ticks / tc.window_ticks            # since_insp is in window units
    symptom_layers = {l.id for l in cfg.layers} - cfg.root_cause_layers()

    def policy(obs: Observation) -> int:
        cands = obs.candidates
        confirmed = [i for i, c in enumerate(cands) if c.action == "repair" and c.features.get("insp_pos")
                     and not c.features.get("repair_fixed")]
        if confirmed:
            return max(confirmed, key=lambda i: cands[i].features["score"])
        options = [i for i, c in enumerate(cands) if c.action == "inspect" and c.features["score"] > tc.min_score
                   and not c.features.get("repair_fixed")
                   and not (c.features.get("insp_neg") and c.features["since_insp"] < recheck)]
        options += [i for i, c in enumerate(cands) if c.action == "repair" and c.layer in symptom_layers
                    and c.features["score"] > tc.min_score and not c.features.get("repaired_recent")]
        if options:
            return max(options, key=lambda i: cands[i].features["score"])
        return _wait(obs)

    return policy


def make_random_policy(seed: int) -> Policy:
    rng = np.random.default_rng(seed)

    def policy(obs: Observation) -> int:
        return int(rng.choice(np.flatnonzero(obs.mask)))

    return policy


def make_rl_policy(agent: CandidateDQN) -> Policy:
    def policy(obs: Observation) -> int:
        return agent.act(obs.feats, obs.mask, epsilon=0.0)

    return policy


def build_policy(name: str, cfg: CivicConfig, agent: CandidateDQN | None, seed: int) -> Policy:
    if name == "rl":
        if agent is None:
            raise ValueError("rl policy needs a trained agent (run python -m app.train)")
        return make_rl_policy(agent)
    if name == "tracer":
        return make_tracer_policy(cfg)
    if name == "complaint_count":
        return complaint_count_policy
    if name == "random":
        return make_random_policy(seed)
    raise ValueError(f"unknown policy {name}")
