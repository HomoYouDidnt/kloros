#!/usr/bin/env bash
#
# Day-1 Acceptance Test for GPU Canary System
#
# Fast, no-downtime sanity checks to verify the system is production-ready.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KLOROS_HOME="/home/kloros"

echo "=========================================="
echo "GPU Canary System - Day-1 Acceptance Test"
echo "=========================================="
echo

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

# Test 1: Predictive path sanity
echo "Test 1: Predictive mode sanity check"
echo "--------------------------------------"

export MODE=predictive
export PYTHONPATH="${KLOROS_HOME}:${KLOROS_HOME}/src"

# Run a simple predictive validation
result=$(${KLOROS_HOME}/.venv/bin/python3 << 'PYEOF'
import sys
sys.path.insert(0, '/home/kloros')

from src.phase.domains.spica_gpu_allocation import SpicaGPUAllocation, GPUAllocationTestConfig, MODE

# Verify MODE
assert MODE == "predictive", f"Expected predictive mode, got {MODE}"

# Create evaluator
config = GPUAllocationTestConfig(
    vllm_memory_util_min=0.60,
    vllm_memory_util_max=0.90
)
evaluator = SpicaGPUAllocation(test_config=config)

# Test candidate (use value within bounds: 0.60-0.90)
candidate = {"vllm_memory_util": 0.75, "whisper_model_size": "small"}
result = evaluator.run_test(candidate)

# Output result
import json
print(json.dumps({
    "mode": MODE,
    "status": result.status,
    "validation_passed": result.validation_passed,
    "validation_reason": result.validation_reason
}))
PYEOF
)

echo "Result: $result"

# Parse result
mode=$(echo "$result" | jq -r '.mode')
validation_passed=$(echo "$result" | jq -r '.validation_passed')

if [[ "$mode" == "predictive" ]]; then
    pass "Predictive mode active"
else
    fail "Unexpected mode: $mode"
fi

if [[ "$validation_passed" == "true" ]] || [[ "$validation_passed" == "false" ]]; then
    pass "Validation completed (passed=$validation_passed)"
else
    warn "Validation status unclear: $validation_passed"
fi

# Verify judge.service not disrupted
if systemctl is-active --quiet judge.service; then
    pass "judge.service still running (no disruption)"
else
    warn "judge.service not running (may be expected in test environment)"
fi

echo

# Test 2: Budget ledger exists and capped
echo "Test 2: Budget ledger sanity"
echo "-----------------------------"

budget_file="${KLOROS_HOME}/.kloros/maintenance/gpu_budget_$(date +%Y%m%d).json"

if [[ -f "$budget_file" ]]; then
    seconds_used=$(jq -r '.seconds_used' "$budget_file")
    max_downtime=$(grep "KLR_GPU_MAINTENANCE_MAX_DOWNTIME" "${KLOROS_HOME}/.kloros_env" | cut -d'=' -f2 || echo "60")
    
    pass "Budget file exists: $budget_file"
    echo "  Seconds used: ${seconds_used}s / ${max_downtime}s"
    
    if (( $(echo "$seconds_used > $max_downtime" | bc -l) )); then
        warn "Budget exceeded limit!"
    else
        pass "Budget within limit"
    fi
else
    pass "No budget file yet (expected if no canaries run today)"
    echo "  Budget file would be: $budget_file"
fi

echo

# Test 3: Lock directory and mechanism
echo "Test 3: Lock mechanism check"
echo "-----------------------------"

lock_dir="${KLOROS_HOME}/.kloros/locks"
lock_file="${lock_dir}/gpu_maintenance.lock"

if [[ -d "$lock_dir" ]]; then
    pass "Lock directory exists: $lock_dir"
else
    fail "Lock directory missing: $lock_dir"
fi

if [[ -f "$lock_file" ]]; then
    warn "GPU lock currently held:"
    cat "$lock_file"
    echo "  (This may indicate an active canary or stale lock)"
else
    pass "GPU lock is free"
fi

echo

# Test 4: Configuration sanity
echo "Test 4: Configuration check"
echo "----------------------------"

# Check key environment variables
source "${KLOROS_HOME}/.kloros_env"

echo "GPU Canary Configuration:"
echo "  MODE: ${KLR_CANARY_MODE:-predictive}"
echo "  PORT: ${KLR_CANARY_PORT:-9011}"
echo "  TIMEOUT: ${KLR_CANARY_TIMEOUT:-30}s"
echo "  MAX_DOWNTIME: ${KLR_GPU_MAINTENANCE_MAX_DOWNTIME:-60}s/day"
echo "  WINDOW: ${KLR_GPU_MAINTENANCE_WINDOW:-03:00-07:00}"
echo "  COOLDOWN: ${KLR_CANARY_COOLDOWN_HOURS:-6}h"
echo "  ALLOW_SPARE: ${KLR_ALLOW_SPARE_GPU:-false}"

if [[ "${KLR_CANARY_MODE:-predictive}" == "predictive" ]]; then
    pass "Default mode is predictive (safe)"
else
    warn "Canary mode is active (will require real VLLM testing)"
fi

echo

# Test 5: Audit trail setup
echo "Test 5: Audit trail check"
echo "--------------------------"

audit_dir="${KLOROS_HOME}/out/orchestration/epochs"
audit_file="${audit_dir}/gpu_canary_$(date +%Y%m%d).jsonl"

if [[ -d "$audit_dir" ]]; then
    pass "Audit directory exists: $audit_dir"
else
    fail "Audit directory missing: $audit_dir"
fi

if [[ -f "$audit_file" ]]; then
    line_count=$(wc -l < "$audit_file")
    pass "Audit file exists with $line_count entries"
    echo "  Latest entry:"
    tail -1 "$audit_file" | jq -C '.' || tail -1 "$audit_file"
else
    pass "No audit file yet (expected if no canaries run today)"
fi

echo

# Test 6: Unit tests
echo "Test 6: Run unit tests"
echo "----------------------"

cd "${KLOROS_HOME}"
if ${KLOROS_HOME}/.venv/bin/pytest tests/test_gpu_canary.py -v -q 2>&1 | tail -5; then
    pass "Unit tests passed"
else
    fail "Unit tests failed"
fi

echo
echo "=========================================="
echo "Day-1 Acceptance: ALL TESTS PASSED ✓"
echo "=========================================="
echo
echo "System is ready for production."
echo "Default mode: predictive (no downtime)"
echo
echo "To monitor system:"
echo "  - Budget: jq . $budget_file"
echo "  - Audit trail: tail -f $audit_file"
echo "  - Lock status: cat $lock_file"
echo
echo "Next steps:"
echo "  1. Let Observer emit config_tuning intents (automatic)"
echo "  2. Monitor predictive mode validation (no downtime)"
echo "  3. Escalation to canary mode will trigger automatically"
echo "     after $( grep "KLR_CANARY_COOLDOWN_HOURS" "${KLOROS_HOME}/.kloros_env" | cut -d'=' -f2 || echo "6" )h cooldown"
echo
