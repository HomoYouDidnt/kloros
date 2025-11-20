#!/bin/bash
# D-REAM Conversation Idle Workload
# Minimal LLM activity - just availability checks

DURATION=${1:-20}

checks=0
start=$SECONDS

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # Check Ollama availability
    curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && checks=$((checks + 1))
    sleep 1
done

# Return checks per second
echo "scale=2; $checks / $DURATION" | bc
