#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "KLoROS llama.cpp Migration Validation"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

print_status() {
    local status=$1
    local message=$2

    if [ "$status" = "OK" ]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [ "$status" = "WARN" ]; then
        echo -e "${YELLOW}⚠${NC} $message"
    else
        echo -e "${RED}✗${NC} $message"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "1. Checking Prerequisites"
echo "-------------------------"

if command -v llama-server &> /dev/null; then
    print_status "OK" "llama-server installed"
else
    print_status "FAIL" "llama-server not found in PATH"
fi

LIVE_MODEL="/home/kloros/models/gguf/qwen2.5-7b-instruct-q3_k_m.gguf"
CODE_MODEL="/home/kloros/models/gguf/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
THINK_MODEL="/home/kloros/models/gguf/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"

if [ -f "$LIVE_MODEL" ]; then
    print_status "OK" "Live model exists: $LIVE_MODEL"
else
    print_status "WARN" "Live model not found: $LIVE_MODEL"
fi

if [ -f "$CODE_MODEL" ]; then
    print_status "OK" "Code model exists: $CODE_MODEL"
else
    print_status "WARN" "Code model not found: $CODE_MODEL"
fi

if [ -f "$THINK_MODEL" ]; then
    print_status "OK" "Think model exists: $THINK_MODEL"
else
    print_status "WARN" "Think model not found: $THINK_MODEL"
fi

echo ""
echo "2. Checking Service Health"
echo "--------------------------"

if systemctl is-active --quiet kloros-llama-live.service 2>/dev/null; then
    print_status "OK" "kloros-llama-live.service is running"

    if curl -s http://127.0.0.1:8080/health | grep -q '"status":"ok"'; then
        print_status "OK" "llama-live is responding on port 8080"
    else
        print_status "FAIL" "llama-live not responding on port 8080"
    fi
else
    print_status "WARN" "kloros-llama-live.service is not running"
fi

if systemctl is-active --quiet kloros-llama-code.service 2>/dev/null; then
    print_status "OK" "kloros-llama-code.service is running"

    if curl -s http://127.0.0.1:8081/health | grep -q '"status":"ok"'; then
        print_status "OK" "llama-code is responding on port 8081"
    else
        print_status "FAIL" "llama-code not responding on port 8081"
    fi
else
    print_status "WARN" "kloros-llama-code.service is not running"
fi

if systemctl is-active --quiet kloros-llama-think.service 2>/dev/null; then
    print_status "OK" "kloros-llama-think.service is running"

    if curl -s http://127.0.0.1:8082/health | grep -q '"status":"ok"'; then
        print_status "OK" "llama-think is responding on port 8082"
    else
        print_status "FAIL" "llama-think not responding on port 8082"
    fi
else
    print_status "WARN" "kloros-llama-think.service is not running"
fi

echo ""
echo "3. Testing Backend Integration"
echo "-------------------------------"

cd "$PROJECT_ROOT"

if python3 -c "from src.reasoning.llama_adapter import LlamaAdapter" 2>/dev/null; then
    print_status "OK" "LlamaAdapter import successful"
else
    print_status "FAIL" "LlamaAdapter import failed"
fi

if python3 -c "from src.model_manager import ModelManager" 2>/dev/null; then
    print_status "OK" "ModelManager import successful"
else
    print_status "FAIL" "ModelManager import failed"
fi

if python3 -c "from src.reasoning.base import create_reasoning_backend; create_reasoning_backend('llama')" 2>/dev/null; then
    print_status "OK" "Factory creates llama backend"
else
    print_status "FAIL" "Factory failed to create llama backend"
fi

echo ""
echo "4. Running Unit Tests"
echo "---------------------"

if pytest tests/unit/test_llama_adapter.py -v --tb=short 2>&1 | tee /tmp/llama_test_output.txt | grep -q "passed"; then
    print_status "OK" "LlamaAdapter unit tests passed"
else
    print_status "FAIL" "LlamaAdapter unit tests failed"
fi

if pytest tests/unit/test_model_manager.py -v --tb=short 2>&1 | grep -q "passed"; then
    print_status "OK" "ModelManager unit tests passed"
else
    print_status "FAIL" "ModelManager unit tests failed"
fi

echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    echo ""
    echo "Migration is ready to proceed."
    echo ""
    echo "Next steps:"
    echo "  1. Start llama.cpp services:"
    echo "     sudo systemctl start kloros-llama-live"
    echo "     sudo systemctl start kloros-llama-code"
    echo "     sudo systemctl start kloros-llama-think"
    echo ""
    echo "  2. Run integration tests:"
    echo "     pytest tests/integration/test_llama_integration.py -v"
    echo ""
    echo "  3. Update services to use llama backend:"
    echo "     export LLM_BACKEND=llama"
    exit 0
else
    echo -e "${RED}Validation failed with $ERRORS error(s)${NC}"
    echo ""
    echo "Please resolve the issues above before proceeding with migration."
    exit 1
fi
