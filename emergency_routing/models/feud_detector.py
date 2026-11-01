"""Pre-trained Public Feud & Fight Detection Model Wrapper."""

from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel
from config.settings import settings
from models.accident_detector import BoundingBox


class FeudDetectionResult(BaseModel):
    detected: bool
    confidence: float
    intensity_score: float  # 0.0 to 1.0 (feud aggression rating)
    dispute_type: str  # "verbal_dispute", "physical_fight", "mob_violence"
    detected_objects: List[BoundingBox]
    timestamp: datetime
    inference_source: str


class FeudDetector:
    """Detects public disputes, altercations, and violent feuds from video frames.

    Designed to interface with pre-trained fight detection weights (e.g.,
    'Musawer1214/Fight-Violence-detection-yolov8' or 3D CNN action classifiers).
    Includes synthetic simulation modes for temporal test scenarios.
    """

    def __init__(self, model_weights: Optional[str] = None, use_mock_if_unavailable: bool = True):
        self.model_weights = model_weights or settings.FEUD_MODEL_WEIGHTS
        self.use_mock_if_unavailable = use_mock_if_unavailable
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from ultralytics import YOLO

            self.model = YOLO(self.model_weights)
        except Exception:
            self.model = None

    def detect_frame(
        self, frame_data: Any, timestamp: Optional[datetime] = None
    ) -> FeudDetectionResult:
        """Runs inference on incoming frame."""
        ts = timestamp or datetime.now()

        if self.model is not None:
            results = self.model(frame_data, conf=settings.FEUD_MIN_INTENSITY_THRESHOLD)
            boxes: List[BoundingBox] = []
            max_conf = 0.0

            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = r.names.get(cls_id, "fight")
                    x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]

                    if conf > max_conf:
                        max_conf = conf

                    boxes.append(
                        BoundingBox(
                            x1=x1,
                            y1=y1,
                            x2=x2,
                            y2=y2,
                            label=cls_name,
                            confidence=round(conf, 3),
                        )
                    )

            detected = len(boxes) > 0
            intensity = min(1.0, max_conf * 1.05) if detected else 0.0
            dispute_type = "mob_violence" if len(boxes) >= 4 else "physical_fight"

            return FeudDetectionResult(
                detected=detected,
                confidence=round(max_conf, 3),
                intensity_score=round(intensity, 3),
                dispute_type=dispute_type,
                detected_objects=boxes,
                timestamp=ts,
                inference_source="ultralytics_feud_detector",
            )

        return FeudDetectionResult(
            detected=False,
            confidence=0.0,
            intensity_score=0.0,
            dispute_type="none",
            detected_objects=[],
            timestamp=ts,
            inference_source="simulated_standby",
        )

    def simulate_detection(
        self,
        confidence: float = 0.82,
        intensity: float = 0.75,
        dispute_type: str = "physical_fight",
        timestamp: Optional[datetime] = None,
    ) -> FeudDetectionResult:
        """Generates synthetic feud detection for simulation and temporal testing."""
        ts = timestamp or datetime.now()
        boxes = [
            BoundingBox(
                x1=50.0,
                y1=180.0,
                x2=190.0,
                y2=380.0,
                label=dispute_type,
                confidence=confidence,
            )
        ]
        return FeudDetectionResult(
            detected=True,
            confidence=confidence,
            intensity_score=intensity,
            dispute_type=dispute_type,
            detected_objects=boxes,
            timestamp=ts,
            inference_source="synthetic_simulation",
        )
