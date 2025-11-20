#!/bin/bash
# D-REAM ASR/TTS Mixed Workload
# Combined bursts of short and long phrases

DURATION=${1:-60}

short_phrases=("Hello" "Testing" "Quick check" "Status")
long_phrases=(
    "This is a longer phrase for testing the speech synthesis pipeline"
    "D-REAM multi-regime evolutionary optimization testing in progress"
)

start=$SECONDS
samples=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # 70% short, 30% long
    if [ $((RANDOM % 10)) -lt 7 ]; then
        idx=$((RANDOM % ${#short_phrases[@]}))
        phrase="${short_phrases[$idx]}"
        delay=0.3
    else
        idx=$((RANDOM % ${#long_phrases[@]}))
        phrase="${long_phrases[$idx]}"
        delay=1.0
    fi
    
    echo "$phrase" | \
        piper --model /home/kloros/models/piper/glados_piper_medium.onnx \
              --output_file /tmp/dream_tts_mixed_$$.wav \
              --quiet 2>/dev/null
    
    if [ -f /tmp/dream_tts_mixed_$$.wav ]; then
        samples=$((samples + 1))
        rm -f /tmp/dream_tts_mixed_$$.wav
    fi
    
    sleep $delay
done

# Return samples per second
echo "scale=3; $samples / $DURATION" | bc
