#!/bin/bash
# Stable KLoROS launcher that handles audio issues

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export PULSE_RUNTIME_PATH="$XDG_RUNTIME_DIR/pulse"

# Function to setup audio
setup_audio() {
    echo "[launcher] Setting up audio environment..."
    
    # Kill existing PulseAudio
    pulseaudio --kill 2>/dev/null || true
    sleep 1
    
    # Start PulseAudio with fallback configuration
    pulseaudio --start --exit-idle-time=-1 --disable-shm 2>/dev/null || true
    sleep 2
    
    # Check if PulseAudio is running
    if pactl info >/dev/null 2>&1; then
        echo "[launcher] ✓ PulseAudio running"
        
        # Load null sink and source for testing
        pactl load-module module-null-sink sink_name=kloros_test 2>/dev/null || true
        pactl load-module module-virtual-source source_name=kloros_mic master=kloros_test.monitor 2>/dev/null || true
        
        return 0
    else
        echo "[launcher] ✗ PulseAudio failed to start"
        return 1
    fi
}

# Function to run KLoROS with fallback modes
run_kloros() {
    local mode=$1
    echo "[launcher] Running KLoROS in $mode mode..."
    
    case $mode in
        "headless")
            export KLR_HEADLESS=1
            export KLR_TEST_TRANSCRIPT="${KLR_TEST_TRANSCRIPT:-testing voice pipeline}"
            ;;
        "virtual")
            export KLR_INPUT_IDX=0
            export KLR_AUDIO_BACKEND=sounddevice
            ;;
        "mock")
            export KLR_AUDIO_BACKEND=mock
            ;;
    esac
    
    cd /home/kloros
    timeout 30 /home/kloros/.venv/bin/python -m src.kloros_voice
    return $?
}

# Main execution
echo "[launcher] KLoROS Stable Launcher"

# Try different approaches in order of preference
if setup_audio; then
    echo "[launcher] Trying virtual audio mode..."
    if run_kloros "virtual"; then
        echo "[launcher] ✓ Success with virtual audio"
        exit 0
    fi
    
    echo "[launcher] Virtual audio failed, trying mock mode..."
    if run_kloros "mock"; then
        echo "[launcher] ✓ Success with mock audio"
        exit 0
    fi
fi

echo "[launcher] Falling back to headless mode..."
if run_kloros "headless"; then
    echo "[launcher] ✓ Success with headless mode"
    exit 0
fi

echo "[launcher] ✗ All modes failed"
exit 1
