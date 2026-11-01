from dataclasses import dataclass, replace
from datetime import datetime, timezone


@dataclass(frozen=True)
class EvidenceHit:
    chunk_id: str
    doc_id: str
    tenant_id: str
    text: str
    vector_score: float
    fused_score: float
    verified: bool
    jurisdiction: str
    expires_at: datetime | None
    stale: bool = False
    fetched_at: datetime | None = None


@dataclass(frozen=True)
class EvidenceResult:
    usable_hits: list[EvidenceHit]
    abstain: bool
    flags: list[str]


def validate_evidence(
    hits: list[EvidenceHit],
    *,
    min_similarity: float,
    city_id: str | None,
    now: datetime | None = None,
    freshness_days: int = 90,
) -> EvidenceResult:
    now = now or datetime.now(timezone.utc)
    flags: set[str] = set()
    surviving: list[EvidenceHit] = []
    for hit in hits:
        expiry = hit.expires_at
        if not hit.verified:
            continue
        if expiry and expiry <= now:
            continue
        if hit.jurisdiction != "national" and hit.jurisdiction != city_id:
            continue
        if hit.fetched_at and (now - hit.fetched_at).days >= freshness_days:
            flags.add("stale")
            hit = replace(hit, stale=True)
        if hit.vector_score < min_similarity:
            continue
        surviving.append(hit)
    if not surviving or max(hit.vector_score for hit in surviving) < min_similarity:
        return EvidenceResult([], True, sorted(flags))
    return EvidenceResult(
        sorted(surviving, key=lambda item: item.fused_score, reverse=True)[:4], False, sorted(flags)
    )
