#!/usr/bin/env python3
"""Interactive labeling tool - run on your Mac (needs opencv).

Shows each captured frame and files it into the dataset:

    python tools/label_frames.py --captures captures/night1 --dataset dataset

Keys:  b = back/supine    s = side    e = empty bed
       space = skip       q / ESC = quit
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cv2

KEYMAP = {ord("b"): "supine", ord("s"): "side", ord("e"): "empty"}
WINDOW = "noro labeler"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--captures", required=True, help="directory of night frames")
    ap.add_argument("--dataset", default="dataset", help="labeled output root")
    args = ap.parse_args()

    src = Path(args.captures)
    files = sorted(
        p for p in src.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not files:
        raise SystemExit(f"no images found in {src}")

    for label in set(KEYMAP.values()):
        (Path(args.dataset) / label).mkdir(parents=True, exist_ok=True)
    print(f"{len(files)} frames | keys: b=back(supine) s=side e=empty space=skip q=quit")

    labeled = skipped = 0
    for i, path in enumerate(files):
        img = cv2.imread(str(path))
        if img is None:
            print(f"skipping unreadable {path.name}")
            continue
        hud = img.copy()
        cv2.putText(hud, f"{i + 1}/{len(files)}  {path.name}", (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
        cv2.imshow(WINDOW, hud)
        while True:
            key = cv2.waitKey(0) & 0xFF
            if key == ord(" "):
                skipped += 1
                break
            if key in (ord("q"), 27):
                cv2.destroyAllWindows()
                print(f"labeled {labeled}, skipped {skipped}, "
                      f"{len(files) - labeled - skipped} left")
                return
            if key in KEYMAP:
                shutil.copy2(path, Path(args.dataset) / KEYMAP[key] / path.name)
                labeled += 1
                break
    cv2.destroyAllWindows()
    print(f"labeled {labeled}, skipped {skipped}")


if __name__ == "__main__":
    main()
