#!/bin/bash
# KLoROS Voice Pipeline Validation Script

echo "=========================================="
echo "KLoROS VOICE PIPELINE VALIDATION"
echo "=========================================="

cd /home/kloros || { echo "ERROR: Cannot access /home/kloros"; exit 1; }

echo "1. Testing import paths and backend loading..."
echo "----------------------------------------------"

# Test import path resolution
echo "Testing import path for reasoning base module:"
/home/kloros/.venv/bin/python -c "
import sys
sys.path.insert(0, '/home/kloros')
try:
    from src.reasoning import base
    print('✅ Reasoning base module loaded from:', base.__file__)
    backend = base.create_reasoning_backend('ollama')
    print('✅ Ollama backend created successfully:', type(backend).__name__)
except Exception as e:
    print('❌ Import/backend creation failed:', e)
    exit(1)
" || { echo "❌ Python import test failed"; exit 1; }

echo ""
echo "2. Checking environment variables..."
echo "--------------------------------------"

# Check critical environment variables
check_env() {
    local var_name="$1"
    local var_value="${!var_name}"
    if [ -n "$var_value" ]; then
        echo "✅ $var_name=$var_value"
    else
        echo "⚠️  $var_name not set (will use default)"
    fi
}

check_env "KLR_REASON_BACKEND"
check_env "OLLAMA_HOST"
check_env "OLLAMA_MODEL"
check_env "KLR_INPUT_IDX"
check_env "KLR_VAD_SENSITIVITY"
check_env "KLR_PIPER_VOICE"

echo ""
echo "3. Testing Ollama connectivity..."
echo "--------------------------------"

OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-nous-hermes:7b-q4_0}"

# Test Ollama health
if curl -s "$OLLAMA_HOST" > /dev/null; then
    echo "✅ Ollama server is responding at $OLLAMA_HOST"
else
    echo "❌ Ollama server not responding at $OLLAMA_HOST"
fi

# Test model availability
if curl -s "$OLLAMA_HOST/api/tags" | grep -q "$OLLAMA_MODEL"; then
    echo "✅ Model $OLLAMA_MODEL is available"
else
    echo "⚠️  Model $OLLAMA_MODEL may not be available"
fi

# Test GPU integration with a simple request
echo "Testing GPU acceleration..."
GPU_TEST_RESPONSE=$(curl -s -X POST "$OLLAMA_HOST/api/generate" \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"$OLLAMA_MODEL\",
        \"prompt\": \"Hello\",
        \"stream\": false,
        \"options\": {\"num_gpu\": 999, \"main_gpu\": 0}
    }" | jq -r '.response // "ERROR"')

if [ "$GPU_TEST_RESPONSE" != "ERROR" ] && [ -n "$GPU_TEST_RESPONSE" ]; then
    echo "✅ GPU-accelerated request successful: ${GPU_TEST_RESPONSE:0:50}..."
else
    echo "❌ GPU-accelerated request failed"
fi

echo ""
echo "4. Testing audio system..."
echo "--------------------------"

# Test audio devices
echo "Available audio devices:"
/home/kloros/.venv/bin/python -c "
import sounddevice as sd
try:
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        name = d.get('name', str(d)) if isinstance(d, dict) else str(d)
        max_in = d.get('max_input_channels', 0) if isinstance(d, dict) else 0
        if max_in > 0:
            print(f'  {i}: {name} (input)')
except Exception as e:
    print('❌ Audio device query failed:', e)
"

# Test PulseAudio/PipeWire commands
if command -v pactl > /dev/null; then
    echo "✅ pactl available for half-duplex control"
    if pactl info > /dev/null 2>&1; then
        echo "✅ PulseAudio/PipeWire responding"
    else
        echo "⚠️  PulseAudio/PipeWire not responding"
    fi
else
    echo "❌ pactl not available - half-duplex won't work"
fi

echo ""
echo "5. Testing systemd service configuration..."
echo "-------------------------------------------"

if [ -f "/home/kloros/.config/systemd/user/kloros.service" ]; then
    echo "✅ Systemd service file exists"
    echo "Service configuration:"
    grep -E "(WorkingDirectory|PYTHONPATH|KLR_REASON_BACKEND)" /home/kloros/.config/systemd/user/kloros.service | sed 's/^/  /'
else
    echo "❌ Systemd service file missing"
fi

echo ""
echo "6. Validating file structure..."
echo "-------------------------------"

# Check key files exist
check_file() {
    local file="$1"
    if [ -f "$file" ]; then
        echo "✅ $file exists"
    else
        echo "❌ $file missing"
    fi
}

check_file "/home/kloros/src/kloros_voice.py"
check_file "/home/kloros/src/reasoning/base.py"
check_file "/home/kloros/src/rag.py"
check_file "/home/kloros/.venv/bin/python"

# Check for import conflicts
if [ -e "/home/kloros/KLoROS" ]; then
    echo "⚠️  /home/kloros/KLoROS exists - potential import conflict"
else
    echo "✅ No KLoROS directory conflict"
fi

echo ""
echo "7. GPU utilization test..."
echo "--------------------------"

echo "Current GPU status:"
if command -v nvidia-smi > /dev/null; then
    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits | \
        awk -F, '{printf "  GPU: %s | Memory: %sMB/%sMB | Usage: %s%%\n", $1, $2, $3, $4}'
else
    echo "⚠️  nvidia-smi not available"
fi

echo ""
echo "=========================================="
echo "VALIDATION COMPLETE"
echo "=========================================="

# Summary recommendations
echo ""
echo "🚀 QUICK START COMMANDS:"
echo "------------------------"
echo "# Test startup (headless mode):"
echo "cd /home/kloros && KLR_HEADLESS=1 KLR_REASON_BACKEND=ollama ./.venv/bin/python -m src.kloros_voice"
echo ""
echo "# Enable systemd service:"
echo "systemctl --user daemon-reload"
echo "systemctl --user enable kloros"
echo "systemctl --user start kloros"
echo ""
echo "# Monitor service:"
echo "systemctl --user status kloros"
echo "journalctl --user -u kloros -f"
echo ""
echo "# Check GPU usage during voice interaction:"
echo "watch -n 0.5 nvidia-smi"