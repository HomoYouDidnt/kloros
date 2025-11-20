#!/bin/bash
# D-REAM GPU Short Inference Bursts (Normal Load)
# Real inference workload via Ollama with bounded timeout

DURATION=${1:-30}

python3 << 'PYEOF'
import time
import json
import urllib.request
import urllib.error
import sys

def ollama_generate(prompt: str, model: str = "qwen2.5:7b", timeout: int = 12) -> dict:
    """
    Real Ollama inference with timeout and graceful fallback.
    """
    data = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError) as e:
        # Graceful fallback: return structured error, NOT simulate success
        return {"error": f"ollama_unavailable", "details": str(e), "functional": False}

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 30
start = time.time()
inferences_ok = 0
inferences_failed = 0

prompts = [
    "Count from 1 to 5.",
    "What is 2+2?",
    "Name a color.",
    "Say hello."
]

while time.time() - start < duration:
    prompt = prompts[inferences_ok % len(prompts)]
    result = ollama_generate(prompt, timeout=12)

    if "error" not in result:
        inferences_ok += 1
    else:
        inferences_failed += 1
        # If Ollama is down, don't busy-loop - back off
        time.sleep(2.0)
        continue

    time.sleep(0.5)  # Gap between inferences

# Return throughput + error rate
elapsed = time.time() - start
throughput = inferences_ok / elapsed if elapsed > 0 else 0.0
error_rate = inferences_failed / (inferences_ok + inferences_failed) if (inferences_ok + inferences_failed) > 0 else 0.0

# Structured output
print(json.dumps({
    "throughput_inferences_per_sec": round(throughput, 2),
    "successful_inferences": inferences_ok,
    "failed_inferences": inferences_failed,
    "error_rate": round(error_rate, 2),
    "functional": inferences_ok > 0
}))
PYEOF
