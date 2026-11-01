"""LLM-powered Incident Classifier and Final Dispatch Decision Engine.

Uses Groq free-tier models (openai/gpt-oss-120b as primary, qwen/qwen3.8-27b as fallback)
to make the final decision: DISPATCH_AMBULANCE / DISPATCH_POLICE / MONITOR / IGNORE.
Replaces ALL hardcoded routing rules with structured LLM reasoning.
"""

import os
import json
import httpx
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

# Ordered list of free Groq models to try (most capable first)
GROQ_TEXT_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]


class LLMClassificationResult(BaseModel):
    """Structured output from LLM classification."""
    decision: str                    # DISPATCH_AMBULANCE | DISPATCH_POLICE | MONITOR | IGNORE
    confidence: float                # 0.0 - 1.0
    rationale: str                   # Human-readable explanation
    severity_override: Optional[float] = None   # LLM-adjusted severity if different
    escalate_to_police: bool = False
    dispatch_ambulance: bool = False
    model_used: str = "unknown"
    raw_response: str = ""


SYSTEM_PROMPT = """You are an AI emergency dispatch classifier for a city surveillance system.
You receive structured incident data from computer vision detectors and make the final dispatch decision.

Your job is to analyze the incident and output a JSON decision with these fields:
- decision: one of "DISPATCH_AMBULANCE", "DISPATCH_POLICE", "MONITOR", "IGNORE"
- confidence: float 0.0-1.0
- rationale: brief explanation (1-2 sentences)
- severity_override: null or float 0.0-1.0 if you disagree with CV severity
- escalate_to_police: true/false
- dispatch_ambulance: true/false

Decision rules (use your judgment, these are guidelines):
- DISPATCH_AMBULANCE: For accidents, vehicle crashes, injuries, medical emergencies with confidence >= 0.6
- DISPATCH_POLICE: For violent feuds/fights persisting >= 60 seconds (feud_duration_seconds >= 60), active riots, or verified weapons
- MONITOR: For feuds/fights persisting under 60 seconds (duration < 60s), suspicious activity, or borderline situations
- IGNORE: For false alarms, very low confidence (<0.4), normal traffic events
IMPORTANT: For disputes/feuds with feud_duration_seconds < 60.0 and no weapons, choose "MONITOR", not "DISPATCH_POLICE". Police should not be disturbed for brief arguments.

Respond ONLY with valid JSON, no markdown, no explanation outside JSON.
"""


def _call_groq(model: str, messages: list, timeout: int = 15) -> Optional[str]:
    """Calls Groq chat completion API."""
    if not GROQ_API_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.1,
    }
    try:
        r = httpx.post(GROQ_BASE_URL, headers=headers, json=payload, timeout=timeout)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception:
        return None


class LLMClassifier:
    """LLM-powered final dispatch decision engine using Groq free models."""

    def __init__(self):
        self._last_model_used = "none"

    def classify_incident(
        self,
        incident_type: str,
        confidence: float,
        severity: float,
        address: str,
        camera_id: str,
        feud_duration_seconds: float = 0.0,
        feud_avg_intensity: float = 0.0,
        image_description: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> LLMClassificationResult:
        """Classifies an incident and returns the final dispatch decision.

        Falls back to rule-based logic if all LLM calls fail.
        """
        user_content = self._build_prompt(
            incident_type=incident_type,
            confidence=confidence,
            severity=severity,
            address=address,
            camera_id=camera_id,
            feud_duration_seconds=feud_duration_seconds,
            feud_avg_intensity=feud_avg_intensity,
            image_description=image_description,
            additional_context=additional_context,
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # Try each model in order
        for model in GROQ_TEXT_MODELS:
            raw = _call_groq(model, messages)
            if raw:
                result = self._parse_response(raw, model)
                if result:
                    self._last_model_used = model
                    return result

        # Full fallback to rule-based
        return self._rule_based_fallback(
            incident_type, confidence, severity, feud_duration_seconds
        )

    def _build_prompt(self, **kwargs) -> str:
        lines = [
            f"INCIDENT CLASSIFICATION REQUEST - {datetime.now().isoformat()}",
            f"Type: {kwargs['incident_type']}",
            f"CV Confidence: {kwargs['confidence']:.2f}",
            f"CV Severity: {kwargs['severity']:.2f}",
            f"Location: {kwargs['address']} (Camera: {kwargs['camera_id']})",
        ]
        if kwargs["incident_type"] == "FEUD":
            lines.append(f"Feud Duration: {kwargs['feud_duration_seconds']:.1f}s")
            lines.append(f"Average Intensity: {kwargs['feud_avg_intensity']:.2f}")
        if kwargs.get("image_description"):
            lines.append(f"Vision Analysis: {kwargs['image_description']}")
        if kwargs.get("additional_context"):
            lines.append(f"Context: {kwargs['additional_context']}")
        lines.append("\nProvide your dispatch decision as JSON.")
        return "\n".join(lines)

    def _parse_response(self, raw: str, model: str) -> Optional[LLMClassificationResult]:
        """Parses LLM JSON response into LLMClassificationResult."""
        # Strip markdown if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        try:
            data = json.loads(text)
            decision = data.get("decision", "MONITOR").upper()
            if decision not in {"DISPATCH_AMBULANCE", "DISPATCH_POLICE", "MONITOR", "IGNORE"}:
                decision = "MONITOR"
            return LLMClassificationResult(
                decision=decision,
                confidence=float(data.get("confidence", 0.5)),
                rationale=data.get("rationale", "LLM provided no rationale."),
                severity_override=data.get("severity_override"),
                escalate_to_police=bool(data.get("escalate_to_police", False)),
                dispatch_ambulance=bool(data.get("dispatch_ambulance", False)),
                model_used=model,
                raw_response=raw[:500],
            )
        except Exception:
            return None

    def _rule_based_fallback(
        self,
        incident_type: str,
        confidence: float,
        severity: float,
        feud_duration_seconds: float,
    ) -> LLMClassificationResult:
        """Fallback rule-based classification when LLM is unavailable."""
        if incident_type == "ACCIDENT" and confidence >= 0.6:
            return LLMClassificationResult(
                decision="DISPATCH_AMBULANCE",
                confidence=confidence,
                rationale=f"[FALLBACK] Accident detected with confidence {confidence:.2f}. Dispatching ambulance.",
                dispatch_ambulance=True,
                model_used="rule_based_fallback",
                raw_response="",
            )
        elif incident_type == "FEUD":
            if feud_duration_seconds >= 60.0 and severity >= 0.55:
                return LLMClassificationResult(
                    decision="DISPATCH_POLICE",
                    confidence=confidence,
                    rationale=f"[FALLBACK] Feud persisted {feud_duration_seconds:.0f}s with intensity {severity:.2f}. Dispatching police.",
                    escalate_to_police=True,
                    model_used="rule_based_fallback",
                    raw_response="",
                )
            else:
                return LLMClassificationResult(
                    decision="MONITOR",
                    confidence=confidence,
                    rationale=f"[FALLBACK] Feud duration {feud_duration_seconds:.0f}s below threshold. Monitoring.",
                    model_used="rule_based_fallback",
                    raw_response="",
                )
        elif confidence < 0.4:
            return LLMClassificationResult(
                decision="IGNORE",
                confidence=confidence,
                rationale=f"[FALLBACK] Low confidence detection ({confidence:.2f}). Ignoring.",
                model_used="rule_based_fallback",
                raw_response="",
            )
        else:
            return LLMClassificationResult(
                decision="MONITOR",
                confidence=confidence,
                rationale="[FALLBACK] Unclear incident type. Monitoring.",
                model_used="rule_based_fallback",
                raw_response="",
            )

    @property
    def last_model_used(self) -> str:
        return self._last_model_used
