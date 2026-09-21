#!/usr/bin/env python3
"""Overnight frame recorder for training data (run on the Raspberry Pi).

Captures one JPEG every --interval seconds into --out until --hours elapse.
Typical night:

    python tools/capture_night.py --out captures/night1 --interval 2 --hours 10

Roughly 1 GB per night at 640x480 / 2 s interval. Copy the folder to your
Mac afterwards and label it with tools/label_frames.py.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image


def build_camera(args: argparse.Namespace):
    from picamera2 import Picamera2  # Pi only; imported lazily

    picam2 = Picamera2()
    config = picam2.create_still_configuration(
        main={"size": (args.width, args.height), "format": "RGB888"}
    )
    picam2.configure(config)
    # NOTE: keep this format identical to noro/camera.py so training and
    # inference see the same channel order.
    picam2.set_controls(
        {
            "AeEnable": False,
            "ExposureTime": args.exposure_us,
            "AnalogueGain": args.gain,
        }
    )
    picam2.start()
    time.sleep(1.0)  # settle at the fixed exposure
    return picam2


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    ap.add_argument("--out", default=None,
                    help="output directory (default captures/<timestamp>)")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between frames")
    ap.add_argument("--hours", type=float, default=10.0, help="stop after this long")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--exposure-us", type=int, default=100_000,
                    help="fixed exposure in microseconds (night)")
    ap.add_argument("--gain", type=float, default=12.0, help="analog gain")
    ap.add_argument("--jpeg-quality", type=int, default=85)
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path("captures") / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    print(f"recording {args.hours} h at {args.interval} s intervals -> {out}")

    picam2 = build_camera(args)
    deadline = time.monotonic() + args.hours * 3600
    n = dark = 0
    try:
        next_shot = time.monotonic()
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now < next_shot:
                time.sleep(min(0.1, next_shot - now))
                continue
            next_shot = max(next_shot + args.interval, now)

            frame = np.ascontiguousarray(picam2.capture_array("main"))
            n += 1
            mean = float(frame.mean())
            if mean < 8.0:
                dark += 1
                if dark % 50 == 1:
                    print(
                        f"WARNING: {dark}/{n} frames nearly black "
                        f"(mean={mean:.1f}) - check the IR illuminator"
                    )
            name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] + ".jpg"
            Image.fromarray(frame).save(out / name, quality=args.jpeg_quality)
            if n % 150 == 0:
                print(f"{n} frames saved ({dark} dark)")
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        picam2.close()
    print(f"saved {n} frames to {out}")


if __name__ == "__main__":
    main()
