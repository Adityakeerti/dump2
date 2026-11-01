"""Train the department policy offline: python -m app.train [--episodes N] [--config PATH]

Each episode plants 1-2 random root causes on a fresh seed. Both departments act every tick and share the
team reward. The first `rl.demo_episodes` episodes follow the tracer baseline to seed the replay buffer
with successful diagnoses (off-policy learning still applies). Nothing trains live.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from app.config import BASE, CivicConfig, load_config
from app.dqn import CandidateDQN
from app.env import CivicEnv
from app.policies import make_tracer_policy
from app.tracer import feature_names, max_candidates


def epsilon_at(cfg: CivicConfig, episode: int) -> float:
    r = cfg.rl
    k = max(0, episode - r.demo_episodes)
    frac = min(1.0, k / r.epsilon_decay_episodes)
    return r.epsilon_start + frac * (r.epsilon_end - r.epsilon_start)


def train(cfg: CivicConfig, episodes: int | None = None, log_every: int = 50, verbose: bool = True):
    episodes = episodes or cfg.rl.train_episodes
    env = CivicEnv(cfg)
    names = feature_names(cfg)
    agent = CandidateDQN(cfg.rl, len(names), max_candidates(cfg), cfg.seed)
    teacher = make_tracer_policy(cfg)
    history: list[dict] = []
    t0 = time.perf_counter()
    for ep in range(episodes):
        obs = env.reset(seed=cfg.seed + ep)
        demo = ep < cfg.rl.demo_episodes
        eps = epsilon_at(cfg, ep)
        losses = []
        while not env.done:
            if demo:
                choices = {d: teacher(obs[d]) for d in env.departments}
            else:
                choices = {d: agent.act(obs[d].feats, obs[d].mask, eps) for d in env.departments}
            nxt, reward, done, _ = env.step(choices, policy="demo" if demo else "rl-train")
            for d in env.departments:
                agent.buffer.push(obs[d].feats[choices[d]], reward, nxt[d].feats, nxt[d].mask, done)
            losses.append(agent.update())
            obs = nxt
        m = env.episode_metrics()
        m.update({"episode": ep, "epsilon": round(eps, 3), "demo": demo, "loss": round(float(np.mean(losses)), 4)})
        history.append(m)
        if verbose and (ep + 1) % log_every == 0:
            blk = history[-log_every:]
            ident = sum(h["identified"] for h in blk) / max(1, sum(h["causes"] for h in blk))
            print(f"ep {ep + 1:4d}  eps {eps:.2f}  reward {np.mean([h['reward'] for h in blk]):8.2f}  "
                  f"identified {ident:.2f}  complaints {np.mean([h['complaints'] for h in blk]):6.1f}  "
                  f"false_repairs {np.mean([h['false_repairs'] for h in blk]):4.1f}  "
                  f"loss {np.mean([h['loss'] for h in blk]):.4f}  {time.perf_counter() - t0:6.1f}s", flush=True)
    return agent, history


def curve(history: list[dict], block: int) -> list[dict]:
    out = []
    for i in range(0, len(history), block):
        blk = history[i:i + block]
        out.append({"episodes": f"{i + 1}-{i + len(blk)}", "demo": all(h["demo"] for h in blk),
                    "mean_reward": round(float(np.mean([h["reward"] for h in blk])), 2),
                    "identified_rate": round(sum(h["identified"] for h in blk) / max(1, sum(h["causes"] for h in blk)), 3),
                    "mean_complaints": round(float(np.mean([h["complaints"] for h in blk])), 1)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--episodes", type=int, default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    agent, history = train(cfg, args.episodes)
    meta = {
        "algorithm": cfg.rl.algorithm, "config_hash": cfg.config_hash(), "seed": cfg.seed,
        "episodes": len(history), "train_seeds": [cfg.seed, cfg.seed + len(history) - 1],
        "feature_names": feature_names(cfg), "updates": agent.updates, "curve": curve(history, 50),
        "simulated": True,
    }
    path = agent.save(BASE / cfg.rl.checkpoint_path, meta)
    print(f"saved {path}")


if __name__ == "__main__":
    main()
