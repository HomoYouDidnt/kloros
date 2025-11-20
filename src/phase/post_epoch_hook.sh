#!/bin/bash
# PHASE Post-Epoch Hook: Compute fitness and promote memory
# Call this after PHASE completes an epoch

set -euo pipefail

PYTHON=/usr/bin/python3
FITNESS_WRITER=/home/kloros/src/dream/fitness_writer.py
PROMOTER=/home/kloros/src/kloros_memory/promoter.py

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] PHASE post-epoch hook started" | logger -t phase-hook

# 1. Compute fitness from phase_report.jsonl
echo "Computing fitness..." | logger -t phase-hook
$PYTHON $FITNESS_WRITER || {
    echo "ERROR: Fitness computation failed" | logger -t phase-hook
    exit 1
}

# 2. Check promotion eligibility
echo "Checking memory promotion..." | logger -t phase-hook
RESULT=$($PYTHON $PROMOTER)
echo "$RESULT" | logger -t phase-hook

# 3. Log event
if echo "$RESULT" | grep -q '"promoted": true'; then
    echo "✓ Memory promoted" | logger -t phase-hook
else
    echo "○ Memory not promoted (gate not met)" | logger -t phase-hook
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] PHASE post-epoch hook completed" | logger -t phase-hook
