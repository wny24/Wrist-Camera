#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/wrist-cam-view-$UID.lock"
if ! flock -n 9; then
    echo 'The comparison viewer is already running.' >&2
    exit 1
fi
if [[ ! -x "$project_root/.venv/bin/python" ]]; then
    echo 'Run bash scripts/setup.sh first.' >&2
    exit 1
fi
exec "$project_root/.venv/bin/python" "$project_root/tools/live_compare.py" "$@"
