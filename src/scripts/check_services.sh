#!/bin/bash
# KLoROS Service Health Check Script

echo "KLoROS Service Health Check"
echo "==========================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Vosk HTTP service
echo -n "Checking Vosk HTTP service (port 8080)... "
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
    VOSK_STATUS=$(curl -s http://localhost:8080/health)
    echo "  Status: $VOSK_STATUS"
else
    echo -e "${RED}✗ Not responding${NC}"
    echo -e "${YELLOW}  Start with: vosk-server --model-path /home/kloros/kloros_models/vosk/model${NC}"
    exit 1
fi

# Check Ollama LLM service
echo -n "Checking Ollama LLM service (port 11434)... "
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
    MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*' | cut -d'"' -f4 | head -3)
    echo "  Available models: $MODELS"
else
    echo -e "${RED}✗ Not responding${NC}"
    echo -e "${YELLOW}  Start with: ollama serve${NC}"
    exit 1
fi

# Check GLaDOS voice model
echo -n "Checking GLaDOS voice model... "
if [ -f "/home/kloros/kloros_models/piper/glados_piper_medium.onnx" ]; then
    echo -e "${GREEN}✓ Found${NC}"
    SIZE=$(du -h /home/kloros/kloros_models/piper/glados_piper_medium.onnx | cut -f1)
    echo "  Size: $SIZE"
else
    echo -e "${RED}✗ Missing${NC}"
    echo -e "${YELLOW}  Expected: /home/kloros/kloros_models/piper/glados_piper_medium.onnx${NC}"
    exit 1
fi

# Check Vosk model
echo -n "Checking Vosk model directory... "
if [ -d "/home/kloros/kloros_models/vosk/model" ] && [ -f "/home/kloros/kloros_models/vosk/model/am/final.mdl" ]; then
    echo -e "${GREEN}✓ Found${NC}"
else
    echo -e "${RED}✗ Missing or incomplete${NC}"
    echo -e "${YELLOW}  Expected: /home/kloros/kloros_models/vosk/model/am/final.mdl${NC}"
    exit 1
fi

# Check Python environment
echo -n "Checking KLoROS Python environment... "
if [ -f "/opt/kloros/.venv/bin/python" ]; then
    echo -e "${GREEN}✓ Found${NC}"
    PYTHON_VERSION=$(/opt/kloros/.venv/bin/python --version)
    echo "  Version: $PYTHON_VERSION"
else
    echo -e "${RED}✗ Missing${NC}"
    echo -e "${YELLOW}  Expected: /opt/kloros/.venv/bin/python${NC}"
    exit 1
fi

echo -e "\n${GREEN}All services are ready! ✓${NC}"
echo "KLoROS can be started safely."
