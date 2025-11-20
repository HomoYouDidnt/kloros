#!/bin/bash
# Check Gaming Rig Auto-Failover Status

JUDGE_CONFIG="/home/kloros/.kloros/judge_config.json"

echo "════════════════════════════════════════════════════════════"
echo "  GAMING RIG AUTO-FAILOVER STATUS"
echo "════════════════════════════════════════════════════════════"
echo ""

if [ ! -f "$JUDGE_CONFIG" ]; then
    echo "⚠ Gaming rig not configured"
    echo ""
    echo "Current State:"
    echo "  Judge: Agents queued (no remote judge)"
    echo "  Ollama: Local only"
    echo ""
    echo "To configure: judge-enable <GAMING_RIG_IP>"
    exit 0
fi

# Parse config
JUDGE_URL=$(jq -r '.judge_url' "$JUDGE_CONFIG" 2>/dev/null)
OLLAMA_URL=$(jq -r '.ollama_remote_url' "$JUDGE_CONFIG" 2>/dev/null)
GAMING_RIG_IP=$(echo "$JUDGE_URL" | sed -E 's|http://([^:]+):.*|\1|')
UPDATED=$(jq -r '.updated_at' "$JUDGE_CONFIG" 2>/dev/null)

echo "Gaming Rig IP: $GAMING_RIG_IP"
echo "Last Updated: $UPDATED"
echo ""

# Check Judge
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "vLLM JUDGE (Port 8001) - Auto-Failover"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "URL: $JUDGE_URL"
echo ""

if curl -s --max-time 2 "$JUDGE_URL" > /dev/null 2>&1; then
    echo "✓ Judge is ONLINE"
    echo "  → Agents can graduate (fitness scoring active)"
    echo "  → Progressive skill mastery operational"
else
    echo "○ Judge is OFFLINE"
    echo "  → Agents queued in purgatory"
    echo "  → Will auto-process when judge comes online"
fi

echo ""

# Check Ollama
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OLLAMA LLM (Port 11434) - Auto-Failover"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Remote URL: $OLLAMA_URL"
echo "Local Fallback: http://127.0.0.1:11434"
echo ""

if curl -s --max-time 2 "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    echo "✓ Remote Ollama is ONLINE"
    echo "  → Using gaming rig (big models)"
    echo "  → Investigations use qwen2.5:72b"
else
    echo "○ Remote Ollama is OFFLINE"
    echo "  → Using local server (smaller models)"
    echo "  → Investigations use qwen2.5:14b"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "Auto-Failover:"
echo "  Both services check every 30 seconds"
echo "  Just start/stop services on gaming rig!"
echo ""
echo "Commands:"
echo "  Configure:  judge-enable <GAMING_RIG_IP>"
echo "  Clear:      judge-disable"
echo "  Status:     judge-status"
echo "════════════════════════════════════════════════════════════"
