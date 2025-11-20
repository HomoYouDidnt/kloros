#!/bin/bash
# D-REAM ASR/TTS Normal Workload
# Typical speech processing - a few TTS generations

DURATION=${1:-30}

# Generate short TTS samples
start=$SECONDS
samples=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Generate short audio with Piper
    echo "Test phrase number $samples" | \
        piper --model /home/kloros/models/piper/glados_piper_medium.onnx \
              --output_file /tmp/dream_tts_test_$$.wav \
              --quiet 2>/dev/null
    
    if [ -f /tmp/dream_tts_test_$$.wav ]; then
        samples=$((samples + 1))
        rm -f /tmp/dream_tts_test_$$.wav
    fi
    
    sleep 2
done

# Return samples per second
echo "scale=3; $samples / $DURATION" | bc
