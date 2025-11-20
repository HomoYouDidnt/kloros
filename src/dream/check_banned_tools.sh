#!/bin/bash
# Unit check: Fail if banned tools found in active D-REAM source

echo "Checking for banned utilities in src/dream/ Python source..."

BANNED_PATTERN="stress-ng|sysbench|stressapptest|STREAM\b|^stream|fio"

# Check only Python files, exclude artifacts/docs/backups
if rg -n "$BANNED_PATTERN" /home/kloros/src/dream/*.py /home/kloros/src/dream/**/*.py 2>/dev/null | grep -v "artifacts\|\.md\|scripts_backup\|regimes.yaml\|legacy_domains"; then
    echo "✗ FAILED: Found banned utilities in active D-REAM code"
    exit 1
else
    echo "✓ PASSED: No banned utilities in active D-REAM code"
    exit 0
fi
