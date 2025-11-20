#!/bin/bash
# D-REAM ASR/TTS Idle Workload
# Minimal speech pipeline activity - just initialization checks

DURATION=${1:-20}

# Simple check that Vosk and Piper are available
start=$SECONDS
checks=0

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Check Vosk model
    if [ -d /home/kloros/models/vosk/model ]; then
        checks=$((checks + 1))
    fi
    
    # Check Piper binary
    if command -v piper >/dev/null 2>&1; then
        checks=$((checks + 1))
    fi
    
    sleep 1
done

# Return checks per second (should be ~2 per second)
echo "scale=2; $checks / $DURATION" | bc
