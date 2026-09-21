"""Central configuration: every tunable of the watchdog lives here."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppConfig:
    # --- trigger -----------------------------------------------------------
    hold_time_s: float = 2.0        # supine seconds before a pulse fires
    cooldown_s: float = 10.0        # min seconds between pulses (re-nudges
                                    # every cooldown while still supine)
    unknown_grace_s: float = 0.5    # brief UNKNOWN blips tolerated inside a
                                    # supine streak (classifier flicker)

    # --- actuator ----------------------------------------------------------
    pulse_width_s: float = 0.2      # GPIO pulse length
    gpio_pin: int = 17              # BCM numbering (GPIO17 = physical pin 11)

    # --- camera (night defaults for the NoIR v2 + IR illuminator) ----------
    frame_width: int = 640
    frame_height: int = 480
    exposure_us: int = 100_000      # fixed 100 ms exposure, AE off
    analog_gain: float = 12.0       # high gain for IR-lit dark scenes
    capture_interval_s: float = 1.0  # ~1 fps is plenty for a 2 s hold

    # --- detector ----------------------------------------------------------
    model_path: str = "models/model.tflite"
    labels_path: str = "models/labels.txt"
    confidence_threshold: float = 0.70  # below this -> UNKNOWN (resets streak)
