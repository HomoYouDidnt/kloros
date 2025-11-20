#!/bin/bash
# Sync promotions - converts winners to promotions with apply_map
# Run this every ~5 minutes via cron or systemd timer

WINNERS_DIR="/home/kloros/artifacts/dream/winners"
PROMOTIONS_DIR="/home/kloros/artifacts/dream/promotions"
EMITTER="/home/kloros/src/dream/tools/emit_promotion.py"

mkdir -p "$PROMOTIONS_DIR"

# Helper function to check if winner params/fitness changed
has_winner_changed() {
    local winner_file="$1"
    local promo_file="$2"

    # If promotion doesn't exist, winner has "changed" (needs initial promotion)
    [ ! -f "$promo_file" ] && return 0

    # Extract winner params and fitness
    local winner_params=$(python3 -c "import json, sys; w=json.load(open('$winner_file')); print(json.dumps(w['best']['params'], sort_keys=True))" 2>/dev/null)
    local winner_fitness=$(python3 -c "import json, sys; w=json.load(open('$winner_file')); print(w['best']['fitness'])" 2>/dev/null)

    # Extract existing promotion params and fitness
    local promo_params=$(python3 -c "import json, sys; p=json.load(open('$promo_file')); print(json.dumps(p['winner']['params'], sort_keys=True))" 2>/dev/null)
    local promo_fitness=$(python3 -c "import json, sys; p=json.load(open('$promo_file')); print(p['winner']['fitness'])" 2>/dev/null)

    # Return 0 (changed) if params or fitness differ
    [ "$winner_params" != "$promo_params" ] || [ "$winner_fitness" != "$promo_fitness" ]
}

# Process each experiment's winner file
for experiment in rag_opt_baseline audio_latency_trim conv_quality_tune; do
    winner_file="$WINNERS_DIR/${experiment}.json"
    promo_file="$PROMOTIONS_DIR/${experiment}.promotion.json"

    if [ -f "$winner_file" ]; then
        # Only emit if winner params/fitness actually changed
        if has_winner_changed "$winner_file" "$promo_file"; then
            /home/kloros/.venv/bin/python3 "$EMITTER" "$experiment" "$winner_file" "$promo_file"
        fi
    fi
done

# tool_evolution is special - it tests configurations but doesn't create promotions yet
# LLM-guided code mutations will be added in future iteration
# For now, tool_evolution results are just logged for analysis
