#!/bin/bash
# D-REAM Audio Full Duplex Workload
# Simultaneous capture and playback simulation (mixed load)

DURATION=${1:-60}

operations=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Simulate capture (generate test audio)
    sox -n -r 48000 -c 1 /tmp/dream_capture_$$.wav synth 1 sine 440 2>/dev/null &
    capture_pid=$!
    
    # Simulate playback (resample different audio)
    sox -n -r 48000 -c 2 /tmp/dream_playback_$$.wav synth 1 sine 880 2>/dev/null &
    playback_pid=$!
    
    # Wait for both
    wait $capture_pid 2>/dev/null
    wait $playback_pid 2>/dev/null
    
    # Check if both succeeded
    if [ -f /tmp/dream_capture_$$.wav ] && [ -f /tmp/dream_playback_$$.wav ]; then
        operations=$((operations + 1))
    fi
    
    rm -f /tmp/dream_capture_$$.wav /tmp/dream_playback_$$.wav
    
    sleep 0.5
done

# Return operations per second
echo "scale=3; $operations / $DURATION" | bc
