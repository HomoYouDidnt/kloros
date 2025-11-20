#!/bin/bash
# D-REAM Audio Burst Workload
# Rapid audio generation bursts - stress test

DURATION=${1:-60}

samples=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Generate short burst (0.5s)
    sox -n -r 48000 -c 2 /tmp/dream_audio_burst_$$.wav synth 0.5 sine 440 2>/dev/null
    
    if [ -f /tmp/dream_audio_burst_$$.wav ]; then
        # Quick resample operation
        sox /tmp/dream_audio_burst_$$.wav -r 44100 /tmp/dream_audio_burst_out_$$.wav 2>/dev/null
        samples=$((samples + 1))
        rm -f /tmp/dream_audio_burst_$$.wav /tmp/dream_audio_burst_out_$$.wav
    fi
    
    sleep 0.2  # Short delay for burst pattern
done

# Return samples per second
echo "scale=2; $samples / $DURATION" | bc
