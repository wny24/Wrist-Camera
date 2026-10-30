"""Approximate receiver-time pairing, NOT synchronized exposure timestamps.

Run after compare_fps.py. The 20 ms threshold is an acceptance rule, not
an accuracy guarantee: Luckfox encoding/transport delay is not calibrated.
"""

import argparse
import bisect
import csv
from pathlib import Path


def pair(luckfox, realsense, tolerance_s=0.020):
    times = [float(r["host_monotonic_seconds"]) for r in realsense]
    next_unused = 0
    for row in luckfox:
        t = float(row["host_monotonic_seconds"])
        index = bisect.bisect_left(times, t, lo=next_unused)
        candidates = [i for i in (index - 1, index) if next_unused <= i < len(times)]
        if not candidates:
            continue
        best = min(candidates, key=lambda i: abs(times[i] - t))
        if abs(times[best] - t) <= tolerance_s:
            yield (
                row["frame_number"],
                realsense[best]["frame_number"],
                (times[best] - t) * 1000,
            )
            next_unused = best + 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Benchmark output directory")
    parser.add_argument("--tolerance-ms", type=float, default=20)
    args = parser.parse_args()
    if args.tolerance_ms < 0:
        parser.error("tolerance must be nonnegative")
    root = args.directory

    def read(name):
        with (root / name).open() as f:
            return list(csv.DictReader(f))

    pairs = list(
        pair(
            read("luckfox_frames.csv"),
            read("d435i_frames.csv"),
            args.tolerance_ms / 1000,
        )
    )
    with (root / "approximate_host_pairs.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["luckfox_sample_index", "realsense_frame_number", "arrival_delta_ms"]
        )
        writer.writerows(pairs)
    print(
        f"{len(pairs)} one-to-one receiver-time pairs; exposure alignment is NOT verified."
    )
