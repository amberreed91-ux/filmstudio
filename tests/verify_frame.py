#!/usr/bin/env python3
"""
Verify a single frame from /tmp/smoke/video.mp4.

Prints frame shape, min/max pixel values, standard deviation,
and which warning branch (if any) the values trigger.

Usage:
    tests/venvs/video/bin/python tests/verify_frame.py
"""

import imageio
import numpy as np
import sys
from pathlib import Path

VIDEO_PATH = Path("/tmp/smoke/video.mp4")


def main():
    if not VIDEO_PATH.exists():
        print(f"[ERROR] Video not found: {VIDEO_PATH}")
        sys.exit(1)

    reader = imageio.get_reader(str(VIDEO_PATH))
    frame = reader.get_next_data()
    reader.close()

    shape = frame.shape
    min_val = int(frame.min())
    max_val = int(frame.max())
    std_val = float(np.std(frame))

    print(f"shape: {shape}")
    print(f"min:   {min_val}")
    print(f"max:   {max_val}")
    print(f"std:   {std_val:.14f}")

    # Warning branches
    warnings = []

    if min_val < 0:
        warnings.append("MIN_NEGATIVE — frame contains negative pixel values")
    elif min_val == 0:
        warnings.append("MIN_FLOOR — frame clamps to 0 (possible black border)")

    if max_val < 255:
        warnings.append("MAX_CEIL — frame max < 255, possible under-exposure or compression")
    elif max_val == 255:
        warnings.append("MAX_WHITE — frame touches full white (usual for uint8)")
    elif max_val > 255:
        warnings.append("OVERFLOW — max > 255, likely float unclipped")

    if std_val < 10:
        warnings.append("LOW_CONTRAST — standard deviation < 10, near-uniform frame")
    elif std_val > 80:
        warnings.append("HIGH_CONTRAST — standard deviation > 80, wide dynamic range")

    if not warnings:
        print("WARNING: none — values in expected range")
    else:
        for w in warnings:
            print(f"WARNING: {w}")

    print("\nDone.")


if __name__ == "__main__":
    main()