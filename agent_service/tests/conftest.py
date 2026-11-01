import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["DEMO_MODE"] = "1"
os.environ["USE_SENTENCE_TRANSFORMER"] = "0"
os.environ["JWT_SECRET"] = "test-secret-only-not-a-production-key-12345678"
# Deterministic tests: replies use the template fallbacks unless a test enables composition with a fake LLM.
os.environ["COMPOSE_REPLIES"] = "0"

from src.knowledge.evidence import EvidenceHit


@pytest.fixture
def hit() -> EvidenceHit:
    return EvidenceHit(
        "chunk",
        "doc",
        "public",
        "supported text",
        0.8,
        1.0,
        True,
        "dehradun",
        datetime.now(timezone.utc) + timedelta(days=365),
    )
