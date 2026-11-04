# Camera Usage Guide

Before installing the camera, board, and wrist mount for the first time, read the [hardware assembly guide](hardware-assembly-zh.md). Complete the wiring and mechanical checks before running the software.

Run `bash scripts/setup.sh`, then enter the device serials in `config.local.json`. Find the Luckfox serial with `adb devices -l` and the RealSense serial with RealSense Viewer or `rs-enumerate-devices`. Devices are identified by serial number: changing USB cables or ports does not require a configuration change, but replacing a board does.

## Live Comparison

RealSense is optional and is not required to preview the wrist camera alone. To compare the cameras, keep the `luckfox` entry and add `realsense` in `config.local.json`:

```json
{
  "luckfox": [
    {"name": "Wrist camera", "serial": "YOUR_ADB_SERIAL", "port": 18554, "stream": 1}
  ],
  "realsense": {"serial": "YOUR_REALSENSE_SERIAL"}
}
```

The tested device is a D435i using RGB only, with depth disabled. Ensure that the RealSense SDK and USB permissions allow device access.

Connect Luckfox and RealSense, open a terminal on a Linux desktop, and run from the repository root:

```bash
bash scripts/view.sh
```

The window shows Luckfox and RealSense color streams side by side, both targeting 1080p30.

- `0`: show both streams; `1` / `2`: enlarge either stream.
- `F`: toggle fullscreen; `S`: save full-resolution images and timestamps to `output/snapshots/`.
- `Q` / `Esc`: exit and release the devices.

Pause RealSense capture in other applications first to avoid device contention. The displayed FPS measures RGB-array delivery, not screen refresh rate. `RGB age` is not total exposure-to-display latency. Each camera displays its latest frame; simultaneous exposure is not guaranteed. The application retries after disconnects and clearly marks old frames as STALE.

## Luckfox-Only Preview and Temperature

```bash
bash scripts/play.sh
```

This launcher uses the original CameraPlayer FFplay window and supports multiple Luckfox devices. It reads each board's SoC temperature through ADB without requiring an SSH password. Assign a different local port to each camera.

The verified 30 fps configuration uses `/live/1` at 1920 × 1080. The original main stream, `/live/0`, may still run at 25 fps. Check and configure a new board using the [30 fps configuration guide](luckfox-30fps.md).

## Measuring Frame Rate

Close the comparison window first, then run:

```bash
bash scripts/benchmark.sh --duration 60 --warmup 5
```

Results are saved to a new `output/benchmark-*` directory, including a JSON summary and per-frame CSV files. The Python readers produce RGB NumPy arrays without frame interpolation. Measure again after adding algorithmic processing to the capture pipeline.

## Timestamp Pairing and Headless Checks

Replace the example directory below with the directory created by your benchmark:

```bash
bash scripts/pair.sh output/benchmark-YYYYMMDD-HHMMSS-ffffff --tolerance-ms 20
```

Pairing selects the nearest frames by host receive time, using each frame at most once. The 20 ms tolerance is a selection threshold, not exposure-synchronization accuracy. See the [timestamp guide](timestamps.md).

Without a graphical desktop, you can check the same capture workers using:

```bash
bash scripts/view.sh --headless-seconds 12
```

## Connection Troubleshooting

Check device serials, USB data cables, power, and competing applications first. The default startup wait is 45 seconds. After the physical connection recovers, the monitor restores ADB forwarding. If the kernel reports USB descriptor errors or over-current conditions, inspect the cables and power supply; software retries alone cannot resolve these problems.

Local configuration, runtime logs, images, complete board INI backups, and virtual environments are excluded from Git. Full INI files may contain account settings; keep them locally under `output/`.
