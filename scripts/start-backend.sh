#!/usr/bin/env bash
# Start the Eventra backend. Uses FastAPI+uvicorn when installed, otherwise the
# zero-dependency stdlib server.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN=python

export PYTHONPATH="$PWD"
exec "$PYTHON_BIN" backend/run.py --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
