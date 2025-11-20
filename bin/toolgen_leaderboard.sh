#!/usr/bin/env bash
#
# ToolGen Leaderboard: Extract top-N performers per spec from D-REAM metrics
#
# Usage: /home/kloros/bin/toolgen_leaderboard.sh [N] [output_file]
#
# Defaults: N=5, output=/home/kloros/logs/dream/toolgen_top5.json

set -euo pipefail

TOP_N="${1:-5}"
OUTPUT="${2:-/home/kloros/logs/dream/toolgen_top${TOP_N}.json}"
METRICS="/home/kloros/logs/dream/metrics.jsonl"

if [[ ! -f "$METRICS" ]]; then
    echo "Error: Metrics file not found: $METRICS" >&2
    exit 1
fi

# Ensure jq is installed
if ! command -v jq &>/dev/null; then
    echo "Error: jq is required but not installed" >&2
    exit 1
fi

echo "Generating ToolGen leaderboard (top-${TOP_N})..."
echo "  Input : $METRICS"
echo "  Output: $OUTPUT"

# Extract toolgen domain metrics, group by spec, sort by fitness, take top N
grep '"domain":"toolgen"' "$METRICS" 2>/dev/null | \
jq -s --argjson n "$TOP_N" \
'group_by(.spec_path)[] | sort_by(-.fitness)[:$n] | {
  spec: .[0].spec_path,
  top_n: [.[] | {
    epoch: .epoch,
    fitness: .fitness,
    impl: .impl_style,
    median_ms: .median_ms,
    stability: .components.stability,
    timestamp: .timestamp
  }]
}' | \
jq -s '.' > "$OUTPUT"

echo "✓ Leaderboard written to: $OUTPUT"
echo ""
echo "Preview (first entry):"
jq '.[0]' "$OUTPUT" 2>/dev/null || echo "(Empty or invalid JSON)"
