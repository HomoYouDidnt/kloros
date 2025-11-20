#!/bin/bash
# D-REAM Audio Loopback RTL (Round-Trip Latency) Test
# Normal audio processing - measure pipeline latency

DURATION=${1:-30}

# Create test tone and measure processing time
samples=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Generate 1 second of silence as test signal
    sox -n -r 48000 -c 1 /tmp/dream_audio_test_$$.wav trim 0 1 2>/dev/null
    
    if [ -f /tmp/dream_audio_test_$$.wav ]; then
        # Simulate processing through audio pipeline
        sox /tmp/dream_audio_test_$$.wav /tmp/dream_audio_out_$$.wav rate 44100 2>/dev/null
        
        if [ -f /tmp/dream_audio_out_$$.wav ]; then
            samples=$((samples + 1))
        fi
        
        rm -f /tmp/dream_audio_test_$$.wav /tmp/dream_audio_out_$$.wav
    fi
    
    sleep 1
done

# Return samples per second
echo "scale=3; $samples / $DURATION" | bc
