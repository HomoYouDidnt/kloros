#!/usr/bin/env bash
set -euo pipefail
TARGET="/home/kloros"
echo "==> Installing Deus Ex Machina v2 Add-On into $TARGET"
mkdir -p "$TARGET/dream/experiments" "$TARGET/dream/golden" "$TARGET/scripts" "$TARGET/metrics" "$TARGET/systemd"
cp -f "./dream/experiments/rag_quality.yaml"  "$TARGET/dream/experiments/rag_quality.yaml"
cp -f "./dream/golden/rag_golden.json"       "$TARGET/dream/golden/rag_golden.json"
cp -f "./dream/run_rag_quality.py"           "$TARGET/dream/run_rag_quality.py"
cp -f "./scripts/metrics.sh"                 "$TARGET/scripts/metrics.sh"
cp -f "./scripts/metrics_dashboard.py"       "$TARGET/scripts/metrics_dashboard.py"
cp -f "./systemd/kloros-dream.service"       "$TARGET/systemd/kloros-dream.service"
chmod +x "$TARGET/scripts/metrics.sh"
echo "==> Install complete."
