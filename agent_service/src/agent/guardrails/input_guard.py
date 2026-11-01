"""Input Guardrail module for City Sense Agent Service.

Detects prompt injections, jailbreaks, instruction overrides, system prompt extractions,
and delimiter/control sequence evasions across English, Hindi, and Hinglish.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass
class GuardrailCheckResult:
    """Represents the outcome of an input safety inspection."""

    is_safe: bool
    reason: str | None = None
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "reason": self.reason,
            "risk_score": self.risk_score,
        }


# High confidence instruction override patterns (Risk score: 0.90 - 1.00)
INSTRUCTION_OVERRIDE_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (
        re.compile(
            r"\bignore\s+(?:all\s+)?(?:previous|prior|above|past)\s+(?:instructions|prompts?|directions?|rules?|commands?|context)\b",
            re.IGNORECASE,
        ),
        "instruction_override_ignore_previous",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:forget|disregard|drop|cancel|clear|reset)\s+(?:all\s+)?(?:previous|prior|above|past)\s+(?:instructions|prompts?|directions?|rules?|context)\b",
            re.IGNORECASE,
        ),
        "instruction_override_forget_previous",
        0.95,
    ),
    (
        re.compile(
            r"\boverride\s+(?:system|all|safety|security)\s+(?:instructions|prompts?|rules?|guardrails?|filters?)\b",
            re.IGNORECASE,
        ),
        "instruction_override_system_override",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:bypass|disable|turn\s+off|remove|circumvent)\s+(?:all\s+)?(?:safety|guardrails?|filters?|content\s+filters?|moderation|restrictions?)\b",
            re.IGNORECASE,
        ),
        "safety_bypass_attempt",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:new\s+system\s+instructions?|from\s+now\s+on\s+you\s+are\s+no\s+longer\s+(?:city\s+sense|civic))\b",
            re.IGNORECASE,
        ),
        "system_identity_override",
        0.90,
    ),
    (
        re.compile(
            r"\b(?:start\s+a\s+new\s+session\s+and\s+forget\s+everything|wipe\s+all\s+memory\s+and\s+instructions)\b",
            re.IGNORECASE,
        ),
        "memory_wipe_instruction",
        0.90,
    ),
]

# High confidence jailbreak patterns (Risk score: 0.90 - 1.00)
JAILBREAK_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (
        re.compile(r"\b(?:dan\s+mode|do\s+anything\s+now)\b", re.IGNORECASE),
        "jailbreak_dan_mode",
        0.98,
    ),
    (
        re.compile(
            r"\b(?:jailbreak|jailbroken|anti-?filter|unfiltered\s+mode|god\s+mode|chaos\s+mode|evil\s+mode)\b",
            re.IGNORECASE,
        ),
        "jailbreak_explicit_mode",
        0.95,
    ),
    (
        re.compile(
            r"\bdeveloper\s+mode\s+(?:enabled|activated|on|switched\s+on)\b",
            re.IGNORECASE,
        ),
        "jailbreak_developer_mode",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:act\s+as\s+an?\s+unrestricted|pretend\s+you\s+have\s+no\s+rules|pretend\s+there\s+are\s+no\s+safety\s+guidelines)\b",
            re.IGNORECASE,
        ),
        "jailbreak_roleplay_unrestricted",
        0.92,
    ),
    (
        re.compile(
            r"\b(?:stan\s+mode|dude\s+mode|mongo\s+tom|aim\s+mode)\b",
            re.IGNORECASE,
        ),
        "jailbreak_persona_exploit",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:bypass\s+all\s+limitations|ignore\s+ethical\s+guidelines|unrestricted\s+ai)\b",
            re.IGNORECASE,
        ),
        "jailbreak_ethics_bypass",
        0.90,
    ),
]

# System prompt extraction and leakage probing (Risk score: 0.85 - 0.95)
PROMPT_EXTRACTION_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (
        re.compile(
            r"\b(?:what\s+is|what're|show\s+me|display|reveal|print|output|dump|leak|repeat|read\s+out)\s+(?:(?:your|the)\s+)?(?:initial\s+|hidden\s+|internal\s+|secret\s+|original\s+)?(?:system\s+prompt|system\s+instructions?|system\s+context|developer\s+instructions?|base\s+prompt|meta\s+prompt|prompt|instructions?)\b",
            re.IGNORECASE,
        ),
        "prompt_extraction_system_prompt",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:repeat|print|output)\s+(?:the\s+)?(?:text|words|instructions)\s+(?:above|before\s+this|from\s+the\s+beginning)\b",
            re.IGNORECASE,
        ),
        "prompt_extraction_repeat_above",
        0.90,
    ),
    (
        re.compile(
            r"\bwhat\s+was\s+written\s+before\s+my\s+(?:message|turn|prompt)\b",
            re.IGNORECASE,
        ),
        "prompt_extraction_context_probing",
        0.88,
    ),
    (
        re.compile(
            r"^\s*(?:what\s+is\s+your\s+system\s+prompt\??|reveal\s+system\s+prompt|show\s+system\s+prompt|print\s+system\s+prompt)\s*$",
            re.IGNORECASE,
        ),
        "prompt_extraction_direct_command",
        0.95,
    ),
]

# Delimiter evasion and delimiter injection tokens (Risk score: 0.85 - 0.95)
DELIMITER_EVASION_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"<\s*\|\s*im_start\s*\|\s*>", re.IGNORECASE), "delimiter_im_start", 0.95),
    (re.compile(r"<\s*\|\s*im_end\s*\|\s*>", re.IGNORECASE), "delimiter_im_end", 0.95),
    (re.compile(r"\[\s*INST\s*\]|\[\s*/\s*INST\s*\]", re.IGNORECASE), "delimiter_llama_inst", 0.95),
    (re.compile(r"<\s*<\s*SYS\s*>\s*>|<\s*/\s*<\s*SYS\s*>\s*>", re.IGNORECASE), "delimiter_llama_sys", 0.95),
    (re.compile(r"\[\s*SYSTEM\s*\]|\[\s*/\s*SYSTEM\s*\]", re.IGNORECASE), "delimiter_system_tag", 0.90),
    (re.compile(r"<\s*system\s*>|<\s*/\s*system\s*>", re.IGNORECASE), "delimiter_xml_system", 0.90),
    (re.compile(r"```\s*system", re.IGNORECASE), "delimiter_code_system", 0.90),
    (
        re.compile(r"---\s*(?:BEGIN|END)\s+SYSTEM\s+PROMPT\s*---", re.IGNORECASE),
        "delimiter_boundary_spoofing",
        0.95,
    ),
    (
        re.compile(r"(?m)^\s*(?:System|Human|Assistant|User)\s*:\s*(?:ignore|you\s+are|override|forget)", re.IGNORECASE),
        "delimiter_role_spoofing",
        0.90,
    ),
]

# Hindi and Hinglish prompt injection patterns (Risk score: 0.85 - 0.95)
HINDI_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (
        re.compile(
            r"(?:पिछले|पुराने|सभी)\s+(?:निर्देश|नियम|आदेश)\s+(?:भूल\s+जाओ|रद्द\s+करो|अनदेखा\s+करो|हटाओ|मिटाओ)",
            re.IGNORECASE,
        ),
        "hindi_instruction_override",
        0.95,
    ),
    (
        re.compile(
            r"सिस्टम\s+प्रॉम्प्ट\s+(?:दिखाओ|बताओ|प्रिंट\s+करो|शेयर\s+करो|लिखो|बाहर\s+निकालो)",
            re.IGNORECASE,
        ),
        "hindi_prompt_extraction",
        0.95,
    ),
    (
        re.compile(
            r"(?:अपने\s+नियम|सुरक्षा\s+नियम)\s+(?:बदलो|तोड़ो|हटाओ|बायपास\s+करो)",
            re.IGNORECASE,
        ),
        "hindi_rule_break",
        0.90,
    ),
    (
        re.compile(
            r"(?:DAN\s+मोड|जेलब्रेक|हैक\s+मोड|अनफिल्टर्ड\s+मोड)",
            re.IGNORECASE,
        ),
        "hindi_jailbreak",
        0.95,
    ),
    (
        re.compile(
            r"(?:अब\s+से\s+तुम\s+बिना\s+किसी\s+नियम\s+के|अब\s+से\s+तुम\s+कुछ\s+भी\s+कर\s+सकते\s+हो)",
            re.IGNORECASE,
        ),
        "hindi_role_override",
        0.90,
    ),
    # Hinglish patterns
    (
        re.compile(
            r"\b(?:pehle\s+ke|purane)\s+(?:instructions?|rules?|nirdesh)\s+(?:bhool\s+jao|bhul\s+jao|ignore\s+karo)\b",
            re.IGNORECASE,
        ),
        "hinglish_instruction_override",
        0.95,
    ),
    (
        re.compile(
            r"\bsystem\s+prompt\s+(?:dikhao|batao|print\s+karo|share\s+karo)\b",
            re.IGNORECASE,
        ),
        "hinglish_prompt_extraction",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:jailbreak\s+mode|bina\s+kisi\s+rule\s+ke)\b",
            re.IGNORECASE,
        ),
        "hinglish_jailbreak",
        0.92,
    ),
]


class InputGuard:
    """Evaluates user text inputs for prompt injections, jailbreaks, and evasions."""

    def __init__(self, risk_threshold: float = 0.70):
        self.risk_threshold = risk_threshold
        self.all_rules = (
            INSTRUCTION_OVERRIDE_PATTERNS
            + JAILBREAK_PATTERNS
            + PROMPT_EXTRACTION_PATTERNS
            + DELIMITER_EVASION_PATTERNS
            + HINDI_INJECTION_PATTERNS
        )

    @staticmethod
    def normalize_text(text: str) -> str:
        """Cleans zero-width characters and normalizes unicode representations."""
        if not text:
            return ""
        # Unicode normalization (NFKC decomposes compatibility chars, e.g. ligature evasions)
        normalized = unicodedata.normalize("NFKC", text)
        # Strip zero-width characters & BOM
        normalized = re.sub(r"[\u200b\u200c\u200d\ufeff\u2060]", "", normalized)
        # Strip non-printable ASCII control characters (keeping standard whitespace)
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", normalized)
        return normalized

    def check(self, text: str) -> GuardrailCheckResult:
        """Inspects text and returns a GuardrailCheckResult."""
        if not text or not text.strip():
            return GuardrailCheckResult(is_safe=True, reason=None, risk_score=0.0)

        cleaned = self.normalize_text(text)

        # Evaluate against all categorized pattern rules
        max_score = 0.0
        primary_reason: str | None = None

        for pattern, reason, score in self.all_rules:
            if pattern.search(cleaned):
                if score > max_score:
                    max_score = score
                    primary_reason = reason

        # Delimiter heuristic: check for excessive suspicious delimiters combined with command words
        if max_score < self.risk_threshold:
            bracket_density = len(re.findall(r"[<>{}\[\]|]", cleaned))
            if bracket_density > 6 and re.search(r"\b(?:system|instruction|prompt|mode)\b", cleaned, re.IGNORECASE):
                max_score = max(max_score, 0.75)
                primary_reason = "suspicious_delimiter_stuffing"

        is_safe = max_score < self.risk_threshold
        return GuardrailCheckResult(
            is_safe=is_safe,
            reason=primary_reason if not is_safe else None,
            risk_score=max_score,
        )


_DEFAULT_GUARD = InputGuard()


def check_input_safety(text: str, risk_threshold: float = 0.70) -> GuardrailCheckResult:
    """Convenience functional interface to inspect input text safety."""
    if risk_threshold == 0.70:
        return _DEFAULT_GUARD.check(text)
    return InputGuard(risk_threshold=risk_threshold).check(text)
