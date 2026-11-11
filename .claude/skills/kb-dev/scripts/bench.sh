#!/usr/bin/env bash
# Thin wrapper: run the repo's scripts/bench.py from any directory, so Claude composes instead of rebuilding.
# usage: bench.sh [--n 200]
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)" || exit 1
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY=python3; fi
cd "$ROOT" && exec "$PY" scripts/bench.py "$@"
