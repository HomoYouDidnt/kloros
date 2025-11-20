# Production-Realistic Testing for D-REAM GPU Evaluator

**Date**: 2025-10-28
**Version**: 1.0
**Status**: ✅ IMPLEMENTED & VALIDATED

---

## Executive Summary

Enhanced the D-REAM GPU allocation evaluator to match production constraints, preventing deployment of configurations that would fail in production. The improved evaluator now:

- ✅ Detects production services (kloros, judge, ollama)
- ✅ Validates VLLM model size + KV cache requirements
- ✅ Accounts for persistent services that won't be restarted
- ✅ Correctly rejects 40% VLLM allocation that failed in production
- ✅ Provides detailed validation reasons for debugging

---

## The Problem

### Original Issue (2025-10-28)

D-REAM GPU experiment identified 40% VLLM allocation as optimal, but deployment failed:

```
ValueError: No available memory for the cache blocks.
Try increasing `gpu_memory_utilization` when initializing the engine.
```

**Root Cause**: Experiment environment ≠ Production environment

| Aspect | Experiment | Production |
|--------|-----------|------------|
| Testing | Sequential, isolated | All services concurrent |
| Services | Only VLLM + Whisper | kloros + judge + ollama + others |
| Memory | Clean state per test | Fragmented, persistent allocations |
| Constraints | Simplified | Full production complexity |

**Result**: Winner configuration (40% VLLM) worked in experiments but failed in production.

---

## The Solution

### 1. Production Service Detection

Added `get_production_services()` method to detect running GPU services:

```python
def get_production_services(self) -> Dict[str, Any]:
    """Detect running production services and their GPU memory usage."""
    services = {
        "kloros": {"running": False, "memory_mb": 0, "pid": None},
        "judge": {"running": False, "memory_mb": 0, "pid": None},
        "ollama": {"running": False, "memory_mb": 0, "pid": None},
        "other": {"count": 0, "memory_mb": 0}
    }

    # Query nvidia-smi for GPU processes
    # Identify by process name and command line
    # Return service inventory with memory usage
```

**Detection Logic**:
- **kloros**: Python process with 'kloros_voice' in command line
- **judge**: Process name contains 'vllm' or 'EngineCore'
- **ollama**: Process name contains 'ollama'
- **other**: Any other GPU-using processes

**Example Output**:
```
kloros: 952MB (PID: 2816503)
judge: 6134MB (PID: 2839331)
ollama: 1068MB (PID: 2387058)
other: 1 processes, 242MB
```

---

### 2. VLLM Allocation Validation

Added `validate_vllm_allocation()` method with three critical checks:

#### Check 1: Model Size Constraint

VLLM allocation must fit the model + minimum KV cache:

```python
# Model size for Qwen2.5-7B-AWQ (from production data)
estimated_model_mb = 5700  # Conservative estimate

# VLLM allocation (% of total GPU, not available)
estimated_vllm_mb = total_mb * vllm_memory_util

# Minimum KV cache requirement
min_kv_cache_mb = 370  # From production: 370MB at 50%

# Check: Does allocation fit model + cache?
if estimated_vllm_mb < (estimated_model_mb + min_kv_cache_mb):
    return INVALID
```

**Why This Matters**:
- At 40%: 4915MB allocation < (5700MB model + 370MB cache) = **INVALID** ❌
- At 50%: 6144MB allocation > (5700MB model + 370MB cache) = **VALID** ✅

#### Check 2: Persistent Services

Account for services that stay loaded (not restarted with judge):

```python
# Calculate persistent services memory
persistent_mb = 0
persistent_mb += services["kloros"]["memory_mb"]  # ~950MB
persistent_mb += services["ollama"]["memory_mb"]   # ~1068MB
persistent_mb += services["other"]["memory_mb"]    # ~242MB
# Total: ~2260MB

# Available for VLLM = Total GPU - Persistent services
available_for_vllm = total_mb - persistent_mb
```

**Key Insight**: Only judge service is restarted when testing VLLM allocations. Kloros, Ollama, and other services remain resident in GPU memory.

#### Check 3: Total Memory Check

Verify VLLM allocation fits with persistent services:

```python
if available_for_vllm < estimated_vllm_mb:
    return INVALID  # Would fail in production
```

---

### 3. Pre-Flight Validation

Integrated validation into `run_test()` before measurements:

```python
def run_test(self, candidate: Dict[str, Any]) -> GPUAllocationTestResult:
    # Get GPU state (includes production services)
    gpu_state = self.get_gpu_state()

    # PRE-FLIGHT VALIDATION
    validation = self.validate_vllm_allocation(vllm_util, gpu_state)

    if not validation["valid"]:
        # Return early - config would fail in production
        return GPUAllocationTestResult(
            status="invalid_production",
            validation_passed=False,
            validation_reason=validation["reason"],
            stt_latency_ms=999.0,  # Not measured
            llm_latency_ms=999.0,
            # ... other fields
        )

    # Validation passed - proceed with measurements
    stt_latency = self.measure_stt_latency(whisper_model)
    llm_latency = self.measure_llm_latency()
    # ... continue test
```

**Benefits**:
- ✅ Fast failure - reject invalid configs without expensive measurements
- ✅ Detailed reasons - log exactly why config is invalid
- ✅ Zero fitness - invalid configs get 0.0 fitness, never promoted

---

## Validation Results

### Test 1: Known-Good Config (50% VLLM)

**Input**:
```json
{
  "vllm_memory_util": 0.50,
  "whisper_model_size": "tiny"
}
```

**Validation**:
```
✅ VALID
Reason: 6144MB allocation fits model (5700MB) + KV cache (444MB)
        with persistent services (2262MB)

Breakdown:
- VLLM Allocation: 6144MB (50% of 12288MB)
- Model Size: 5700MB
- KV Cache: 444MB (6144 - 5700)
- Persistent Services: 2262MB (kloros + ollama + other)
- Available: 10026MB (12288 - 2262)
- Fits: YES (6144 < 10026)
```

### Test 2: Known-Bad Config (40% VLLM)

**Input**:
```json
{
  "vllm_memory_util": 0.40,
  "whisper_model_size": "tiny"
}
```

**Validation**:
```
❌ INVALID
Reason: VLLM allocation (4915MB) too small for model+cache
        (need 6070MB, deficit: 1155MB)

Breakdown:
- VLLM Allocation: 4915MB (40% of 12288MB)
- Model Size: 5700MB
- Min KV Cache: 370MB
- Required: 6070MB (5700 + 370)
- Fits: NO (4915 < 6070)
- Deficit: 1155MB
```

**Result**: Correctly rejected - matches production failure! ✅

---

## Implementation Details

### File Modified

`/home/kloros/src/phase/domains/spica_gpu_allocation.py`

### Changes Made

1. **Added `GPUAllocationTestResult` fields** (lines 73-76):
   ```python
   validation_passed: bool = True
   validation_reason: str = ""
   production_services: Optional[Dict[str, Any]] = None
   ```

2. **Added `get_production_services()` method** (lines 113-173):
   - Queries nvidia-smi for GPU processes
   - Identifies kloros, judge, ollama by name/command
   - Returns service inventory with memory usage

3. **Added `validate_vllm_allocation()` method** (lines 175-285):
   - Check 1: Model size + KV cache constraint
   - Check 2: Persistent services accounting
   - Check 3: Total memory availability
   - Returns validation dict with detailed breakdown

4. **Modified `get_gpu_state()` method** (lines 287-329):
   - Now calls `get_production_services()`
   - Includes production services in returned state

5. **Modified `run_test()` method** (lines 363-450):
   - Calls validation before measurements
   - Returns early if validation fails
   - Includes validation info in results

6. **Modified `compute_fitness()` method** (line 454):
   - Now checks `validation_passed` flag
   - Returns 0.0 fitness for invalid production configs

### Backward Compatibility

All new fields use default values, ensuring compatibility with existing code:
- `validation_passed: bool = True` (assumes valid if not checked)
- `validation_reason: str = ""` (empty if not validated)
- `production_services: Optional[Dict] = None` (None if not detected)

---

## Usage Guide

### Running Production-Realistic Tests

```python
from src.phase.domains.spica_gpu_allocation import SpicaGPUAllocation

# Create evaluator
evaluator = SpicaGPUAllocation()

# Test a configuration
candidate = {
    "vllm_memory_util": 0.40,
    "whisper_model_size": "tiny"
}

# Evaluate (includes pre-flight validation)
result = evaluator.evaluate(candidate)

# Check result
if result["status"] == "invalid_production":
    print(f"Config rejected: {result.validation_reason}")
elif result["status"] == "pass":
    print(f"Config valid! Fitness: {result['fitness']:.3f}")
```

### Interpreting Validation Results

**Status Values**:
- `"invalid"`: Out of bounds (VLLM util not in min/max range)
- `"invalid_production"`: Would fail in production (pre-flight validation failed)
- `"pass"`: All checks passed, measurements successful
- `"fail"`: Measurements completed but OOM detected

**Validation Reasons** (examples):
```
"VLLM allocation (4915MB) too small for model+cache (need 6070MB, deficit: 1155MB)"
→ Model size constraint violated

"Insufficient GPU memory with persistent services: need 6144MB, have 5800MB (persistent: 6488MB)"
→ Persistent services constraint violated

"Valid: 6144MB allocation fits model (5700MB) + KV cache (444MB) with persistent services (2262MB)"
→ All checks passed
```

---

## Testing

### Manual Validation Test

Run the production validation test:

```bash
PYTHONPATH=/home/kloros:/home/kloros/src \
  /home/kloros/.venv/bin/python3 \
  /tmp/test_production_validation.py
```

**Expected Output**:
```
✅ Good config (50%) correctly validated as VALID
✅ Bad config (40%) correctly rejected as INVALID
✅ ALL TESTS PASSED - Validation logic working correctly!
```

### D-REAM Integration

The enhanced evaluator integrates seamlessly with D-REAM:

```bash
# Run D-REAM experiment with production-realistic validation
cd /home/kloros
/home/kloros/.venv/bin/python3 -m src.dream.runner \
  --config /home/kloros/src/dream/config/dream.yaml \
  --logdir /home/kloros/logs/dream \
  --epochs-per-cycle 1
```

**What Changes**:
- Invalid production configs get status="invalid_production"
- Fitness = 0.0 for invalid configs
- Logs show validation reasons
- R-Zero selection naturally avoids invalid configs
- Winner will be production-viable

---

## Production Constraints Captured

The validation now captures these real-world constraints:

### 1. Model Size Constraint
**Reality**: Qwen2.5-7B-AWQ model is ~5700MB
**Validation**: VLLM allocation must fit model + min 370MB KV cache
**Example**: 40% (4915MB) < 6070MB needed → **REJECT**

### 2. Persistent Services
**Reality**: kloros (~950MB), ollama (~1068MB) stay loaded
**Validation**: Account for ~2260MB persistent services
**Example**: Total GPU 12288MB - 2262MB persistent = 10026MB available

### 3. KV Cache Requirement
**Reality**: VLLM needs contiguous space for cache blocks
**Validation**: Minimum 370MB based on production data at 50%
**Example**: At 50%, 6144MB allocation - 5700MB model = 444MB KV cache ✅

### 4. Concurrent Services
**Reality**: All services run simultaneously (not sequential)
**Validation**: Check all services via nvidia-smi at test time
**Example**: kloros + judge + ollama all detected and measured

---

## Lessons Learned

### What Worked ✅

1. **Empirical Model Size**: Used production data (50% allocation) to derive model size
2. **Service Detection**: nvidia-smi + ps command combination reliably identifies services
3. **Multi-Check Validation**: Three independent checks catch different failure modes
4. **Early Rejection**: Pre-flight validation saves time vs. attempting invalid configs
5. **Detailed Logging**: Validation reasons help debug and understand rejections

### What to Watch ⚠️

1. **Model Size Changes**: If VLLM model changes, update `estimated_model_mb`
2. **New Services**: Add detection for any new GPU-using services
3. **Memory Fragmentation**: Current validation assumes contiguous allocation possible
4. **Dynamic Workloads**: Validation uses snapshot; real load may vary

### Future Improvements

1. **Dynamic Model Detection**: Query VLLM for actual model size vs hardcoded
2. **Fragmentation Modeling**: Account for memory fragmentation explicitly
3. **Load-Based Validation**: Test under various workload conditions
4. **Staging Environment**: Add staging tier between experiments and production
5. **Adaptive Thresholds**: Learn optimal KV cache requirements from production metrics

---

## Impact Assessment

### Immediate Benefits

- ✅ Prevents deployment of configurations that would fail in production
- ✅ Saves time - no need to rollback failed deployments
- ✅ Increases confidence in D-REAM recommendations
- ✅ Provides detailed diagnostics for configuration tuning

### Long-Term Benefits

- ✅ Future GPU experiments will be production-realistic
- ✅ Framework can be extended to other resource constraints
- ✅ Enables safe autonomous optimization
- ✅ Documents production constraints for operational knowledge

### Metrics

**Before Production-Realistic Validation**:
- D-REAM winner: 40% VLLM + tiny Whisper
- Deployment success rate: 50% (1 of 2 optimizations)
- Rollbacks required: 1 (VLLM allocation)

**After Production-Realistic Validation**:
- D-REAM will reject 40% VLLM (invalid_production)
- Expected deployment success rate: 100% (only valid configs promoted)
- Rollbacks required: 0 (invalid configs never reach deployment)

---

## References

### Related Documentation
- `/home/kloros/FINAL_DEPLOYMENT_REPORT.md` - Original deployment and failure analysis
- `/home/kloros/VLLM_ALLOCATION_TEST_REPORT.md` - 40% VLLM failure details
- `/home/kloros/GPU_OPTIMIZATION_QUICK_REF.md` - Current production config
- `/home/kloros/src/phase/domains/spica_gpu_allocation.py` - Implementation

### Production Data Sources
- nvidia-smi GPU memory queries
- judge.service systemd logs (KV cache: 370MB at 50%)
- Production GPU usage patterns (kloros + judge + ollama)

### Test Artifacts
- `/tmp/test_production_validation.py` - Validation test script
- `/tmp/spica_backup.py` - Pre-modification backup

---

## Conclusion

The production-realistic testing enhancements successfully address the gap between experiment conditions and production reality. The improved D-REAM GPU evaluator now:

1. ✅ Correctly rejects 40% VLLM allocation (failed in production)
2. ✅ Correctly validates 50% VLLM allocation (succeeds in production)
3. ✅ Accounts for all production services and constraints
4. ✅ Provides detailed validation reasons for debugging
5. ✅ Integrates seamlessly with existing D-REAM framework

**Next D-REAM experiments will produce production-viable winners! 🚀**

---

**Document Version**: 1.0
**Last Updated**: 2025-10-28
**Author**: Claude (KLoROS Autonomous Agent)
**Status**: Production-deployed and validated
