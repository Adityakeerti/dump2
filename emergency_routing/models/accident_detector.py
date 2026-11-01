"""Pre-trained Accident Detection Model Wrapper (YOLOv8 Accident Specialist)."""

from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from config.settings import settings


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    confidence: float


class AccidentDetectionResult(BaseModel):
    detected: bool
    confidence: float
    severity: float  # 0.0 to 1.0
    detected_objects: List[BoundingBox]
    timestamp: datetime
    inference_source: str


class AccidentDetector:
    """Detects traffic accidents, vehicle crashes, and collisions from video frames.

    Designed to load pre-trained YOLOv8 accident detection models (e.g.,
    'keremberke/yolov8m-car-accident-detection' or local .pt weights).
    Includes simulated fallback for offline environments and CI/CD testing.
    """

    def __init__(self, model_weights: Optional[str] = None, use_mock_if_unavailable: bool = True):
        self.model_weights = model_weights or settings.ACCIDENT_MODEL_WEIGHTS
        self.use_mock_if_unavailable = use_mock_if_unavailable
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from ultralytics import YOLO

            # Load weights from local path or HuggingFace hub
            self.model = YOLO(self.model_weights)
        except Exception:
            # Fall back to synthetic detector mode if ultralytics/torch/cuda is not loaded
            self.model = None

    def detect_frame(
        self, frame_data: Any, timestamp: Optional[datetime] = None
    ) -> AccidentDetectionResult:
        """Runs inference on a single video frame (numpy array or image path)."""
        ts = timestamp or datetime.now()

        if self.model is not None:
            results = self.model(frame_data, conf=settings.ACCIDENT_CONFIDENCE_THRESHOLD)
            boxes: List[BoundingBox] = []
            max_conf = 0.0

            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = r.names.get(cls_id, "accident")
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
            severity = min(1.0, max_conf * 1.1) if detected else 0.0
            return AccidentDetectionResult(
                detected=detected,
                confidence=round(max_conf, 3),
                severity=round(severity, 3),
                detected_objects=boxes,
                timestamp=ts,
                inference_source="ultralytics_yolov8",
            )

        # Fallback simulated response
        return AccidentDetectionResult(
            detected=False,
            confidence=0.0,
            severity=0.0,
            detected_objects=[],
            timestamp=ts,
            inference_source="simulated_standby",
        )

    def simulate_detection(
        self, confidence: float = 0.88, severity: float = 0.85, timestamp: Optional[datetime] = None
    ) -> AccidentDetectionResult:
        """Generates a realistic test detection for integration verification."""
        ts = timestamp or datetime.now()
        boxes = [
            BoundingBox(
                x1=120.0,
                y1=200.0,
                x2=340.0,
                y2=410.0,
                label="car_collision",
                confidence=confidence,
            )
        ]
        return AccidentDetectionResult(
            detected=True,
            confidence=confidence,
            severity=severity,
            detected_objects=boxes,
            timestamp=ts,
            inference_source="synthetic_simulation",
        )
