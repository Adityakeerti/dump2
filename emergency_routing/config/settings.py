"""Global configuration for Emergency Response Agent System.
All thresholds and model IDs loaded from environment or sensible defaults.
"""

import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    # Feud / Dispute Temporal Thresholds (used as LLM context hints, not hard rules)
    FEUD_MIN_DURATION_SECONDS: float = float(os.getenv("FEUD_MIN_DURATION_SECONDS", "60.0"))
    FEUD_MIN_INTENSITY_THRESHOLD: float = float(os.getenv("FEUD_MIN_INTENSITY_THRESHOLD", "0.55"))
    FEUD_COOLDOWN_RESET_SECONDS: float = float(os.getenv("FEUD_COOLDOWN_RESET_SECONDS", "45.0"))

    # Accident Thresholds
    ACCIDENT_CONFIDENCE_THRESHOLD: float = float(os.getenv("ACCIDENT_CONFIDENCE_THRESHOLD", "0.60"))

    # Ambulance & Traffic Parameters
    DEFAULT_AMBULANCE_SPEED_KMH: float = float(os.getenv("DEFAULT_AMBULANCE_SPEED_KMH", "60.0"))
    JAM_SPEED_KMH: float = float(os.getenv("JAM_SPEED_KMH", "12.0"))

    # Pre-trained CV Model Checkpoint Paths / HuggingFace IDs
    ACCIDENT_MODEL_WEIGHTS: str = os.getenv(
        "ACCIDENT_MODEL_WEIGHTS", "keremberke/yolov8m-car-accident-detection"
    )
    FEUD_MODEL_WEIGHTS: str = os.getenv(
        "FEUD_MODEL_WEIGHTS", "Musawer1214/Fight-Violence-detection-yolov8"
    )

    # LLM Models (confirmed free & working as of 2026-10-30 live check)
    LLM_CLASSIFIER_PRIMARY: str = os.getenv("LLM_CLASSIFIER_PRIMARY", "openai/gpt-oss-120b")
    LLM_CLASSIFIER_FALLBACK: str = os.getenv("LLM_CLASSIFIER_FALLBACK", "openai/gpt-oss-20b")

    # Vision Models (confirmed free & vision-capable as of 2026-10-30 live check)
    VISION_PRIMARY_MODEL: str = os.getenv("VISION_PRIMARY_MODEL", "gemma4:31b")
    VISION_PRIMARY_PROVIDER: str = os.getenv("VISION_PRIMARY_PROVIDER", "ollama_cloud")
    VISION_FALLBACK_MODEL: str = os.getenv("VISION_FALLBACK_MODEL", "qwen/qwen3.8-27b")
    VISION_FALLBACK_PROVIDER: str = os.getenv("VISION_FALLBACK_PROVIDER", "groq")

    # API Keys (read from .env)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OLLAMA_KEY: str = os.getenv("OLLAMA", "")

    # Simulation & Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
