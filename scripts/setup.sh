#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'; exit 1; }
uv sync --locked
if [[ ! -f config.local.json ]]; then
    cp config.example.json config.local.json
    echo 'Edit config.local.json with your camera serials before starting.'
fi
.venv/bin/python -c 'import tkinter, av, numpy, pyrealsense2; print("Python dependencies ready")'
command -v adb >/dev/null || echo 'Install adb to use USB cameras.'
command -v ffplay >/dev/null || echo 'Optional FFplay viewer: install ffmpeg.'
