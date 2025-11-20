#!/bin/bash
# D-REAM ASR/TTS Stress Workload
# Heavy pipeline load - continuous TTS generation with longer phrases

DURATION=${1:-60}

phrases=(
    "The quick brown fox jumps over the lazy dog"
    "Testing speech synthesis performance under load"
    "D-REAM evolutionary optimization in progress"
    "KLoROS voice assistant speech pipeline evaluation"
    "Continuous text to speech stress testing workload"
)

start=$SECONDS
samples=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    phrase_idx=$((RANDOM % ${#phrases[@]}))
    echo "${phrases[$phrase_idx]}" | \
        piper --model /home/kloros/models/piper/glados_piper_medium.onnx \
              --output_file /tmp/dream_tts_stress_$$.wav \
              --quiet 2>/dev/null
    
    if [ -f /tmp/dream_tts_stress_$$.wav ]; then
        samples=$((samples + 1))
        rm -f /tmp/dream_tts_stress_$$.wav
    fi
    
    sleep 0.5
done

# Return samples per second
echo "scale=3; $samples / $DURATION" | bc
