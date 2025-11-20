#!/bin/bash
# D-REAM Conversation Normal Workload
# Typical LLM inference load - short queries

DURATION=${1:-30}

queries=0
start=$SECONDS

prompts=(
    "What is 2+2?"
    "Hello"
    "Define AI"
    "Status check"
)

while [ $((SECONDS - start)) -lt $DURATION ]; do
    prompt_idx=$((RANDOM % ${#prompts[@]}))
    prompt="${prompts[$prompt_idx]}"
    
    # Send query to Ollama
    response=$(curl -s -X POST http://localhost:11434/api/generate -d "{
        \"model\": \"qwen2.5:14b-instruct-q4_0\",
        \"prompt\": \"$prompt\",
        \"stream\": false,
        \"options\": {\"num_predict\": 20}
    }" 2>/dev/null)
    
    if [ -n "$response" ]; then
        queries=$((queries + 1))
    fi
    
    sleep 2
done

# Return queries per second
echo "scale=3; $queries / $DURATION" | bc
