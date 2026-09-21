"""Frame sources: everything that yields (timestamp, RGB image) pairs.

All hardware knowledge is isolated here. `PiCameraSource` only works on the
Raspberry Pi; `FileSource` and `SyntheticSource` make the rest of the app
runnable (and testable) on any machine.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

import numpy as np
from PIL import Image


@dataclass
class Frame:
    """One captured frame. `timestamp` is time.monotonic() in seconds."""

    timestamp: float
    image: np.ndarray  # HxWx3 uint8 RGB
    name: str = ""


class FrameSource(abc.ABC):
    """Yields Frames until exhausted (or forever)."""

    @abc.abstractmethod
    def frames(self) -> Iterator[Frame]:
        ...

    def close(self) -> None:
        pass


class SyntheticSource(FrameSource):
    """Deterministic gray frames at a fixed cadence - demos and tests."""

    def __init__(
        self,
        interval: float = 1.0,
        width: int = 640,
        height: int = 480,
        max_frames: Optional[int] = None,
    ) -> None:
        self._interval = interval
        self._size = (height, width)
        self._max_frames = max_frames

    def frames(self) -> Iterator[Frame]:
        i = 0
        while self._max_frames is None or i < self._max_frames:
            image = np.full((*self._size, 3), 40 + (i % 3) * 30, dtype=np.uint8)
            yield Frame(timestamp=time.monotonic(), image=image, name=f"synthetic_{i:06d}")
            i += 1
            if self._interval > 0:
                time.sleep(self._interval)


class FileSource(FrameSource):
    """Replays still images from a directory, sorted by filename.

    Use it to develop on the Mac or to re-run a recorded night through a new
    detector. `interval` optionally paces frames like real time; `loop`
    repeats the directory forever.
    """

    _EXTENSIONS = (".jpg", ".jpeg", ".png")

    def __init__(self, directory: str, interval: float = 0.0, loop: bool = False) -> None:
        self._directory = Path(directory)
        if not self._directory.is_dir():
            raise ValueError(f"not a directory: {self._directory}")
        self._interval = interval
        self._loop = loop

    def _paths(self) -> List[Path]:
        return sorted(
            p for p in self._directory.iterdir()
            if p.suffix.lower() in self._EXTENSIONS
        )

    def frames(self) -> Iterator[Frame]:
        while True:
            paths = self._paths()
            if not paths:
                raise ValueError(f"no images found in {self._directory}")
            for path in paths:
                with Image.open(path) as im:
                    rgb = np.asarray(im.convert("RGB"))
                yield Frame(timestamp=time.monotonic(), image=rgb, name=path.name)
                if self._interval > 0:
                    time.sleep(self._interval)
            if not self._loop:
                return


class PiCameraSource(FrameSource):
    """NoIR camera via picamera2 (Raspberry Pi only).

    Night setup: auto-exposure off, fixed long exposure and high analog gain
    so an IR-illuminated dark bedroom produces a usable image. Tune
    `exposure_us` / `analog_gain` for your illuminator.

    NOTE: picamera2's "RGB888" format historically arrives BGR-ordered on
    some versions. That is harmless here as long as training images come
    from tools/capture_night.py, which uses the same format string.
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        exposure_us: int = 100_000,
        analog_gain: float = 12.0,
        interval: float = 1.0,
    ) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:  # pragma: no cover - Mac / non-Pi
            raise RuntimeError(
                "picamera2 is not available (expected on the Mac). "
                "Use --source files, --source synthetic, or run on the Pi."
            ) from exc
        self._interval = interval
        self._picam2 = Picamera2()
        config = self._picam2.create_still_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self._picam2.configure(config)
        self._picam2.set_controls(
            {
                "AeEnable": False,
                "ExposureTime": exposure_us,
                "AnalogueGain": analog_gain,
            }
        )
        self._picam2.start()
        time.sleep(0.5)  # let the sensor settle at the fixed exposure

    def frames(self) -> Iterator[Frame]:
        while True:
            array = np.ascontiguousarray(self._picam2.capture_array("main"))
            yield Frame(timestamp=time.monotonic(), image=array, name="pi_camera")
            if self._interval > 0:
                time.sleep(self._interval)

    def close(self) -> None:
        self._picam2.close()
