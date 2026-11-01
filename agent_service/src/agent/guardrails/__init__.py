"""Guardrails and Polite Refusal Layer for City Sense Agent Service.

Exports input safety inspection, scope classification, and structured polite refusals.
"""

from src.agent.guardrails.input_guard import (
    GuardrailCheckResult,
    InputGuard,
    check_input_safety,
)
from src.agent.guardrails.polite_refusal import (
    ActionChip,
    PoliteRefusalResult,
    build_polite_refusal,
    refuse_injection,
    refuse_out_of_scope,
    respond_civic_greeting,
)
from src.agent.guardrails.scope_classifier import (
    QueryScope,
    ScopeClassificationResult,
    ScopeClassifier,
    classify_scope,
)

__all__ = [
    "GuardrailCheckResult",
    "InputGuard",
    "check_input_safety",
    "QueryScope",
    "ScopeClassificationResult",
    "ScopeClassifier",
    "classify_scope",
    "ActionChip",
    "PoliteRefusalResult",
    "build_polite_refusal",
    "refuse_injection",
    "refuse_out_of_scope",
    "respond_civic_greeting",
]
