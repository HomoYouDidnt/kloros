#!/bin/bash
# Quick Evolution Summary - Just the highlights

echo "🧬 D-REAM Evolution Summary"
echo "═══════════════════════════════════════════════"
echo ""

# Top performers
echo "🏆 TOP 5 WINNERS (by fitness):"
find /home/kloros/artifacts/dream/winners -name "*.json" -type f 2>/dev/null | \
    xargs -I {} sh -c 'jq -r ".best.fitness" {} 2>/dev/null && echo {}' | \
    paste - - | sort -rn | head -5 | \
    awk '{printf "   %.4f | %s\n", $1, $2}' | \
    sed 's|/home/kloros/artifacts/dream/winners/||g' | \
    sed 's|.json||g' || echo "   No winners yet"

echo ""

# Recent activity
echo "📊 EVOLUTION STATS (last 50 experiments):"
total=$(tail -50 /home/kloros/logs/dream/*.jsonl 2>/dev/null | grep -c fitness || echo 0)
success=$(tail -50 /home/kloros/logs/dream/*.jsonl 2>/dev/null | jq -r 'select(.fitness > -1e18) | .fitness' 2>/dev/null | wc -l || echo 0)
failed=$(tail -50 /home/kloros/logs/dream/*.jsonl 2>/dev/null | jq -r 'select(.fitness == -1e18) | .fitness' 2>/dev/null | wc -l || echo 0)

echo "   Total experiments: $total"
echo "   Successful: $success"
echo "   Failed: $failed"

if [ $total -gt 0 ]; then
    success_rate=$(echo "scale=1; $success * 100 / $total" | bc)
    echo "   Success rate: $success_rate%"
fi

echo ""

# Deployment activity
echo "🚀 RECENT DEPLOYMENTS:"
ls -lt /home/kloros/artifacts/dream/promotions_ack/*.json 2>/dev/null | head -5 | \
    awk '{print $6, $7, $8, $9}' | \
    while read timestamp file; do
        name=$(basename "$file" .ack.json)
        echo "   $timestamp | $name"
    done || echo "   No deployments yet"

echo ""

# Parameter diversity
echo "🎲 PARAMETER DIVERSITY (last 20 experiments):"
unique_params=$(tail -20 /home/kloros/logs/dream/spica_system_health.jsonl 2>/dev/null | \
    jq -r 'select(.params) | .params | @json' 2>/dev/null | sort -u | wc -l || echo 0)
echo "   Unique parameter sets: $unique_params / 20"

if [ $unique_params -gt 15 ]; then
    echo "   Status: ✅ High diversity (excellent)"
elif [ $unique_params -gt 10 ]; then
    echo "   Status: ⚠️  Moderate diversity"
else
    echo "   Status: ❌ Low diversity (needs investigation)"
fi

echo ""

# Hot-reload activity
echo "🔥 CONFIG HOT-RELOAD:"
if [ -f /home/kloros/.kloros/winner_deployer_state.json ]; then
    last_deploy=$(jq -r '.last_updated' /home/kloros/.kloros/winner_deployer_state.json 2>/dev/null || echo "Never")
    deploy_count=$(jq -r '.deployed_hashes | length' /home/kloros/.kloros/winner_deployer_state.json 2>/dev/null || echo 0)
    echo "   Last deployment: $last_deploy"
    echo "   Total configs deployed: $deploy_count"
else
    echo "   No deployment data yet"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "Run './watch_evolution.sh' for live dashboard"
