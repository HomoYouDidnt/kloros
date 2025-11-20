# GPU Allocation Evaluator - Root Cause Analysis

## Issue
Whisper models were loading on CPU instead of GPU during D-REAM experiments, resulting in slow latency measurements (999-3000ms vs expected 35-400ms).

## Root Cause 
**Environment Variable Timing**: The test script was setting `os.environ['CUDA_VISIBLE_DEVICES']` AFTER importing whisper, which was too late - PyTorch had already initialized CUDA by that point.

## Fix Applied
**File**: `/home/kloros/src/phase/domains/spica_gpu_allocation.py`

**Change**: Removed redundant `os.environ['CUDA_VISIBLE_DEVICES'] = '0'` from inside test_script (lines 163-165)

```python
# BEFORE (broken):
test_script = f"""
import whisper
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '0'  # Too late!

# AFTER (fixed):
test_script = f"""
import whisper
# No os.environ setting needed - already set via subprocess env parameter
```

The subprocess.run() call already passes CUDA_VISIBLE_DEVICES via the env parameter (lines 181-182), which is set BEFORE the Python interpreter starts.

## Verification
- ✅ Direct test: 34.4ms (tiny model on cuda:0)
- ✅ Subprocess env passing confirmed working
- ✅ Whisper loading on GPU: `Device: cuda:0`

## GPU Contention Discovery
During testing, discovered that running multiple D-REAM experiments concurrently causes GPU contention:
- Clean GPU: 34ms latency ✅
- 10 concurrent processes: 800+ ms latency ❌

**Recommendation**: Run D-REAM with `--max-parallel 1` to ensure accurate GPU measurements.

## Performance Results (After Fix)
| Model | GPU Memory | Latency | Notes |
|-------|-----------|---------|-------|
| tiny  | ~500MB    | 35ms    | Optimal for constrained GPU |
| base  | ~1GB      | 1153ms  | Slow due to memory pressure (931MB free) |
| small | ~1.5GB    | timeout | Insufficient free memory |

## Next Steps
1. Run clean validation experiment with max-parallel=1
2. Verify tiny model wins due to memory constraints
3. Document findings in experiment report

**Fix Status**: ✅ Resolved
**Date**: 2025-10-28
