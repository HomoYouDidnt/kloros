# GPU Canary System - Operations Checklist

## Prerequisites

### 1. Python Dependencies
Verify `requests` library is available:
```bash
/home/kloros/.venv/bin/python3 -c "import requests; print(f'✓ requests {requests.__version__}')"
```

### 2. VLLM Service
Verify production VLLM service unit name:
```bash
systemctl status vllm.service --no-pager | head -5
```

Expected: Service should exist and be running.

### 3. GPU Access
Verify nvidia-smi access:
```bash
nvidia-smi --query-gpu=name,memory.total --format=csv
```

## Configuration Verification

### 1. Environment Variables
Check GPU canary configuration in `.kloros_env`:
```bash
grep "KLR_" /home/kloros/.kloros_env | grep -E "(CANARY|MAINTENANCE|SPARE)"
```

Expected values:
- `KLR_GPU_MAINTENANCE_MAX_DOWNTIME=60` (seconds)
- `KLR_GPU_MAINTENANCE_WINDOW=03:00-07:00` (maintenance window)
- `KLR_CANARY_MODE=predictive` (default mode)
- `KLR_CANARY_PORT=9011` (canary VLLM port)
- `KLR_CANARY_TIMEOUT=30` (test timeout seconds)
- `KLR_ALLOW_SPARE_GPU=false` (set true if spare GPU available)
- `KLR_SPARE_GPU_ID=1` (CUDA device ID if spare available)

### 2. Lock Directory
Verify lock directory exists:
```bash
ls -ld /home/kloros/.kloros/locks
```

### 3. Budget Directory
Verify budget directory exists:
```bash
ls -ld /home/kloros/.kloros/maintenance
```

## Functional Tests

### 1. Budget Tracking
Check today's budget (should be 0 if no canaries run yet):
```bash
jq . /home/kloros/.kloros/maintenance/gpu_budget_$(date +%Y%m%d).json 2>/dev/null || echo "No budget file yet (OK)"
```

### 2. Maintenance Window Check
Verify current time vs maintenance window:
```bash
TZ="America/New_York" date +"Current time: %H:%M (ET)"
echo "Maintenance window: 03:00-07:00 ET"
```

### 3. GPU Lock Status
Check if GPU lock is held:
```bash
if [ -f /home/kloros/.kloros/locks/gpu_maintenance.lock ]; then
    echo "⚠️  GPU lock is currently held:"
    cat /home/kloros/.kloros/locks/gpu_maintenance.lock
else
    echo "✓ GPU lock is free"
fi
```

### 4. Run Tests
Execute minimal test suite:
```bash
cd /home/kloros
PYTHONPATH=/home/kloros .venv/bin/pytest tests/test_gpu_canary.py -v
```

Expected: All tests should pass.

## Predictive Mode Testing (Default)

Predictive mode uses pre-flight validation without starting real canary VLLM.

### 1. Verify Mode
```bash
grep "KLR_CANARY_MODE" /home/kloros/.kloros_env
```

Expected: `KLR_CANARY_MODE=predictive`

### 2. Test Pre-flight Validation
```bash
cd /home/kloros
sudo -u kloros PYTHONPATH=/home/kloros .venv/bin/python3 << 'PYEOF'
import sys
sys.path.insert(0, '/home/kloros')

from src.phase.domains.spica_gpu_allocation import SpicaGPUAllocation, GPUAllocationTestConfig

# Create evaluator
config = GPUAllocationTestConfig(
    vllm_memory_util_min=0.60,
    vllm_memory_util_max=0.90
)
evaluator = SpicaGPUAllocation(test_config=config)

# Test candidate
candidate = {"vllm_memory_util": 0.75, "whisper_model_size": "small"}
result = evaluator.run_test(candidate)

print(f"Status: {result.status}")
print(f"Validation: {result.validation_passed}")
print(f"Reason: {result.validation_reason}")
PYEOF
```

Expected: Should complete without starting any canary VLLM.

## Canary Mode Testing (Manual)

Canary mode requires manual setup for testing real VLLM canaries.

### 1. Enable Canary Mode
```bash
sudo -u kloros bash -c 'echo "KLR_CANARY_MODE=canary" >> /home/kloros/.kloros_env'
```

### 2. Start Canary VLLM Manually (for testing)
```bash
# Set spare GPU (or use quiesced maintenance window)
export CUDA_VISIBLE_DEVICES=1
export KLR_CANARY_PORT=9011

# Start canary VLLM
systemd-run --user --scope --unit=vllm-canary-test \
  /home/kloros/.venv/bin/python3 -m vllm.entrypoints.openai.api_server \
  --port 9011 \
  --model /home/kloros/models/llm/current \
  --gpu-memory-utilization 0.75
```

### 3. Test Canary Endpoints
Wait ~30s for canary to start, then test:
```bash
# Health check
curl -s http://127.0.0.1:9011/health | jq .

# Test completion
curl -s http://127.0.0.1:9011/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"/home/kloros/models/llm/current","prompt":"test","max_tokens":16}' | jq .
```

### 4. Run Canary Mode Test
```bash
cd /home/kloros
sudo -u kloros KLR_CANARY_MODE=canary PYTHONPATH=/home/kloros .venv/bin/python3 << 'PYEOF'
import sys
sys.path.insert(0, '/home/kloros')

from src.phase.domains.spica_gpu_allocation import SpicaGPUAllocation, GPUAllocationTestConfig

# Create evaluator (will detect MODE=canary from environment)
config = GPUAllocationTestConfig()
evaluator = SpicaGPUAllocation(test_config=config)

# Test candidate
candidate = {"vllm_memory_util": 0.75, "whisper_model_size": "small"}
result = evaluator.run_test(candidate)

print(f"Mode: canary")
print(f"Status: {result.status}")
print(f"Validation: {result.validation_passed}")
print(f"LLM Latency: {result.llm_latency_ms:.1f}ms")
PYEOF
```

### 5. Cleanup Canary
```bash
systemctl --user stop vllm-canary-test.scope
```

### 6. Restore Predictive Mode
```bash
sudo -u kloros sed -i '/KLR_CANARY_MODE=canary/d' /home/kloros/.kloros_env
```

## Monitoring

### 1. Audit Trail
View recent canary activity:
```bash
tail -20 /home/kloros/out/orchestration/epochs/gpu_canary_$(date +%Y%m%d).jsonl | jq .
```

### 2. Budget Usage
Check daily budget consumption:
```bash
jq . /home/kloros/.kloros/maintenance/gpu_budget_$(date +%Y%m%d).json
```

### 3. Lock History
Check if lock was recently held:
```bash
ls -lh /home/kloros/.kloros/locks/
```

## Troubleshooting

### Lock Stuck
If lock is stuck (process died without releasing):
```bash
# Check lock content
cat /home/kloros/.kloros/locks/gpu_maintenance.lock

# Verify PID is dead
ps -p <PID_FROM_LOCK>

# Force release (use with caution)
sudo -u kloros python3 << 'PYEOF'
import sys
sys.path.insert(0, '/home/kloros')
from src.kloros.orchestration.gpu_maintenance_lock import force_release_gpu_lock
force_release_gpu_lock()
print("✓ Lock force-released")
PYEOF
```

### Budget Exhausted
Check if daily budget is exhausted:
```bash
jq '.seconds_used' /home/kloros/.kloros/maintenance/gpu_budget_$(date +%Y%m%d).json
```

If needed, reset budget (emergency only):
```bash
echo '{"seconds_used": 0}' | jq . | sudo -u kloros tee /home/kloros/.kloros/maintenance/gpu_budget_$(date +%Y%m%d).json
```

### Canary Won't Start
Check VLLM service status:
```bash
systemctl status vllm.service --no-pager
journalctl -u vllm.service -n 50 --no-pager
```

Check GPU memory:
```bash
nvidia-smi
```

## Integration with D-REAM

The GPU canary system integrates with D-REAM config tuning:

1. **Observer** detects OOM events → creates intent
2. **Orchestrator** receives intent → invokes ConfigTuningRunner
3. **ConfigTuningRunner** spawns SPICA instances with MODE
4. **SPICA** checks MODE:
   - Predictive: Pre-flight math only (no downtime)
   - Canary: Hit canary endpoint for real metrics
5. **Promotion** written to `/home/kloros/out/promotions/` if candidate passes

## Safety Limits

The system enforces these hard limits:

- **Max downtime**: 60s per night (KLR_GPU_MAINTENANCE_MAX_DOWNTIME)
- **Maintenance window**: 03:00-07:00 America/New_York
- **Canary timeout**: 30s per test (KLR_CANARY_TIMEOUT)
- **Restore SLA**: 15s to restore production VLLM
- **Rate limiting**: Max 3 runs per 24h per subsystem, 6h cooldown

These limits prevent runaway testing from causing excessive downtime.
