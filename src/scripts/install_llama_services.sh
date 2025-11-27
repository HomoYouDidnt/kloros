#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/../config/systemd"
SYSTEMD_DIR="/etc/systemd/system"

LIVE_MODEL="${1:-/home/kloros/models/gguf/qwen2.5-7b-instruct-q3_k_m.gguf}"
CODE_MODEL="${2:-/home/kloros/models/gguf/qwen2.5-coder-7b-instruct-q4_k_m.gguf}"
THINK_MODEL="${3:-/home/kloros/models/gguf/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf}"

echo "[install_llama_services] Installing llama.cpp systemd services..."

if ! command -v llama-server &> /dev/null; then
    echo "ERROR: llama-server not found in PATH"
    echo "Please install llama.cpp first"
    exit 1
fi

if [ ! -f "$LIVE_MODEL" ]; then
    echo "WARNING: Live model not found: $LIVE_MODEL"
    echo "Run: python -m src.kloros.model_manager download qwen2.5:7b"
fi

if [ ! -f "$CODE_MODEL" ]; then
    echo "WARNING: Code model not found: $CODE_MODEL"
    echo "Run: python -m src.kloros.model_manager download qwen2.5-coder:7b"
fi

if [ ! -f "$THINK_MODEL" ]; then
    echo "WARNING: Think model not found: $THINK_MODEL"
    echo "Run: python -m src.kloros.model_manager download deepseek-r1:7b"
fi

echo "[install_llama_services] Installing kloros-llama-live.service..."
sed "s|{{MODEL_PATH}}|$LIVE_MODEL|g" \
    "${CONFIG_DIR}/kloros-llama-live.service.template" \
    > /tmp/kloros-llama-live.service

sudo cp /tmp/kloros-llama-live.service "${SYSTEMD_DIR}/kloros-llama-live.service"
sudo chown root:root "${SYSTEMD_DIR}/kloros-llama-live.service"
sudo chmod 644 "${SYSTEMD_DIR}/kloros-llama-live.service"

echo "[install_llama_services] Installing kloros-llama-code.service..."
sed "s|{{MODEL_PATH}}|$CODE_MODEL|g" \
    "${CONFIG_DIR}/kloros-llama-code.service.template" \
    > /tmp/kloros-llama-code.service

sudo cp /tmp/kloros-llama-code.service "${SYSTEMD_DIR}/kloros-llama-code.service"
sudo chown root:root "${SYSTEMD_DIR}/kloros-llama-code.service"
sudo chmod 644 "${SYSTEMD_DIR}/kloros-llama-code.service"

echo "[install_llama_services] Installing kloros-llama-think.service..."
sed "s|{{MODEL_PATH}}|$THINK_MODEL|g" \
    "${CONFIG_DIR}/kloros-llama-think.service.template" \
    > /tmp/kloros-llama-think.service

sudo cp /tmp/kloros-llama-think.service "${SYSTEMD_DIR}/kloros-llama-think.service"
sudo chown root:root "${SYSTEMD_DIR}/kloros-llama-think.service"
sudo chmod 644 "${SYSTEMD_DIR}/kloros-llama-think.service"

echo "[install_llama_services] Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "[install_llama_services] Services installed successfully!"
echo ""
echo "To start services:"
echo "  sudo systemctl start kloros-llama-live"
echo "  sudo systemctl start kloros-llama-code"
echo "  sudo systemctl start kloros-llama-think"
echo ""
echo "To enable on boot:"
echo "  sudo systemctl enable kloros-llama-live"
echo "  sudo systemctl enable kloros-llama-code"
echo "  sudo systemctl enable kloros-llama-think"
echo ""
echo "To check status:"
echo "  sudo systemctl status kloros-llama-live"
echo "  sudo systemctl status kloros-llama-code"
echo "  sudo systemctl status kloros-llama-think"
