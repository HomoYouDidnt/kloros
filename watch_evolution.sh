#!/bin/bash
# Evolution Dashboard - The Exciting Bits Only

clear
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           D-REAM EVOLUTION DASHBOARD - LIVE                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

while true; do
    tput cup 4 0

    echo "━━━━━━━━━━━━━━━━━━━━━━ FITNESS PROGRESSION ━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Show recent fitness scores (the exciting part!)
    echo "Recent Experiments (last 10):"
    tail -10 /home/kloros/logs/dream/*.jsonl 2>/dev/null | \
        jq -r 'select(.fitness) | "\(.experiment // "unknown") | fitness: \(.fitness | tostring | .[0:6]) | params: \(.params | to_entries[0:2] | map("\(.key)=\(.value)") | join(", "))"' 2>/dev/null | \
        tail -10 || echo "  No recent experiments"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━ WINNERS & PROMOTIONS ━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Show recent winners
    echo "Latest Winners:"
    ls -lt /home/kloros/artifacts/dream/winners/*.json 2>/dev/null | head -3 | while read line; do
        file=$(echo $line | awk '{print $NF}')
        if [ -f "$file" ]; then
            name=$(basename "$file" .json)
            fitness=$(jq -r '.best.fitness // "N/A"' "$file" 2>/dev/null)
            echo "  🏆 $name | fitness: $fitness"
        fi
    done

    echo ""

    # Show recent promotions
    echo "Recent Deployments:"
    ls -lt /home/kloros/artifacts/dream/promotions_ack/*.json 2>/dev/null | head -3 | while read line; do
        file=$(echo $line | awk '{print $NF}')
        if [ -f "$file" ]; then
            timestamp=$(stat -c %y "$file" | cut -d. -f1)
            name=$(basename "$file" .ack.json)
            status=$(jq -r '.status // "unknown"' "$file" 2>/dev/null)
            echo "  🚀 $timestamp | $name | $status"
        fi
    done

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━ LIVE ACTIVITY ━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Show what's happening NOW
    observer_running=$(ps aux | grep -v grep | grep "kloros.observer.run" | wc -l)
    orchestrator_running=$(ps aux | grep -v grep | grep "kloros.orchestration" | wc -l)

    echo "System Status:"
    [ $observer_running -gt 0 ] && echo "  👁️  Observer: RUNNING" || echo "  👁️  Observer: STOPPED"
    [ $orchestrator_running -gt 0 ] && echo "  🎯 Orchestrator: RUNNING" || echo "  🎯 Orchestrator: STOPPED"

    # Count active SPICA instances
    spica_count=$(ls -d /home/kloros/experiments/spica/instances/spica-* 2>/dev/null | wc -l)
    echo "  🧬 SPICA Instances: $spica_count"

    # Show intent queue depth
    intent_count=$(ls /home/kloros/.kloros/intents/*.json 2>/dev/null | wc -l)
    echo "  📋 Pending Intents: $intent_count"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━ PARAMETER DIVERSITY ━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Show parameter space exploration
    echo "Recent Parameter Combinations (unique in last 20 experiments):"
    tail -20 /home/kloros/logs/dream/spica_system_health.jsonl 2>/dev/null | \
        jq -r 'select(.params) | .params | to_entries | map("\(.key)=\(.value)") | join(" | ")' 2>/dev/null | \
        sort -u | tail -5 || echo "  No data yet"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Press Ctrl+C to exit | Refreshing every 3 seconds..."

    sleep 3
done
