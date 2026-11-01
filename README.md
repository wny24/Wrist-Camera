# Wrist Cam

Python tools for a Luckfox Pico / SC3336 USB wrist camera, with a live side-by-side RealSense RGB comparison, measured FPS, timestamps, and reconnect support.

The tested configuration delivers **1920 × 1080 at approximately 30 fps** from Luckfox's buffered secondary stream. The RealSense comparison uses a **D435i RGB stream**, also requested at 1080p30; depth is not enabled. Matching resolution and nominal FPS does not synchronize exposures or match optics.

## Setup

For the printed wrist mount, parts list, wiring and assembly checks, see the [中文硬件组装指南](docs/hardware-assembly-zh.md).

Tested on Linux x86-64 with Python 3.12. A graphical desktop is required for the viewers; benchmarks can run without one.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and OS dependencies. On Ubuntu:

   ```bash
   sudo apt install adb ffmpeg fonts-dejavu-core python3-tk
   ```

2. Clone and install the locked Python environment:

   ```bash
   git clone git@github.com:IEILab/wrist-cam.git
   cd wrist-cam
   bash scripts/setup.sh
   ```

3. Edit `config.local.json` with your device serials. This local file is ignored by Git. Find Luckfox serials with `adb devices -l`; find RealSense serials with `rs-enumerate-devices` or RealSense Viewer. The RealSense SDK and USB permissions must allow access to the device.

   ```json
   {
     "luckfox": [
       {"name": "Wrist camera", "serial": "YOUR_ADB_SERIAL", "port": 18554, "stream": 1}
     ],
     "realsense": {"serial": "YOUR_REALSENSE_SERIAL"}
   }
   ```

The existing 25 fps factory profile often uses `/live/0`. The tested 1080p30 profile uses `/live/1`. See [camera configuration](docs/luckfox-30fps.md) before changing firmware settings.

## Live side-by-side comparison

Connect both devices with USB data cables. Pause capture in other camera applications, then run:

```bash
bash scripts/view.sh
```

| Key | Action |
| --- | --- |
| `0` | Both cameras side by side |
| `1` / `2` | Enlarge Luckfox / RealSense |
| `F` | Toggle fullscreen |
| `S` | Save original-resolution PNGs and timestamps under `output/snapshots/` |
| `Q` / `Esc` | Close and release cameras |

The window displays independent latest frames, actual RGB-array delivery FPS, and stale-frame status. Display resizing preserves aspect ratio. Old frames are not queued for display. `RGB age` measures time since the RGB array was ready, **not capture-to-display latency**. Snapshots are not exposure-synchronized.

The live viewer uses PyAV for H.265 RTSP decoding and `pyrealsense2` for RealSense RGB. It automatically creates/restores the selected Luckfox ADB forward without resetting the global ADB server or overwriting another device's forward. It retries unavailable streams. RealSense exposure-priority settings are restored when the stream closes normally.

## Python FPS benchmark

Close the live comparison first so RealSense is available:

```bash
bash scripts/benchmark.sh --duration 60 --warmup 5
```

Both Python readers run concurrently and actually produce RGB NumPy arrays. Each reader warms up before its measurement window. No resampling or frame interpolation is applied. A new `output/benchmark-*` directory contains:

- `fps_results.json`: source-timeline FPS, receive FPS, NumPy-ready FPS, interval percentiles and gap counts.
- `luckfox_frames.csv`, `d435i_frames.csv`: source timestamps, host monotonic timestamps, frame numbers/sample indexes and NumPy-ready times.

The test exits nonzero if either reader fails. `--output PATH` selects a **new** result directory. `--config PATH` selects another device configuration; `--camera 1` selects the second Luckfox entry (indexes start at zero).

[Measured results](docs/benchmark-results.md) include one 60-second RGB-array run: approximately 30.00 fps for Luckfox and 29.89 fps for D435i, with five D435i frame-number gaps. These are short-run observations on one host, not a throughput guarantee.

## Timestamp pairing

```bash
bash scripts/pair.sh output/benchmark-YYYYMMDD-HHMMSS-ffffff --tolerance-ms 20
```

This produces one-to-one nearest **host receive-time** pairs without reusing frames. The tolerance is a selection threshold, not exposure-synchronization accuracy. RealSense `global_time` and Luckfox RTSP PTS are different time domains and must not be subtracted directly. See [timestamp limitations](docs/timestamps.md).

## Luckfox-only viewing and multiple cameras

```bash
bash scripts/usb.sh             # Wait up to 45 seconds and configure forwards
bash scripts/usb.sh --watch     # Continue restoring forwards after disconnects
bash scripts/play.sh            # FFplay-based viewer with ADB SoC temperature
```

Add Luckfox entries with unique serials and local ports to `config.local.json` to use multiple cameras. The FFplay viewer opens one window per entry. The Python comparison selects one Luckfox entry plus one RealSense. USB connector position does not determine identity; the board serial does.

The original CameraPlayer v5.1 code supplied for this project is retained in `player/`, with diagnostic, temperature and reconnect tests in `tests/player/`. It also supports optional SSH temperature retrieval, but the USB launcher uses ADB and requires no SSH password.

## Project guide

| Documentation | Contents |
| --- | --- |
| [Hardware assembly (中文)](docs/hardware-assembly-zh.md) | Parts, printing, wiring and wrist installation |
| [Quick start (中文)](docs/usage-zh.md) | Preview, device configuration and troubleshooting |
| [1080p30 configuration](docs/luckfox-30fps.md) | Tested firmware settings and rollback |
| [Benchmark results](docs/benchmark-results.md) | Measured FPS and test conditions |
| [Timestamps](docs/timestamps.md) | Time domains and pairing limitations |
| [Hardware files](hardware/README.md) | CAD, simulation scenes, rendering and model attribution |

```text
configs/       Shared camera profiles
docs/          Guides and documentation images
hardware/      CAD, simulation, rendering tools and third-party licenses
player/        CameraPlayer runtime modules
scripts/       Shell entry points for setup, viewing and benchmarks
tests/         Tool tests and CameraPlayer tests
tools/         Capture, configuration and timestamp utilities
```

`config.example.json` is the device-configuration template; edit the ignored `config.local.json` for your own devices. Generated captures, results and board backups belong in the ignored `output/` directory. Python dependencies are declared in `pyproject.toml` and locked in `uv.lock`; optional hardware-rendering dependencies are separate in `hardware/requirements-render.txt`.

## Development and troubleshooting

```bash
uv sync --locked
uv run pytest
bash scripts/view.sh --headless-seconds 12  # Same capture workers, no GUI
```

If a camera is missing, check `adb devices -l`, cables, power and competing viewers. USB descriptor errors and over-current reports require checking the physical connection; software reconnects cannot fix faulty power or cables. Set `WRIST_CAM_CONFIG` or pass `--config` to select a different local configuration.

Runtime images, raw frame logs, complete board configuration backups, virtual environments and device-specific configuration are intentionally ignored. Do not commit full RKIPC INI files: they can contain account settings. [中文快速使用说明](docs/usage-zh.md)
