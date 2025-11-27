#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "KLoROS Rollback to Ollama"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}This will stop llama.cpp services and revert to Ollama${NC}"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

echo ""
echo "1. Stopping llama.cpp services..."
echo "----------------------------------"

sudo systemctl stop kloros-llama-live.service 2>/dev/null || true
sudo systemctl stop kloros-llama-code.service 2>/dev/null || true
sudo systemctl stop kloros-llama-think.service 2>/dev/null || true

echo -e "${GREEN}✓${NC} llama.cpp services stopped"

echo ""
echo "2. Checking Ollama status..."
echo "----------------------------"

if systemctl is-active --quiet ollama.service 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Ollama service is running"
else
    echo "Starting Ollama service..."
    sudo systemctl start ollama.service || {
        echo "ERROR: Failed to start Ollama"
        echo "Manual intervention required"
        exit 1
    }
    sleep 2
    echo -e "${GREEN}✓${NC} Ollama service started"
fi

if curl -s http://127.0.0.1:11434/api/tags | grep -q "models"; then
    echo -e "${GREEN}✓${NC} Ollama is responding"
else
    echo "WARNING: Ollama not responding on port 11434"
fi

echo ""
echo "3. Restoring environment..."
echo "---------------------------"

echo -e "${GREEN}✓${NC} Environment restored (using Ollama by default)"

echo ""
echo "=========================================="
echo "Rollback Complete"
echo "=========================================="
echo ""
echo "Ollama is now active. llama.cpp services are stopped."
echo ""
echo "Services using default 'ollama' backend will work normally."
echo ""
echo "To re-enable llama.cpp later:"
echo "  sudo systemctl start kloros-llama-live"
echo "  sudo systemctl start kloros-llama-code"
echo "  sudo systemctl start kloros-llama-think"
echo ""
