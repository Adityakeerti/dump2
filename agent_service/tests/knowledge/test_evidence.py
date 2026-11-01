from datetime import datetime, timedelta, timezone

from src.knowledge.evidence import EvidenceHit, validate_evidence


def test_threshold_boundary_is_accepted(hit):
    result = validate_evidence([hit], min_similarity=0.8, city_id="dehradun")
    assert result.abstain is False
    assert len(result.usable_hits) == 1


def test_below_threshold_abstains(hit):
    assert validate_evidence([hit], min_similarity=0.81, city_id="dehradun").abstain


def test_expired_document_is_excluded(hit):
    expired = EvidenceHit(
        **{**hit.__dict__, "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    assert validate_evidence([expired], min_similarity=0.1, city_id="dehradun").abstain


def test_jurisdiction_mismatch_is_excluded(hit):
    other = EvidenceHit(**{**hit.__dict__, "jurisdiction": "jaipur"})
    assert validate_evidence([other], min_similarity=0.1, city_id="dehradun").abstain


def test_unverified_document_is_excluded(hit):
    unverified = EvidenceHit(**{**hit.__dict__, "verified": False})
    assert validate_evidence([unverified], min_similarity=0.1, city_id="dehradun").abstain


def test_empty_hits_abstain():
    assert validate_evidence([], min_similarity=0.1, city_id="dehradun").abstain


def test_low_score_hit_cannot_piggyback_on_high_hit(hit):
    from dataclasses import replace

    low = replace(hit, chunk_id="low", vector_score=0.1, fused_score=10)
    result = validate_evidence([hit, low], min_similarity=0.7, city_id="dehradun")
    assert [h.chunk_id for h in result.usable_hits] == [hit.chunk_id]


def test_unknown_city_does_not_allow_local_documents(hit):
    assert validate_evidence([hit], min_similarity=0.1, city_id=None).abstain


def test_staleness_uses_fetch_time_not_imminent_expiry(hit):
    from dataclasses import replace

    now = datetime.now(timezone.utc)
    fresh = replace(hit, fetched_at=now, expires_at=now + timedelta(days=1))
    assert not validate_evidence([fresh], min_similarity=0.1, city_id="dehradun", now=now).flags
    stale = replace(hit, fetched_at=now - timedelta(days=100))
    assert validate_evidence([stale], min_similarity=0.1, city_id="dehradun", now=now).flags == [
        "stale"
    ]
