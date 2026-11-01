"""Vision LLM: Image Analysis via Ollama Cloud (gemma4:31b) with Groq fallback (qwen/qwen3.8-27b).

Accepts base64 images or file paths, returns structured scene analysis for
the Emergency Agent pipeline. Falls back to text-only models if vision fails,
building descriptions from continuous CV model outputs.
"""

import os
import base64
import io
import json
import httpx
from typing import Optional
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OLLAMA_KEY = os.getenv("OLLAMA", "").strip()

OLLAMA_CLOUD_BASE = "https://ollama.com/api/chat"
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

# Primary: Ollama Cloud vision model (free, confirmed working)
OLLAMA_VISION_MODELS = ["gemma4:31b", "gemma4:31b-cloud"]
# Fallback: Groq vision model (free, confirmed working)
GROQ_VISION_MODELS = ["qwen/qwen3.8-27b"]
# Text-only fallback models for when no image vision works
GROQ_TEXT_FALLBACK_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]


class VisionAnalysisResult(BaseModel):
    """Structured result from visual scene analysis."""
    detected_type: str          # ACCIDENT | FEUD | SUSPICIOUS | NORMAL | UNKNOWN
    description: str            # Human-readable scene description
    confidence: float           # 0.0 - 1.0
    severity_estimate: float    # 0.0 - 1.0
    people_count_estimate: int  # Approximate number of people
    vehicles_visible: bool
    injuries_visible: bool
    weapons_visible: bool
    model_used: str
    provider: str
    analysis_method: str        # vision_primary | vision_fallback | text_inference | unavailable


VISION_SYSTEM_PROMPT = """You are an AI emergency scene analyzer for a surveillance camera system.
Analyze the provided image and respond ONLY with valid JSON (no markdown):
{
  "detected_type": "ACCIDENT|FEUD|SUSPICIOUS|NORMAL|UNKNOWN",
  "description": "brief scene description (1-2 sentences)",
  "confidence": 0.0-1.0,
  "severity_estimate": 0.0-1.0,
  "people_count_estimate": integer,
  "vehicles_visible": true/false,
  "injuries_visible": true/false,
  "weapons_visible": true/false
}
Focus on: injuries, vehicle collisions, physical altercations, weapons, crowd dynamics.
"""

TEXT_INFERENCE_PROMPT = """You are an AI emergency scene analyst. Based on the provided CV detector outputs
(no image available), make your best inference about the scene.
Respond ONLY with valid JSON (no markdown):
{
  "detected_type": "ACCIDENT|FEUD|SUSPICIOUS|NORMAL|UNKNOWN",
  "description": "inferred scene description based on sensor data",
  "confidence": 0.0-1.0,
  "severity_estimate": 0.0-1.0,
  "people_count_estimate": integer,
  "vehicles_visible": true/false,
  "injuries_visible": true/false,
  "weapons_visible": true/false
}
Do not speculate or hallucinate. Default weapons_visible and injuries_visible to false unless explicitly stated in the input data.
"""


def _image_to_b64(image_input) -> Optional[str]:
    """Converts image input (path, bytes, or b64 string) to base64 string."""
    if isinstance(image_input, str):
        # Could be a file path or already b64
        p = Path(image_input)
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        # Assume already b64
        return image_input
    elif isinstance(image_input, bytes):
        return base64.b64encode(image_input).decode("utf-8")
    return None


def _parse_vision_json(raw: str, model: str, provider: str, method: str) -> Optional[VisionAnalysisResult]:
    """Parses LLM vision response into structured result."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        data = json.loads(text)
        detected = data.get("detected_type", "UNKNOWN").upper()
        if detected not in {"ACCIDENT", "FEUD", "SUSPICIOUS", "NORMAL", "UNKNOWN"}:
            detected = "UNKNOWN"
        return VisionAnalysisResult(
            detected_type=detected,
            description=data.get("description", "No description provided."),
            confidence=float(data.get("confidence", 0.5)),
            severity_estimate=float(data.get("severity_estimate", 0.0)),
            people_count_estimate=int(data.get("people_count_estimate", 0)),
            vehicles_visible=bool(data.get("vehicles_visible", False)),
            injuries_visible=bool(data.get("injuries_visible", False)),
            weapons_visible=bool(data.get("weapons_visible", False)),
            model_used=model,
            provider=provider,
            analysis_method=method,
        )
    except Exception:
        return None


def _call_ollama_vision(image_b64: str, model: str) -> Optional[str]:
    """Calls Ollama Cloud chat API with image in the messages."""
    if not OLLAMA_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {OLLAMA_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Analyze this emergency surveillance image. " + VISION_SYSTEM_PROMPT,
                "images": [image_b64],
            }
        ],
        "stream": False,
    }
    try:
        r = httpx.post(OLLAMA_CLOUD_BASE, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json().get("message", {}).get("content", "").strip()
        return None
    except Exception:
        return None


def _call_groq_vision(image_b64: str, model: str) -> Optional[str]:
    """Calls Groq vision API with base64 image."""
    if not GROQ_API_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": VISION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this emergency surveillance image:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }
        ],
        "max_tokens": 400,
        "temperature": 0.1,
    }
    try:
        r = httpx.post(GROQ_BASE_URL, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception:
        return None


def _call_groq_text_inference(cv_context: str, model: str) -> Optional[str]:
    """Uses text-only LLM to infer scene from CV output when no image is available."""
    if not GROQ_API_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": TEXT_INFERENCE_PROMPT},
            {"role": "user", "content": f"CV Detector Outputs:\n{cv_context}\n\nInfer the scene:"},
        ],
        "max_tokens": 400,
        "temperature": 0.1,
    }
    try:
        r = httpx.post(GROQ_BASE_URL, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception:
        return None


class VisionLLM:
    """Multi-provider vision analysis with intelligent fallback chain.

    Priority chain:
    1. Ollama Cloud gemma4:31b (free, vision confirmed)
    2. Groq qwen/qwen3.8-27b (free, vision confirmed)
    3. Groq text models with CV output inference (text-only fallback)
    4. Unavailable sentinel
    """

    def analyze_image(
        self,
        image_input,  # base64 str, bytes, or file path
        cv_context: Optional[str] = None,
    ) -> VisionAnalysisResult:
        """Analyzes an image using the best available free model.

        Args:
            image_input: Base64 string, bytes, or file path to image
            cv_context: Optional CV model output string for text-inference fallback
        """
        image_b64 = _image_to_b64(image_input) if image_input else None

        # === STAGE 1: Ollama Cloud Vision (Primary) ===
        if image_b64:
            for model in OLLAMA_VISION_MODELS:
                raw = _call_ollama_vision(image_b64, model)
                if raw:
                    result = _parse_vision_json(raw, model, "ollama_cloud", "vision_primary")
                    if result:
                        return result

        # === STAGE 2: Groq Vision (Fallback) ===
        if image_b64:
            for model in GROQ_VISION_MODELS:
                raw = _call_groq_vision(image_b64, model)
                if raw:
                    result = _parse_vision_json(raw, model, "groq", "vision_fallback")
                    if result:
                        return result

        # === STAGE 3: Text-Only Inference from CV Outputs ===
        if cv_context:
            for model in GROQ_TEXT_FALLBACK_MODELS:
                raw = _call_groq_text_inference(cv_context, model)
                if raw:
                    result = _parse_vision_json(raw, model, "groq", "text_inference")
                    if result:
                        return result

        # === STAGE 4: Fully Unavailable ===
        return VisionAnalysisResult(
            detected_type="UNKNOWN",
            description="No vision analysis available - all models failed or no image provided.",
            confidence=0.0,
            severity_estimate=0.0,
            people_count_estimate=0,
            vehicles_visible=False,
            injuries_visible=False,
            weapons_visible=False,
            model_used="none",
            provider="none",
            analysis_method="unavailable",
        )

    def analyze_cv_outputs(self, cv_context: str) -> VisionAnalysisResult:
        """Text-only analysis from continuous CV model outputs (no image needed)."""
        for model in GROQ_TEXT_FALLBACK_MODELS:
            raw = _call_groq_text_inference(cv_context, model)
            if raw:
                result = _parse_vision_json(raw, model, "groq", "text_inference")
                if result:
                    return result
        return VisionAnalysisResult(
            detected_type="UNKNOWN",
            description="Text inference unavailable.",
            confidence=0.0,
            severity_estimate=0.0,
            people_count_estimate=0,
            vehicles_visible=False,
            injuries_visible=False,
            weapons_visible=False,
            model_used="none",
            provider="none",
            analysis_method="unavailable",
        )
