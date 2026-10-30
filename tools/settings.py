"""Portable local configuration and conservative ADB forwarding."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def load_settings(path=None):
    path = Path(path or os.environ.get("WRIST_CAM_CONFIG", ROOT / "config.local.json"))
    if not path.is_file():
        raise ValueError(
            f"Missing {path}; copy config.example.json and enter device serials first."
        )
    data = json.loads(path.read_text())
    cameras = data.get("luckfox", [])
    if not cameras:
        raise ValueError("Configure at least one Luckfox camera")
    ports, serials = set(), set()
    for camera in cameras:
        serial = camera.get("serial", "")
        port, stream = camera.get("port"), camera.get("stream")
        if not isinstance(serial, str) or not serial or serial.startswith("REPLACE_"):
            raise ValueError("Enter the Luckfox ADB serial in config.local.json")
        if not isinstance(port, int) or not 1024 <= port <= 65535 or port in ports:
            raise ValueError(
                "Each Luckfox camera requires a unique port in 1024..65535"
            )
        if serial in serials:
            raise ValueError("Each Luckfox camera requires a unique serial")
        if stream not in (0, 1, 2):
            raise ValueError("stream must be 0, 1 or 2")
        ports.add(port)
        serials.add(serial)
    return data


def comparison_args(parser):
    parser.add_argument(
        "--config", help="Configuration file (default: config.local.json)"
    )
    parser.add_argument(
        "--camera", type=int, default=0, help="Zero-based Luckfox index"
    )
    parser.add_argument("--luckfox-serial")
    parser.add_argument("--realsense-serial")
    parser.add_argument("--port", type=int)
    parser.add_argument("--stream", type=int)


def resolve_comparison(args):
    settings = load_settings(args.config)
    if not 0 <= args.camera < len(settings["luckfox"]):
        raise ValueError("Invalid --camera index")
    camera = settings["luckfox"][args.camera]
    args.luckfox_serial = args.luckfox_serial or camera["serial"]
    args.port = args.port if args.port is not None else camera["port"]
    args.stream = args.stream if args.stream is not None else camera["stream"]
    args.realsense_serial = args.realsense_serial or settings.get("realsense", {}).get(
        "serial", ""
    )
    if not args.realsense_serial or args.realsense_serial.startswith("REPLACE_"):
        raise ValueError("Enter the RealSense serial in config.local.json")
    if not 1024 <= args.port <= 65535 or args.stream not in (0, 1, 2):
        raise ValueError("Invalid --port or --stream")
    return args


def ensure_forward(serial, port):
    """Return after the chosen board is online; never overwrite another forward."""
    state = subprocess.run(
        ["adb", "-s", serial, "get-state"],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    ).stdout.strip()
    if state != "device":
        raise RuntimeError(f"{serial} is not online")
    lines = subprocess.run(
        ["adb", "forward", "--list"],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    ).stdout.splitlines()
    expected = [serial, f"tcp:{port}", "tcp:554"]
    matches = [
        line.split()
        for line in lines
        if len(line.split()) == 3 and line.split()[1] == expected[1]
    ]
    if matches:
        if matches[0] != expected:
            raise ValueError(
                f"Port {port} belongs to another ADB forward; choose a different port"
            )
        return
    subprocess.run(
        ["adb", "-s", serial, "forward", "--no-rebind", f"tcp:{port}", "tcp:554"],
        capture_output=True,
        timeout=3,
        check=True,
    )
