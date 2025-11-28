#!/bin/bash
# KLoROS Startup Script

echo "Starting KLoROS Voice Assistant"
echo "==============================="

# Colors for output
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m" # No Color

# Check for skip-checks flag first
SKIP_CHECKS=false
if [ "$1" = "--skip-checks" ]; then
    SKIP_CHECKS=true
    echo -e "${YELLOW}⚠ Skipping service checks as requested${NC}"
fi

# Change to kloros home directory
cd /home/kloros || {
    echo -e "${RED}Error: Cannot access /home/kloros directory${NC}"
    exit 1
}

# Run service health checks (unless skipped)
if [ "$SKIP_CHECKS" = false ]; then
    echo -e "\n${BLUE}Running service health checks...${NC}"
    if [ -x "/home/kloros/check_services.sh" ]; then
        ./check_services.sh
    else
        echo -e "${YELLOW}⚠ Service check script not found${NC}"
    fi
fi

# Start KLoROS
echo -e "\n${GREEN}Starting KLoROS...${NC}"
cd /home/kloros
source .venv/bin/activate
export XDG_RUNTIME_DIR=/run/user/1001
exec python -m src.core.interfaces.voice.voice_daemon
