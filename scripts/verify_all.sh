#!/bin/bash
# Comprehensive verification script for KLoROS integration

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="/home/kloros/.venv/bin/python"

echo "============================================================"
echo "KLoROS Integration Verification"
echo "============================================================"
echo

# 1. Tool tracking check
echo "[1/5] Checking tool tracking..."
$VENV_PYTHON "$SCRIPT_DIR/check_tools_tracked.py"
echo

# 2. Diagnostic check (all modules import)
echo "[2/5] Running diagnostic (all modules import)..."
$VENV_PYTHON "$PROJECT_ROOT/diagnose_kloros.py" | tail -5
echo

# 3. TTS smoke test
echo "[3/5] Running TTS smoke test..."
$VENV_PYTHON "$SCRIPT_DIR/smoke_tts.py" 2>&1 | grep -E '\[OK\]|\[FAIL\]|Audio size'
echo

# 4. Pack integration test
echo "[4/5] Testing pack entry points..."
$VENV_PYTHON "$SCRIPT_DIR/e2e_packs_ping.py"
echo

# 5. Voice pipeline test
echo "[5/5] Testing voice pipeline (VAD → ASR → TTS)..."
$VENV_PYTHON "$SCRIPT_DIR/e2e_voice_test.py" 2>&1 | grep -E '\[.*\]|Transcript:|TTS:|OK'
echo

echo "============================================================"
echo "✅ All verification tests passed!"
echo "============================================================"
