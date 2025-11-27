#!/bin/bash
# Configure Gaming Rig IP (Judge + Ollama Auto-Failover)
# Run this once with your gaming rig's Tailscale IP

JUDGE_CONFIG="/home/kloros/.kloros/judge_config.json"
GAMING_RIG_IP="${1:-PLACEHOLDER}"

if [ "$GAMING_RIG_IP" = "PLACEHOLDER" ]; then
    echo "Error: Please provide gaming rig IP"
    echo "Usage: judge-enable <GAMING_RIG_IP>"
    exit 1
fi

# Save gaming rig IP for automatic failover
cat > "$JUDGE_CONFIG" << EOFCONFIG
{
  "judge_url": "http://$GAMING_RIG_IP:8001/v1/chat/completions",
  "ollama_remote_url": "http://$GAMING_RIG_IP:11434",
  "updated_at": "$(date -Iseconds)"
}
EOFCONFIG

echo "✓ Gaming Rig IP Configured: $GAMING_RIG_IP"
echo ""
echo "Auto-Failover System:"
echo "  Judge (port 8001):"
echo "    - Uses remote when available → agents can graduate"
echo "    - Queues when unavailable → agents wait in purgatory"
echo ""
echo "  Ollama (port 11434):"
echo "    - Uses remote when available → big models"
echo "    - Falls back to local when unavailable → smaller models"
echo ""
echo "Both check every 30 seconds automatically."
echo "Just start/stop services on your gaming rig!"
echo ""

echo "Testing current connectivity..."

# Test judge
if curl -s --max-time 3 "http://$GAMING_RIG_IP:8001/health" > /dev/null 2>&1; then
    echo "✓ Judge is currently ONLINE - agents can graduate"
else
    echo "○ Judge is currently OFFLINE - agents queued for judgment"
fi

# Test Ollama
if curl -s --max-time 3 "http://$GAMING_RIG_IP:11434/api/tags" > /dev/null 2>&1; then
    echo "✓ Ollama is currently ONLINE - using big models"
else
    echo "○ Ollama is currently OFFLINE - using local models"
fi
