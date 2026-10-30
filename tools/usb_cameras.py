"""Connect configured USB cameras, optionally run the FFplay viewer and reconnect."""

import argparse
import signal
import subprocess
import sys
import time

from settings import ROOT, ensure_forward, load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument(
        "--view",
        action="store_true",
        help="Run the original FFplay-based viewer with ADB temperature",
    )
    parser.add_argument(
        "--wait", type=float, default=45, help="Initial connection timeout"
    )
    args = parser.parse_args()
    try:
        cameras = load_settings(args.config)["luckfox"]
    except ValueError as exc:
        parser.error(str(exc))
    if args.wait < 0:
        parser.error("--wait must be nonnegative")
    players = []
    last = {}
    started = False
    deadline = time.monotonic() + args.wait
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        while True:
            ready = 0
            for index, camera in enumerate(cameras):
                url = f"rtsp://127.0.0.1:{camera['port']}/live/{camera['stream']}"
                try:
                    ensure_forward(camera["serial"], camera["port"])
                    status = f"Ready: {url}"
                    ready += 1
                except ValueError as exc:
                    print(exc, file=sys.stderr)
                    return 1
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    status = "Waiting for USB / ADB"
                if last.get(index) != status:
                    print(
                        f"{camera.get('name', camera['serial'])}: {status}", flush=True
                    )
                    last[index] = status
            if not started and ready == len(cameras):
                started = True
                if args.view:
                    for camera in cameras:
                        url = (
                            f"rtsp://127.0.0.1:{camera['port']}/live/{camera['stream']}"
                        )
                        players.append(
                            subprocess.Popen(
                                [
                                    sys.executable,
                                    str(ROOT / "player/player.py"),
                                    "--url",
                                    url,
                                    "--transport",
                                    "tcp",
                                    "--adb-serial",
                                    camera["serial"],
                                ]
                            )
                        )
                elif not args.watch:
                    return 0
            if not started and time.monotonic() >= deadline:
                print(
                    "Connection timeout: check USB data cables, power, and device serials",
                    file=sys.stderr,
                )
                return 1
            if players and all(p.poll() is not None for p in players):
                return 0 if all(p.returncode == 0 for p in players) else 1
            time.sleep(2)
    except KeyboardInterrupt:
        return 0
    finally:
        for process in players:
            if process.poll() is None:
                process.terminate()
        for process in players:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
