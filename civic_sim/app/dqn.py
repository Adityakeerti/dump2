"""Double DQN over candidate sets, in NumPy (no torch in the SmartCity venv).

Q(s, a) = MLP(features of candidate a). One network is shared by both departments (a department one-hot
is part of the features), the same weight-sharing idea as the corridor DQN sharing one network across
junctions. Targets: r + gamma * Q_target(s', argmax_a' Q_online(s', a')) over the valid candidates of s'.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.config import RLConfig


class MLP:
    """ReLU MLP with a scalar output, manual backprop and Adam."""

    def __init__(self, sizes: list[int], rng: np.random.Generator, lr: float) -> None:
        self.W = [rng.normal(0, np.sqrt(2.0 / a), (a, b)).astype(np.float64) for a, b in zip(sizes[:-1], sizes[1:])]
        self.b = [np.zeros(b) for b in sizes[1:]]
        self.lr = lr
        self.m = [np.zeros_like(p) for p in self.params()]
        self.v = [np.zeros_like(p) for p in self.params()]
        self.t = 0

    def params(self) -> list[np.ndarray]:
        return self.W + self.b

    def forward(self, x: np.ndarray, keep: bool = False) -> np.ndarray:
        acts = [x]
        h = x
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            h = h @ W + b
            if i < len(self.W) - 1:
                h = np.maximum(h, 0.0)
            acts.append(h)
        if keep:
            self._acts = acts
        return h[..., 0]

    def backward(self, grad_out: np.ndarray) -> list[np.ndarray]:
        """grad_out: dLoss/dOutput [B]. Returns grads in params() order."""
        acts = self._acts
        g = grad_out[:, None]
        gW, gb = [None] * len(self.W), [None] * len(self.b)
        for i in reversed(range(len(self.W))):
            gW[i] = acts[i].T @ g
            gb[i] = g.sum(axis=0)
            if i > 0:
                g = (g @ self.W[i].T) * (acts[i] > 0)
        return gW + gb

    def adam(self, grads: list[np.ndarray], clip: float) -> None:
        norm = np.sqrt(sum(float((g ** 2).sum()) for g in grads))
        scale = min(1.0, clip / (norm + 1e-12))
        self.t += 1
        b1, b2, eps = 0.9, 0.999, 1e-8
        for p, g, m, v in zip(self.params(), grads, self.m, self.v):
            g = g * scale
            m *= b1
            m += (1 - b1) * g
            v *= b2
            v += (1 - b2) * g * g
            mh = m / (1 - b1 ** self.t)
            vh = v / (1 - b2 ** self.t)
            p -= self.lr * mh / (np.sqrt(vh) + eps)

    def copy_from(self, other: "MLP") -> None:
        self.W = [w.copy() for w in other.W]
        self.b = [b.copy() for b in other.b]

    def state(self) -> dict[str, np.ndarray]:
        return {**{f"W{i}": w for i, w in enumerate(self.W)}, **{f"b{i}": b for i, b in enumerate(self.b)}}

    def load(self, state: dict[str, np.ndarray]) -> None:
        self.W = [state[f"W{i}"] for i in range(len(self.W))]
        self.b = [state[f"b{i}"] for i in range(len(self.b))]


class Replay:
    def __init__(self, capacity: int, k: int, d: int) -> None:
        self.x = np.zeros((capacity, d), dtype=np.float32)
        self.r = np.zeros(capacity, dtype=np.float32)
        self.nx = np.zeros((capacity, k, d), dtype=np.float32)
        self.nm = np.zeros((capacity, k), dtype=bool)
        self.done = np.zeros(capacity, dtype=np.float32)
        self.cap, self.n, self.pos = capacity, 0, 0

    def push(self, x, r, nx, nm, done) -> None:
        i = self.pos
        self.x[i], self.r[i], self.nx[i], self.nm[i], self.done[i] = x, r, nx, nm, float(done)
        self.pos = (self.pos + 1) % self.cap
        self.n = min(self.n + 1, self.cap)

    def sample(self, rng: np.random.Generator, batch: int):
        idx = rng.choice(self.n, size=batch, replace=False)
        return self.x[idx], self.r[idx], self.nx[idx], self.nm[idx], self.done[idx]


class CandidateDQN:
    def __init__(self, cfg: RLConfig, feat_dim: int, k: int, seed: int) -> None:
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        sizes = [feat_dim, *cfg.hidden, 1]
        self.online = MLP(sizes, self.rng, cfg.learning_rate)
        self.target = MLP(sizes, self.rng, cfg.learning_rate)
        self.target.copy_from(self.online)
        self.buffer = Replay(cfg.buffer_capacity, k, feat_dim)
        self.updates = 0
        self.feat_dim, self.k = feat_dim, k

    def q(self, feats: np.ndarray, mask: np.ndarray) -> np.ndarray:
        q = self.online.forward(feats.astype(np.float64))
        return np.where(mask, q, -np.inf)

    def act(self, feats: np.ndarray, mask: np.ndarray, epsilon: float) -> int:
        valid = np.flatnonzero(mask)
        if self.rng.random() < epsilon:
            return int(self.rng.choice(valid))
        return int(np.argmax(self.q(feats, mask)))

    def update(self) -> float:
        c = self.cfg
        if self.buffer.n < max(c.batch_size, c.warmup_transitions):
            return 0.0
        x, r, nx, nm, done = self.buffer.sample(self.rng, c.batch_size)
        B, K, D = nx.shape
        flat = nx.reshape(B * K, D).astype(np.float64)
        q_on = np.where(nm, self.online.forward(flat).reshape(B, K), -np.inf)
        a_star = np.argmax(q_on, axis=1)
        q_tg = self.target.forward(flat).reshape(B, K)[np.arange(B), a_star]
        y = r + (1.0 - done) * c.gamma * q_tg
        pred = self.online.forward(x.astype(np.float64), keep=True)
        err = pred - y
        grad = np.clip(err, -c.huber_delta, c.huber_delta) / B          # Huber loss gradient
        self.online.adam(self.online.backward(grad), c.grad_clip)
        self.updates += 1
        if self.updates % c.target_update_interval == 0:
            self.target.copy_from(self.online)
        a = np.abs(err)
        return float(np.mean(np.where(a <= c.huber_delta, 0.5 * err ** 2, c.huber_delta * (a - 0.5 * c.huber_delta))))

    def save(self, path: str | Path, meta: dict) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez(p, **self.online.state(), meta=np.array(json.dumps(meta)))
        return p

    def load(self, path: str | Path) -> dict:
        data = np.load(path, allow_pickle=False)
        self.online.load({k: data[k] for k in data.files if k != "meta"})
        self.target.copy_from(self.online)
        return json.loads(str(data["meta"]))
