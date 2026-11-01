"""Complaint portal: the only channel through which the departments learn about the city.

Intake routing mirrors complaint_module's classifier taxonomy (category -> department unit). The portal
also keeps the public work log: inspections and repairs with their outcomes as the field crew reported them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.config import CivicConfig


@dataclass
class Complaint:
    id: str
    tick: int
    citizen: int
    block: int
    category: int
    department: str
    unit: str
    text: str
    status: str = "OPEN"          # OPEN -> ADDRESSED (a crew acted on an asset covering this block and category)
    text_by: str = "template"     # template | llm (live mode rewrites a few texts with the citizen agent)


@dataclass
class WorkOrder:
    tick: int
    department: str
    layer: str
    asset: int
    action: str                   # inspect | repair
    found_fault: bool             # what the crew reported
    policy: str


@dataclass
class Portal:
    cfg: CivicConfig
    n_blocks: int
    horizon: int
    complaints: list[Complaint] = field(default_factory=list)
    work: list[WorkOrder] = field(default_factory=list)

    def __post_init__(self) -> None:
        c = len(self.cfg.categories)
        self.counts = np.zeros((self.horizon + 1, self.n_blocks, c), dtype=np.float32)
        self.first_tick = np.full((self.n_blocks, c), -1, dtype=int)
        self.route = {cat.id: (cat.department, cat.unit) for cat in self.cfg.categories}
        self.cat_ids = [cat.id for cat in self.cfg.categories]
        # (layer, asset) -> latest inspection/repair outcome
        self.inspected: dict[tuple[str, int], tuple[int, bool]] = {}
        self.repaired: dict[tuple[str, int], tuple[int, bool]] = {}

    def file(self, tick: int, citizen: int, block: int, category: int, text: str) -> Complaint:
        dept, unit = self.route[self.cat_ids[category]]
        c = Complaint(f"C{tick:03d}-{len(self.complaints):05d}", tick, citizen, block, category, dept, unit, text)
        self.complaints.append(c)
        self.counts[tick, block, category] += 1
        if self.first_tick[block, category] < 0:
            self.first_tick[block, category] = tick
        return c

    def log(self, order: WorkOrder) -> None:
        self.work.append(order)
        key = (order.layer, order.asset)
        (self.inspected if order.action == "inspect" else self.repaired)[key] = (order.tick, order.found_fault)

    def address(self, blocks: np.ndarray, categories: list[int]) -> int:
        """Mark open complaints on these blocks/categories as addressed; returns how many."""
        bs, cs, n = set(int(b) for b in blocks), set(categories), 0
        for c in self.complaints:
            if c.status == "OPEN" and c.block in bs and c.category in cs:
                c.status = "ADDRESSED"
                n += 1
        return n

    def window(self, tick: int, ticks: int) -> np.ndarray:
        lo = max(0, tick - ticks + 1)
        return self.counts[lo:tick + 1].sum(axis=0)

    def queue(self, department: str) -> list[Complaint]:
        return [c for c in self.complaints if c.department == department and c.status == "OPEN"]
