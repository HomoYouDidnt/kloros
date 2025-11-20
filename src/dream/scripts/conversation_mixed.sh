#!/bin/bash
# D-REAM Conversation Mixed Workload
# Variable length queries and responses

DURATION=${1:-60}

queries=0
start=$SECONDS

short_prompts=("Hi" "Status" "OK" "Test")
long_prompts=("Explain machine learning" "Describe neural networks")

while [ $((SECONDS - start)) -lt $DURATION ]; do
    # 60% short, 40% long
    if [ $((RANDOM % 10)) -lt 6 ]; then
        idx=$((RANDOM % ${#short_prompts[@]}))
        prompt="${short_prompts[$idx]}"
        tokens=20
        delay=1
    else
        idx=$((RANDOM % ${#long_prompts[@]}))
        prompt="${long_prompts[$idx]}"
        tokens=100
        delay=2
    fi
    
    response=$(curl -s -X POST http://localhost:11434/api/generate -d "{
        \"model\": \"qwen2.5:14b-instruct-q4_0\",
        \"prompt\": \"$prompt\",
        \"stream\": false,
        \"options\": {\"num_predict\": $tokens}
    }" 2>/dev/null)
    
    if [ -n "$response" ]; then
        queries=$((queries + 1))
    fi
    
    sleep $delay
done

# Return queries per second
echo "scale=3; $queries / $DURATION" | bc
