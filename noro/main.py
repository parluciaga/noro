"""Main loop: capture -> classify -> trigger -> actuate.

Runs on the Pi for real; every piece also degrades gracefully on a dev
machine. Hardware-free demo:

    noro --source synthetic --detector mock --actuator stub
"""

from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .actuator import BaseActuator, GpioPulseActuator, StubActuator
from .camera import FileSource, FrameSource, PiCameraSource, SyntheticSource
from .config import AppConfig
from .detector import BaseDetector, BodyPosition, MockDetector, TFLiteDetector
from .trigger import SupineTrigger

log = logging.getLogger("noro")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="noro",
        description="Positional-snoring watchdog: pulse an actuator after ~2 s supine.",
    )
    p.add_argument("--source", choices=["pi", "files", "synthetic"], default="pi",
                   help="frame source (default: pi)")
    p.add_argument("--frames-dir", help="image directory for --source files")
    p.add_argument("--interval", type=float, help="seconds between frames (default 1.0)")
    p.add_argument("--detector", choices=["tflite", "mock"], default="tflite")
    p.add_argument("--model", help="path to model.tflite (default models/model.tflite)")
    p.add_argument("--labels", help="path to labels.txt (default models/labels.txt)")
    p.add_argument("--confidence", type=float, help="min confidence before UNKNOWN (default 0.70)")
    p.add_argument("--actuator", choices=["gpio", "stub"], default="gpio")
    p.add_argument("--pin", type=int, help="BCM GPIO pin for the pulse (default 17)")
    p.add_argument("--hold-time", type=float, help="supine seconds before firing (default 2.0)")
    p.add_argument("--cooldown", type=float, help="min seconds between pulses (default 10)")
    p.add_argument("--pulse-width", type=float, help="pulse length in seconds (default 0.2)")
    p.add_argument("--unknown-grace", type=float,
                   help="seconds of UNKNOWN tolerated inside a streak (default 0.5)")
    p.add_argument("--width", type=int, help="capture width (default 640)")
    p.add_argument("--height", type=int, help="capture height (default 480)")
    p.add_argument("--exposure-us", type=int, help="fixed night exposure in us (default 100000)")
    p.add_argument("--gain", type=float, help="analog gain (default 12)")
    p.add_argument("--log-dir", help="write a per-night timeline CSV here")
    p.add_argument("--max-frames", type=int, help="stop after N frames (debugging)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _apply(cfg: AppConfig, args: argparse.Namespace) -> None:
    overrides = {
        "hold_time_s": args.hold_time,
        "cooldown_s": args.cooldown,
        "unknown_grace_s": args.unknown_grace,
        "pulse_width_s": args.pulse_width,
        "gpio_pin": args.pin,
        "frame_width": args.width,
        "frame_height": args.height,
        "exposure_us": args.exposure_us,
        "analog_gain": args.gain,
        "capture_interval_s": args.interval,
        "model_path": args.model,
        "labels_path": args.labels,
        "confidence_threshold": args.confidence,
    }
    for field, value in overrides.items():
        if value is not None:
            setattr(cfg, field, value)


def _build_source(args: argparse.Namespace, cfg: AppConfig) -> FrameSource:
    if args.source == "pi":
        return PiCameraSource(
            width=cfg.frame_width,
            height=cfg.frame_height,
            exposure_us=cfg.exposure_us,
            analog_gain=cfg.analog_gain,
            interval=cfg.capture_interval_s,
        )
    if args.source == "files":
        if not args.frames_dir:
            raise ValueError("--frames-dir is required when --source files")
        return FileSource(directory=args.frames_dir, interval=cfg.capture_interval_s)
    return SyntheticSource(
        interval=cfg.capture_interval_s,
        width=cfg.frame_width,
        height=cfg.frame_height,
        max_frames=args.max_frames,
    )


def _build_detector(args: argparse.Namespace, cfg: AppConfig) -> BaseDetector:
    if args.detector == "mock":
        return MockDetector()
    return TFLiteDetector(
        model_path=cfg.model_path,
        labels_path=cfg.labels_path,
        confidence_threshold=cfg.confidence_threshold,
    )


def _build_actuator(args: argparse.Namespace, cfg: AppConfig) -> BaseActuator:
    if args.actuator == "gpio":
        return GpioPulseActuator(pin=cfg.gpio_pin)
    return StubActuator()


def _open_timeline(log_dir: str):
    path = Path(log_dir) / f"timeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("w", newline="")
    writer = csv.writer(fh)
    writer.writerow(["wall_time", "monotonic_s", "position", "confidence", "fired"])
    return fh, writer, path


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    cfg = AppConfig()
    _apply(cfg, args)

    try:
        source = _build_source(args, cfg)
        detector = _build_detector(args, cfg)
        actuator = _build_actuator(args, cfg)
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        log.error("%s", exc)
        return 2

    trigger = SupineTrigger(
        hold_time_s=cfg.hold_time_s,
        cooldown_s=cfg.cooldown_s,
        unknown_grace_s=cfg.unknown_grace_s,
    )

    timeline = None
    if args.log_dir:
        fh, writer, path = _open_timeline(args.log_dir)
        timeline = (fh, writer, path)
        log.info("timeline CSV: %s", path)

    frames = pulses = 0
    log.info(
        "watching (hold=%.1fs cooldown=%ss pulse=%.0fms)",
        cfg.hold_time_s, cfg.cooldown_s, cfg.pulse_width_s * 1000,
    )
    try:
        for frame in source.frames():
            frames += 1
            try:
                position, confidence = detector.classify(frame.image)
            except Exception:  # keep the watchdog alive on a bad frame
                log.exception("classify failed (%s)", frame.name)
                position, confidence = BodyPosition.UNKNOWN, 0.0

            fired = trigger.update(position, frame.timestamp)
            if fired:
                pulses += 1
                log.warning(
                    ">>> SUPINE for %.1fs -> PULSE #%d (%.0f ms)",
                    cfg.hold_time_s, pulses, cfg.pulse_width_s * 1000,
                )
                try:
                    actuator.fire(cfg.pulse_width_s)
                except Exception:
                    log.exception("actuator failed")

            log.debug(
                "frame %d: %s conf=%.2f%s",
                frames, position.value, confidence, " FIRED" if fired else "",
            )
            if timeline:
                timeline[1].writerow(
                    [
                        datetime.now().isoformat(timespec="seconds"),
                        f"{frame.timestamp:.3f}",
                        position.value,
                        f"{confidence:.3f}",
                        int(fired),
                    ]
                )
                timeline[0].flush()

            if args.max_frames is not None and frames >= args.max_frames:
                break
    except KeyboardInterrupt:
        log.info("interrupted")
    finally:
        source.close()
        actuator.close()
        if timeline:
            timeline[0].close()

    log.info("done: %d frames, %d pulses", frames, pulses)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
