#!/usr/bin/env bash
#
# RepairLab Analytics: Track success rate of ToolGen→RepairLab handoffs
#
# Usage: /home/kloros/bin/repairlab_analytics.sh

QUEUE_DIR="/tmp/repairlab_queue/processed"

if [[ ! -d "$QUEUE_DIR" ]]; then
    echo "No processed handoffs found. Queue directory: $QUEUE_DIR"
    exit 0
fi

ok_count=$(find "$QUEUE_DIR" -name "*.ok" 2>/dev/null | wc -l)
fail_count=$(find "$QUEUE_DIR" -name "*.fail" 2>/dev/null | wc -l)
total=$((ok_count + fail_count))

if [[ $total -eq 0 ]]; then
    echo "No handoffs processed yet."
    exit 0
fi

success_rate=$(awk "BEGIN {printf \"%.1f\", ($ok_count / $total) * 100}")

echo "========================================"
echo "  RepairLab Handoff Analytics"
echo "========================================"
echo "Total handoffs: $total"
echo "  Success: $ok_count"
echo "  Failed : $fail_count"
echo "  Rate   : ${success_rate}%"
echo ""

# Show recent failures
recent_fails=$(find "$QUEUE_DIR" -name "*.fail" -mtime -1 2>/dev/null | wc -l)
if [[ $recent_fails -gt 0 ]]; then
    echo "Recent failures (last 24h): $recent_fails"
    echo "Latest 5 failures:"
    find "$QUEUE_DIR" -name "*.fail" -printf "%T+ %p\n" | sort -r | head -5 | \
        while read -r ts path; do
            basename=$(basename "$path" .fail.json)
            echo "  - $basename"
        done
fi

echo "========================================"
