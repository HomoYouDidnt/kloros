#!/bin/bash
# Clear Gaming Rig Configuration
# Use this to force local-only mode

JUDGE_CONFIG="/home/kloros/.kloros/judge_config.json"

# Remove config to disable remote access
rm -f "$JUDGE_CONFIG"

echo "✓ Gaming Rig Configuration Cleared"
echo ""
echo "KLoROS will now use local resources only:"
echo "  - Judge: Agents queued (no scoring available)"
echo "  - Ollama: Local models only"
echo ""
echo "To re-enable: judge-enable <GAMING_RIG_IP>"
