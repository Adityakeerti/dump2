"""Typed, strict configuration for the civic simulator. Unknown keys and dangling references are rejected."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Department = Literal["municipal", "police"]
LayerKind = Literal["tree", "route", "feeder", "radius", "node"]
POLICIES: tuple[str, ...] = ("rl", "tracer", "complaint_count", "random")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GridConfig(Strict):
    rows: int = Field(ge=2)
    cols: int = Field(ge=2)
    spacing_m: float = Field(gt=0)
    center_lat: float
    center_lon: float
    ward_block: int = Field(ge=1)
    arterial_rows: list[int] = []
    arterial_cols: list[int] = []


class CategoryConfig(Strict):
    id: str
    label: str
    department: Department
    unit: str
    noise_rate: float = Field(ge=0)
    severity: float = Field(gt=0)


class LayerConfig(Strict):
    id: str
    label: str
    department: Department
    kind: LayerKind
    tree_root: tuple[int, int] | None = None
    num_assets: int | None = Field(default=None, ge=1)
    radius: int = Field(default=0, ge=0)
    match: dict[str, float]
    primary: list[str]
    mechanism: str
    inspect_label: str
    repair_label: str
    inspect_miss_prob: float = Field(ge=0, lt=1)
    relief_categories: list[str] = []
    relief_hops: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def kind_params(self) -> "LayerConfig":
        if self.kind == "tree" and self.tree_root is None:
            raise ValueError(f"layer {self.id}: kind 'tree' needs tree_root")
        if self.kind in ("route", "feeder") and not self.num_assets:
            raise ValueError(f"layer {self.id}: kind '{self.kind}' needs num_assets")
        if self.kind == "radius" and self.radius < 1:
            raise ValueError(f"layer {self.id}: kind 'radius' needs radius >= 1")
        if not set(self.primary) <= set(self.match):
            raise ValueError(f"layer {self.id}: primary categories must appear in match")
        return self


class DepartmentConfig(Strict):
    id: Department
    label: str
    layers: list[str]
    hq_block: tuple[int, int]      # where crews start from (map only)
    hq_label: str


class EmissionConfig(Strict):
    category: str
    rate: float = Field(ge=0)
    hop_factor: float = Field(gt=0)
    min_hop: int = Field(default=0, ge=0)
    delay_ticks: int = Field(default=0, ge=0)
    spread_ticks_per_hop: int = Field(default=0, ge=0)


class CauseConfig(Strict):
    id: str
    layer: str
    weight: float = Field(gt=0)
    min_zone_blocks: int = Field(default=1, ge=1)
    pothole_spawn: float = Field(default=0.0, ge=0)
    pothole_hops: int = Field(default=0, ge=0)
    emissions: list[EmissionConfig]


class EpisodeConfig(Strict):
    min_causes: int = Field(ge=0)
    max_causes: int = Field(ge=0)
    onset_max_tick: int = Field(ge=0)
    relief_ticks: int = Field(ge=0)


class RoadsConfig(Strict):
    random_pothole_prob: float = Field(ge=0, le=1)
    pothole_intensity: float = Field(ge=0)
    traffic_per_pothole: float = Field(ge=0)
    max_potholes_per_block: int = Field(ge=1)


class PersonaConfig(Strict):
    id: str
    label: str
    weight: float = Field(gt=0)
    propensity: float = Field(ge=0)


class CitizensConfig(Strict):
    per_block: int = Field(ge=1)
    report_scale: float = Field(gt=0)
    ward_factor_range: tuple[float, float]
    personas: list[PersonaConfig]
    templates: dict[str, list[str]]


class RewardConfig(Strict):
    complaint_weight: float
    inspect_cost: float
    repair_cost: float
    false_repair_penalty: float
    identify_bonus: float
    fix_bonus: float


class TracerConfig(Strict):
    window_ticks: int = Field(ge=2)
    candidates_per_layer: int = Field(ge=1)
    count_norm: float = Field(gt=0)
    lift_norm: float = Field(gt=0)
    score_secondary_weight: float = Field(ge=0)
    score_root_first_bonus: float = Field(ge=0)
    min_score: float = Field(ge=0)
    reinspect_after_ticks: int = Field(ge=1)


class DiagnosisConfig(Strict):
    cusum_k: float = Field(gt=0)            # allowance, in multiples of the zone's background rate
    cusum_h: float = Field(gt=0)            # alarm threshold, in excess complaints
    background_floor: float = Field(gt=0)   # minimum background rate per block per tick


class RLConfig(Strict):
    algorithm: str
    hidden: list[int]
    learning_rate: float = Field(gt=0)
    gamma: float = Field(ge=0, lt=1)
    batch_size: int = Field(ge=1)
    buffer_capacity: int = Field(ge=1)
    target_update_interval: int = Field(ge=1)
    train_episodes: int = Field(ge=1)
    epsilon_start: float = Field(ge=0, le=1)
    epsilon_end: float = Field(ge=0, le=1)
    epsilon_decay_episodes: int = Field(ge=1)
    huber_delta: float = Field(gt=0)
    grad_clip: float = Field(gt=0)
    warmup_transitions: int = Field(ge=0)
    checkpoint_path: str
    demo_episodes: int = Field(default=0, ge=0)


class EvaluationConfig(Strict):
    episodes_per_scenario: int = Field(ge=1)
    seed_offset: int
    policies: list[str]
    report_path: str
    json_path: str


class BridgeConfig(Strict):
    enabled: bool
    url: str
    max_per_tick: int = Field(ge=0)


class ReasoningConfig(Strict):
    base_url: str
    model: str
    fallback_model: str
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    temperature: float = 0.2
    max_tokens: int = Field(default=4096, ge=1)
    timeout_sec: float = Field(default=60, gt=0)


class LiveConfig(Strict):
    port: int
    tick_interval_sec: float = Field(gt=0)
    policy: str
    llm_base_url: str
    llm_model: str
    llm_timeout_sec: float = Field(gt=0)
    llm_max_per_tick: int = Field(ge=0)
    log_size: int = Field(ge=1)
    root_cause: ReasoningConfig
    portal_bridge: BridgeConfig


class CivicConfig(Strict):
    seed: int
    horizon_ticks: int = Field(ge=2)
    tick_hours: int = Field(ge=1)
    clock_start_day: int = 1
    grid: GridConfig
    categories: list[CategoryConfig]
    layers: list[LayerConfig]
    departments: list[DepartmentConfig]
    causes: list[CauseConfig]
    episode: EpisodeConfig
    roads: RoadsConfig
    citizens: CitizensConfig
    reward: RewardConfig
    tracer: TracerConfig
    diagnosis: DiagnosisConfig
    rl: RLConfig
    evaluation: EvaluationConfig
    live: LiveConfig

    @model_validator(mode="after")
    def cross_refs(self) -> "CivicConfig":
        cats = {c.id for c in self.categories}
        layers = {l.id for l in self.layers}
        if len(cats) != len(self.categories) or len(layers) != len(self.layers):
            raise ValueError("category and layer ids must be unique")
        if "pothole" not in cats or "traffic_jam" not in cats:
            raise ValueError("categories must include 'pothole' and 'traffic_jam' (road model)")
        for l in self.layers:
            unknown = (set(l.match) | set(l.relief_categories)) - cats
            if unknown:
                raise ValueError(f"layer {l.id}: unknown categories {sorted(unknown)}")
            if l.tree_root and not (0 <= l.tree_root[0] < self.grid.rows and 0 <= l.tree_root[1] < self.grid.cols):
                raise ValueError(f"layer {l.id}: tree_root outside the grid")
        owned: list[str] = []
        for d in self.departments:
            if set(d.layers) - layers:
                raise ValueError(f"department {d.id}: unknown layers {sorted(set(d.layers) - layers)}")
            owned += d.layers
            for lid in d.layers:
                if next(l for l in self.layers if l.id == lid).department != d.id:
                    raise ValueError(f"layer {lid} is listed under department {d.id} but declares another")
        if sorted(owned) != sorted(layers):
            raise ValueError("every layer must belong to exactly one department")
        for c in self.causes:
            if c.layer not in layers:
                raise ValueError(f"cause {c.id}: unknown layer {c.layer}")
            if {e.category for e in c.emissions} - cats:
                raise ValueError(f"cause {c.id}: unknown emission category")
        if set(self.citizens.templates) != cats:
            raise ValueError("citizens.templates must have an entry for every category")
        if self.episode.min_causes > self.episode.max_causes:
            raise ValueError("episode.min_causes > max_causes")
        if self.episode.onset_max_tick >= self.horizon_ticks:
            raise ValueError("episode.onset_max_tick must be inside the horizon")
        if set(self.evaluation.policies) - set(POLICIES) or self.live.policy not in POLICIES:
            raise ValueError(f"policies must be among {POLICIES}")
        for r in self.grid.arterial_rows:
            if not 0 <= r < self.grid.rows:
                raise ValueError("arterial row outside grid")
        for c in self.grid.arterial_cols:
            if not 0 <= c < self.grid.cols:
                raise ValueError("arterial col outside grid")
        return self

    # convenience lookups
    def category_index(self) -> dict[str, int]:
        return {c.id: i for i, c in enumerate(self.categories)}

    def layer(self, layer_id: str) -> LayerConfig:
        return next(l for l in self.layers if l.id == layer_id)

    def root_cause_layers(self) -> set[str]:
        """Layers whose assets can be a root cause (public mechanism table); the rest only carry symptoms."""
        return {c.layer for c in self.causes}

    def clock(self, tick: int) -> str:
        hours = tick * self.tick_hours
        return f"Day {self.clock_start_day + hours // 24} {hours % 24:02d}:00"

    def config_hash(self) -> str:
        """Hash of everything that affects simulation, training or evaluation (live-service settings excluded)."""
        data = self.model_dump(mode="json", exclude={"live"})
        for d in data["departments"]:
            d.pop("hq_block"), d.pop("hq_label")
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


BASE = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> CivicConfig:
    with open(path or BASE / "config.yaml", "r", encoding="utf-8") as f:
        return CivicConfig.model_validate(yaml.safe_load(f))
