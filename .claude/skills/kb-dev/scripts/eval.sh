#!/usr/bin/env bash
# Thin wrapper: run the repo's scripts/eval.sh from any directory, so Claude composes instead of rebuilding.
# usage: eval.sh [--public|--dev|--locked|--quick] [--out DIR]
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)" || exit 1
cd "$ROOT" && exec bash scripts/eval.sh "$@"
