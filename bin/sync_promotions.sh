#!/usr/bin/env bash
# Sync promotions - converts winners to promotions for cross-epoch learning
# Run this every ~2 minutes via systemd timer

set -euo pipefail

WINNERS_DIR="/home/kloros/artifacts/dream/winners"
PROMOTIONS_DIR="/home/kloros/artifacts/dream/promotions"
EMITTER="/home/kloros/bin/emit_promotion.py"

mkdir -p "$PROMOTIONS_DIR"

# Helper function to check if winner has changed
has_winner_changed() {
    local winner_file="$1"
    local promo_file="$2"

    # If promotion doesn't exist, winner has "changed" (needs initial promotion)
    [[ ! -f "$promo_file" ]] && return 0

    # If winner file is newer than promotion, it has changed
    [[ "$winner_file" -nt "$promo_file" ]]
}

# ── ToolGen winners → promotion ────────────────────────────────────────────────
if [[ -f "$WINNERS_DIR/spica_toolgen.json" ]]; then
    winner_file="$WINNERS_DIR/spica_toolgen.json"
    promo_file="$PROMOTIONS_DIR/spica_toolgen.promotion.json"

    if has_winner_changed "$winner_file" "$promo_file"; then
        /home/kloros/.venv/bin/python3 "$EMITTER" "spica_toolgen" "$winner_file" "$promo_file"
    fi
fi
