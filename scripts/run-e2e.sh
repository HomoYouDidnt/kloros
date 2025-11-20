#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${PYTHONPATH:-}:$(pwd):$(pwd)/src:$(pwd)/kloros-e2e"
exec "${PYTEST_BIN:-/home/kloros/.venv/bin/python3}" -m pytest -q kloros-e2e/tests/e2e -k "not slow" ${PYTEST_ADDOPTS:-}
