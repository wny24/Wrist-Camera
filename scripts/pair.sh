#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ! -x "$project_root/.venv/bin/python" ]]; then
    echo 'Run bash scripts/setup.sh first.' >&2
    exit 1
fi
exec "$project_root/.venv/bin/python" "$project_root/tools/pair_by_host_time.py" "$@"
