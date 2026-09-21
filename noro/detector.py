"""Position classification: turns an RGB frame into SUPINE / SIDE / UNKNOWN."""

from __future__ import annotations

import abc
import enum
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


class BodyPosition(enum.Enum):
    SUPINE = "supine"    # lying on the back -> this is what triggers a pulse
    SIDE = "side"        # any non-supine sleeping posture
    UNKNOWN = "unknown"  # low confidence / empty bed / nobody visible


_LABEL_TO_POSITION = {
    "supine": BodyPosition.SUPINE,
    "side": BodyPosition.SIDE,
}


def position_from_label(label: str) -> BodyPosition:
    """Map a model label to a position. Anything else ('empty', ...) is
    UNKNOWN, which safely resets the trigger after the grace window."""
    return _LABEL_TO_POSITION.get(label.strip().lower(), BodyPosition.UNKNOWN)


def _make_interpreter(model_path: str):
    """TFLite interpreter, preferring the small Pi package when present."""
    try:
        from tflite_runtime.interpreter import Interpreter  # Raspberry Pi

        return Interpreter(model_path=model_path)
    except ImportError:
        pass
    try:
        from ai_edge_litert.interpreter import Interpreter  # newer host pkg

        return Interpreter(model_path=model_path)
    except ImportError:
        pass
    try:
        import tensorflow as tf  # full TF install

        return tf.lite.Interpreter(model_path=model_path)
    except ImportError:
        raise RuntimeError(
            "No TFLite interpreter found. On the Pi: pip install tflite-runtime. "
            "On a dev machine: pip install tensorflow (or use --detector mock)."
        )


class BaseDetector(abc.ABC):
    """Classifies one RGB frame into a body position."""

    @abc.abstractmethod
    def classify(self, image: np.ndarray) -> "tuple[BodyPosition, float]":
        """Returns (position, confidence in [0, 1])."""
        ...


class MockDetector(BaseDetector):
    """Scripted detector for demos and tests: cycles a fixed pattern."""

    DEFAULT_PATTERN = [BodyPosition.SIDE] * 3 + [BodyPosition.SUPINE] * 7

    def __init__(
        self,
        pattern: Optional[list] = None,
        confidence: float = 0.95,
    ) -> None:
        self._pattern = list(pattern or self.DEFAULT_PATTERN)
        self._confidence = confidence
        self._i = 0

    def classify(self, image: np.ndarray) -> "tuple[BodyPosition, float]":
        position = self._pattern[self._i % len(self._pattern)]
        self._i += 1
        return position, self._confidence


class TFLiteDetector(BaseDetector):
    """Runs the classifier exported by tools/train_classifier.py."""

    def __init__(
        self,
        model_path: str,
        labels_path: str,
        confidence_threshold: float = 0.70,
    ) -> None:
        model_path = Path(model_path)
        labels_path = Path(labels_path)
        if not model_path.is_file():
            raise FileNotFoundError(
                f"model not found: {model_path}. Train one with "
                "tools/train_classifier.py (or use --detector mock)."
            )
        if not labels_path.is_file():
            raise FileNotFoundError(f"labels file not found: {labels_path}")

        self._interpreter = _make_interpreter(str(model_path))
        self._interpreter.allocate_tensors()

        input_details = self._interpreter.get_input_details()[0]
        self._input_index = input_details["index"]
        # trust the model's own input geometry, not a hardcoded constant
        self._input_size = (int(input_details["shape"][1]), int(input_details["shape"][2]))
        self._output_index = self._interpreter.get_output_details()[0]["index"]

        self._labels = [
            line.strip()
            for line in labels_path.read_text().splitlines()
            if line.strip()
        ]
        self._threshold = float(confidence_threshold)

    def classify(self, image: np.ndarray) -> "tuple[BodyPosition, float]":
        self._interpreter.set_tensor(self._input_index, self._preprocess(image))
        self._interpreter.invoke()
        probs = self._interpreter.get_tensor(self._output_index)[0]
        idx = int(np.argmax(probs))
        confidence = float(probs[idx])
        label = self._labels[idx] if idx < len(self._labels) else ""
        if confidence < self._threshold:
            return BodyPosition.UNKNOWN, confidence
        return position_from_label(label), confidence

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Resize to the model input and scale to [-1, 1] (MobileNet style).

        Must match keras.applications.mobilenet_v2.preprocess_input used in
        tools/train_classifier.py.
        """
        resized = Image.fromarray(image).resize(self._input_size, Image.BILINEAR)
        arr = np.asarray(resized, dtype=np.float32) / 127.5 - 1.0
        return arr[np.newaxis, ...]
