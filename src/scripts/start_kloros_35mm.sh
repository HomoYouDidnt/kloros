#!/bin/bash
# KLoROS Voice Assistant - 3.5mm Speaker Configuration
# Run this script to start KLoROS with your 3.5mm speaker

cd /home/kloros

# KLoROS Configuration
export KLR_USE_VOSK_HTTP=1
export KLR_PIPER_VOICE=/home/kloros/kloros_models/piper/glados_piper_medium.onnx
export KLR_AUDIO_OUTPUT_DEVICE=plughw:2,0

# Optional: Enable debug output
# export KLR_DEBUG=1

echo "Starting KLoROS with 3.5mm speaker (plughw:2,0)..."
echo "Say \"KLoROS\" to wake her up!"

/opt/kloros/.venv/bin/python -m src.core.interfaces.voice.voice_daemon
