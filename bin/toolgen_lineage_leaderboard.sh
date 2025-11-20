#!/usr/bin/env bash
# Usage: toolgen_lineage_leaderboard.sh [N] [OUT_JSON]
set -euo pipefail
N="${1:-5}"
OUT="${2:-/home/kloros/logs/dream/toolgen_lineage_top.json}"
MET="/home/kloros/logs/dream/metrics.jsonl"

# Filter ToolGen metrics, group by lineage, pick top-N by fitness per lineage
jq -sr --argjson N "$N" '
  def topn(n; arr): (arr | sort_by(-.fitness))[0:n];
  [ .[] | select(.domain=="toolgen") ] as $all
  | ($all | group_by(.lineage) | map({
      lineage: (.[0].lineage // "unknown"),
      top: topn($N; [ .[] | {epoch, fitness, impl_style, spec: (.spec_path | split("/")[-1]), median_ms, stability, meta_repair} ])
    }))' "$MET" > "$OUT"

echo "Wrote $OUT"
