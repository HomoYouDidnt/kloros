#!/bin/bash
# Quick start script for Phase 1 E2E tests

set -e

cd /home/kloros/kloros-e2e

echo "=== KLoROS E2E Test Setup ==="
echo

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo
echo "✅ Setup complete!"
echo
echo "To run tests:"
echo "  1. In terminal 1: python /home/kloros/ingress/http_text.py"
echo "  2. In terminal 2: cd /home/kloros/kloros-e2e && source .venv/bin/activate && pytest -v"
echo
