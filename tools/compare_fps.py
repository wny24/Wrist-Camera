"""Measure RGB frame timing concurrently; no frame resampling or duplication."""

import argparse
from datetime import datetime
from settings import ROOT, comparison_args, resolve_comparison, ensure_forward
import concurrent.futures
import csv
import json
import subprocess
import time
from pathlib import Path

import av
import numpy as np
import pyrealsense2 as rs


def summarize(rows, info):
    if len(rows) < 2:
        raise ValueError("Not enough frames to measure FPS")
    arr = np.asarray(rows)
    src, host = arr[:, 0], arr[:, 1]
    delta = np.diff(src) * 1000
    arrival = np.diff(host) * 1000
    info.update(
        frames=len(rows),
        source_span_s=float(src[-1] - src[0]),
        source_fps=float((len(rows) - 1) / (src[-1] - src[0])),
        received_fps=float((len(rows) - 1) / (host[-1] - host[0])),
        source_interval_ms={
            "median": float(np.median(delta)),
            "p99": float(np.percentile(delta, 99)),
            "max": float(delta.max()),
        },
        arrival_interval_ms={
            "median": float(np.median(arrival)),
            "p99": float(np.percentile(arrival, 99)),
            "max": float(arrival.max()),
        },
        source_gaps_over_50ms=int(np.sum(delta > 50)),
        arrival_gaps_over_50ms=int(np.sum(arrival > 50)),
        nonincreasing_source_timestamps=int(np.sum(delta <= 0)),
    )
    ready = arr[:, 3]
    info["numpy_ready_fps"] = float((len(rows) - 1) / (ready[-1] - ready[0]))
    info["numpy_conversion_p99_ms"] = float(np.percentile((ready - host) * 1000, 99))
    return info


def realsense(args):
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(args.realsense_serial)
    config.enable_stream(rs.stream.color, 1920, 1080, rs.format.rgb8, 30)
    profile = pipeline.start(config)
    sensor = profile.get_device().first_color_sensor()
    old_priority = None
    rows = []
    info = {
        "serial": args.realsense_serial,
        "resolution": [1920, 1080],
        "requested_fps": 30,
        "format": "RGB8 (SDK conversion from YUYV)",
        "depth_enabled": False,
    }
    try:
        info["rgb_supports_inter_cam_sync_mode"] = sensor.supports(
            rs.option.inter_cam_sync_mode
        )
        if sensor.supports(rs.option.global_time_enabled):
            info["global_time_enabled"] = sensor.get_option(
                rs.option.global_time_enabled
            )
        if sensor.supports(rs.option.auto_exposure_priority):
            old_priority = sensor.get_option(rs.option.auto_exposure_priority)
            sensor.set_option(rs.option.auto_exposure_priority, 0)
            info["auto_exposure_priority_during_test"] = 0
            info["auto_exposure_priority_before_test"] = old_priority
        for name in ("enable_auto_exposure", "exposure", "gain"):
            option = getattr(rs.option, name)
            if sensor.supports(option):
                info[name] = sensor.get_option(option)
        start = time.monotonic()
        while time.monotonic() - start < args.warmup + args.duration:
            frame = pipeline.wait_for_frames(5000).get_color_frame()
            now = time.monotonic()
            rgb = np.asanyarray(frame.get_data()).copy()
            ready = time.monotonic()
            assert rgb.shape == (1080, 1920, 3)
            if now - start < args.warmup:
                continue
            rows.append(
                (frame.get_timestamp() / 1000, now, frame.get_frame_number(), ready)
            )
            info["timestamp_domain"] = str(frame.get_frame_timestamp_domain())
            if "frame_metadata_sample" not in info:
                info["frame_metadata_sample"] = {}
                for name in (
                    "frame_timestamp",
                    "sensor_timestamp",
                    "backend_timestamp",
                    "time_of_arrival",
                    "actual_exposure",
                    "actual_fps",
                ):
                    key = getattr(rs.frame_metadata_value, name, None)
                    if key is not None and frame.supports_frame_metadata(key):
                        info["frame_metadata_sample"][name] = frame.get_frame_metadata(
                            key
                        )
        info["missing_frame_numbers"] = sum(
            max(0, b[2] - a[2] - 1) for a, b in zip(rows, rows[1:])
        )
    finally:
        try:
            if old_priority is not None:
                sensor.set_option(rs.option.auto_exposure_priority, old_priority)
        finally:
            pipeline.stop()
    return rows, summarize(rows, info)


def luckfox(args):
    rows = []
    with av.open(
        f"rtsp://127.0.0.1:{args.port}/live/{args.stream}",
        options={"rtsp_transport": "tcp"},
        timeout=(10, 5),
    ) as container:
        stream = container.streams.video[0]
        info = {
            "serial": args.luckfox_serial,
            "resolution": [stream.width, stream.height],
            "advertised_fps": str(stream.average_rate),
            "format": stream.codec_context.name,
            "timestamp_domain": "RTSP presentation timestamps; not exposure timestamps",
        }
        start = time.monotonic()
        for frame in container.decode(stream):
            now = time.monotonic()
            rgb = frame.to_ndarray(format="rgb24")
            ready = time.monotonic()
            assert rgb.shape == (1080, 1920, 3)
            if now - start < args.warmup:
                continue
            if now - start >= args.warmup + args.duration:
                break
            if frame.pts is None:
                raise RuntimeError("Missing Luckfox PTS")
            rows.append((float(frame.pts * frame.time_base), now, len(rows), ready))
    return rows, summarize(rows, info)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    comparison_args(parser)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--warmup", type=float, default=5)
    parser.add_argument("--output", type=Path)
    try:
        args = resolve_comparison(parser.parse_args())
        if args.duration <= 0 or args.warmup < 0:
            raise ValueError("duration must be positive and warmup nonnegative")
        ensure_forward(args.luckfox_serial, args.port)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    output = args.output or ROOT / "output" / datetime.now().strftime(
        "benchmark-%Y%m%d-%H%M%S-%f"
    )
    output.mkdir(parents=True, exist_ok=False)
    print(f"Saving results to {output}", flush=True)
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(fn, args): name
            for name, fn in [("d435i", realsense), ("luckfox", luckfox)]
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                rows, results[name] = future.result()
                with (output / (name + "_frames.csv")).open("w") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "source_seconds",
                            "host_monotonic_seconds",
                            "frame_number",
                            "numpy_ready_monotonic_seconds",
                        ]
                    )
                    writer.writerows(rows)
            except Exception as exc:
                results[name] = {"error": str(exc)}
            print(name, json.dumps(results[name], ensure_ascii=False), flush=True)
    (output / "fps_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )

    raise SystemExit(1 if any("error" in result for result in results.values()) else 0)
