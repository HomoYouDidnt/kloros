#!/bin/bash
# D-REAM Conversation Stress Workload
# Heavy LLM load - long responses

DURATION=${1:-60}

queries=0
start=$SECONDS

long_prompts=(
    "Explain quantum computing in detail"
    "Describe the history of artificial intelligence"
    "What are the key principles of evolutionary algorithms?"
)

while [ $((SECONDS - start)) -lt $DURATION ]; do
    prompt_idx=$((RANDOM % ${#long_prompts[@]}))
    prompt="${long_prompts[$prompt_idx]}"
    
    # Send longer query
    response=$(curl -s -X POST http://localhost:11434/api/generate -d "{
        \"model\": \"qwen2.5:14b-instruct-q4_0\",
        \"prompt\": \"$prompt\",
        \"stream\": false,
        \"options\": {\"num_predict\": 200}
    }" 2>/dev/null)
    
    if [ -n "$response" ]; then
        queries=$((queries + 1))
    fi
    
    sleep 1
done

# Return queries per second
echo "scale=3; $queries / $DURATION" | bc
