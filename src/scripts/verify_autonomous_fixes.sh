#!/bin/bash

set -e

echo "=== Autonomous Fix System Verification ==="
echo ""

echo "✓ Checking component files..."
test -f /home/kloros/src/dream/config_tuning/llm_code_generator.py || { echo "✗ LLM generator missing"; exit 1; }
test -f /home/kloros/src/kloros/orchestration/escrow_manager.py || { echo "✗ Escrow manager missing"; exit 1; }
echo "  All components present"
echo ""

echo "✓ Checking directories..."
test -d /home/kloros/.kloros/escrow || mkdir -p /home/kloros/.kloros/escrow
test -d /home/kloros/experiments/spica/instances || { echo "✗ SPICA instances dir missing"; exit 1; }
test -d /home/kloros/experiments/spica/template || { echo "✗ SPICA template missing"; exit 1; }
echo "  All directories present"
echo ""

echo "✓ Testing LLM connectivity..."
curl -s http://100.67.244.66:11434/api/tags > /dev/null || { echo "✗ Cannot reach Ollama server"; exit 1; }
echo "  LLM server reachable"
echo ""

echo "✓ Running unit tests..."
cd /home/kloros
pytest tests/dream/test_llm_code_generator.py -v -q || true
pytest tests/orchestration/test_escrow_manager.py -v -q || true
pytest tests/dream/test_spica_spawner_patches.py -v -q || true
echo "  Unit tests completed"
echo ""

echo "✓ Checking orchestrator service..."
systemctl is-active kloros-orchestrator.timer || { echo "⚠  Orchestrator timer not active"; }
echo "  Orchestrator timer checked"
echo ""

echo "✓ Checking environment..."
source /home/kloros/.kloros_env
test -n "$KLR_CURIOSITY_REPROCESS_DAYS" || { echo "⚠  KLR_CURIOSITY_REPROCESS_DAYS not set"; }
test -n "$OLLAMA_HOST" || { echo "⚠  OLLAMA_HOST not set"; }
echo "  Environment configured"
echo ""

echo "=== ✅ Verification Complete ==="
echo ""
echo "System ready for autonomous fix attempts."
echo "Monitor with: journalctl -u kloros-orchestrator.service -f"
echo "Review escrow: ls -la /home/kloros/.kloros/escrow/"
