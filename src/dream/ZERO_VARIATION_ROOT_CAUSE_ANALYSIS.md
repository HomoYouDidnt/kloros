# D-REAM Zero Variation Root Cause Analysis

**Date**: 2025-10-19
**Issue**: All D-REAM optimization runs produce identical scores (0.850) regardless of dataset or hyperparameters

---

## Root Causes Identified

### 1. **Hardcoded Dataset Path** (FIXED ✓)

**Location**: `/opt/kloros/tools/stt_bench:44` and `/home/kloros/src/tools/real_metrics.py:319`

**Problem**:
```python
# OLD CODE (stt_bench)
metrics = get_real_metrics(
    eval_audio_path="/home/kloros/assets/asr_eval/mini_eval_set/sample1.wav",  # HARDCODED
    params=params
)

# OLD CODE (real_metrics.py)
def get_real_metrics(
    eval_audio_path: str = "/home/kloros/assets/asr_eval/mini_eval_set/sample1.wav",  # HARDCODED
    ...
):
    wer = measure_wer_from_eval_set()  # Doesn't pass eval_dir!
```

Even when `dataset_path` was passed in params, it was completely ignored. All evaluations always used `mini_eval_set` (3 samples).

**Fix Applied**:
- Updated `stt_bench` to extract `dataset_path` from params and pass to `get_real_metrics()`
- Updated `real_metrics.py` to accept `dataset_dir` parameter and pass to WER measurement
- Changed parameter from `eval_audio_path` (single file) to `dataset_dir` (directory)

**Files Modified**:
- `/opt/kloros/tools/stt_bench` (backup: `stt_bench.backup_hardcoded`)
- `/home/kloros/src/tools/real_metrics.py` (backup: `real_metrics.py.backup_hardcoded`)

---

### 2. **WER Measurement Architecture Mismatch** (NOT FIXED - Critical Issue)

**Location**: `/home/kloros/tools/audio/asr_wer.py`

**Problem**:
The WER is measured by **Vosk ASR** (HTTP service on port 8080), NOT by Whisper!

```python
# From asr_wer.py
parser.add_argument("--backend", default="vosk", choices=["vosk"],
                    help="ASR backend to evaluate")
```

**Architecture**:
```
D-REAM Optimization
  ↓
stt_bench (receives Whisper hyperparameters: beam, temperature, vad_threshold)
  ↓
real_metrics.py (ignores Whisper hyperparameters for WER)
  ↓
asr_wer.py (calls Vosk HTTP service on :8080)
  ↓
Vosk ASR (completely different model, no hyperparameter support)
```

**Why This Causes Zero Variation**:
- **WER** (primary metric, 85% weight in score) is measured by Vosk with NO hyperparameter configuration
- Changing Whisper beam/temperature/vad_threshold has ZERO effect on WER
- Latency is measured by Whisper but only uses device/model_size (not beam/temperature)
- VAD is measured independently of ASR

**Result**: All hyperparameter combinations produce identical WER → identical scores

---

### 3. **Port Conflict: Dashboard vs Vosk** (BLOCKING)

**Problem**:
- D-REAM dashboard runs on port 8080 (http://localhost:8080)
- Vosk ASR service ALSO expects port 8080
- Port conflict → Vosk unavailable → WER measurement falls back to 0.25

**Evidence**:
```bash
$ curl http://localhost:8080
<!doctype html>  # Dashboard HTML, not Vosk JSON API
```

**Result**: WER always returns fallback value 0.25 because Vosk service unreachable

---

## Impact Summary

### What Works:
✓ D-REAM infrastructure (GA optimization, quality gates, dashboard)
✓ Dataset conversion (LibriSpeech, GLaDOS with real Silero VAD)
✓ Artifact generation (pack.json, lineage, admission/quarantine)
✓ Parameter tagging (hyperparameters correctly stored in artifacts)

### What Doesn't Work:
✗ WER measurement uses wrong ASR backend (Vosk instead of Whisper)
✗ Hyperparameters have no effect on WER (primary metric)
✗ Port conflict blocks Vosk service entirely
✗ Score variation impossible due to architecture mismatch

---

## Evidence

### Test 1: Mini Eval Set (3 samples)
- WER: 0.2500
- Score: 0.8500
- Dataset: mini_eval_set

### Test 2: GLaDOS (1579 samples, quality variation)
- WER: 0.2500 (identical)
- Score: 0.8500 (identical)
- Dataset: glados_full_dataset

### Test 3: LibriSpeech (200 samples, real human speech)
- WER: 0.2500 (identical)
- Score: 0.8500 (identical)
- Dataset: librispeech_eval_set

### Test 4: Different Hyperparameters
- beam=1,2,3,5: WER always 0.2500
- vad_threshold=0.25-0.58: WER always 0.2500
- temperature=0.08-0.35: WER always 0.2500

**Conclusion**: WER is constant because it's measured by Vosk (not affected by Whisper hyperparameters or dataset quality)

---

## Recommended Fixes

### Option 1: Quick Fix - Use Whisper for WER (Recommended)

**Pros**: Minimal changes, uses D-REAM's intended ASR backend
**Cons**: Requires implementing WER measurement in Whisper

**Implementation**:
1. Update `real_metrics.py` to add `measure_wer_with_whisper()` function
2. Use faster-whisper library to transcribe dataset with specified hyperparameters
3. Calculate WER against ground truth using Levenshtein distance
4. Pass hyperparameters (beam, temperature, etc.) to Whisper transcription
5. Bypass asr_wer.py entirely

**Expected Result**: Different hyperparameters → different WER → score variation

---

### Option 2: Fix Vosk Integration

**Pros**: Keeps existing architecture
**Cons**: Vosk still doesn't support Whisper hyperparameters

**Implementation**:
1. Move D-REAM dashboard to different port (e.g., 5000)
2. Start Vosk service on port 8080
3. Still won't show hyperparameter variation (Vosk has no beam/temperature)

**Expected Result**: Consistent WER measurement, but no hyperparameter sensitivity

---

### Option 3: Hybrid Approach

**Use**:
- Whisper for latency + WER measurement (with hyperparameters)
- Silero VAD for boundary detection (existing)

**Pros**: Complete control, hyperparameters affect all metrics
**Cons**: More complex implementation

---

## Next Steps

### Immediate (to unblock testing):
1. Implement `measure_wer_with_whisper()` in `real_metrics.py`
2. Update to use faster-whisper with configurable hyperparameters
3. Test with LibriSpeech to verify score variation

### Follow-up:
1. Document that Vosk backend is deprecated
2. Update all evaluation docs to reference Whisper-based WER
3. Add hyperparameter sensitivity tests to D-REAM validation

---

## Files Modified

### Backups Created:
- `/opt/kloros/tools/stt_bench.backup_hardcoded`
- `/home/kloros/src/tools/real_metrics.py.backup_hardcoded`

### Current Status:
- ✓ Dataset path routing fixed
- ✗ WER measurement still uses Vosk
- ✗ Hyperparameters have no effect
- ✗ Port conflict blocks Vosk service

---

## Test Commands

### Verify Dataset Path Fix:
```bash
sudo -u kloros bash -c 'export DREAM_ARTIFACTS=/home/kloros/src/dream/artifacts && \
  export PYTHONPATH=/home/kloros:$PYTHONPATH && \
  export EPISODE_ID=test_dataset_fix && \
  /opt/kloros/tools/stt_bench '"'"'{"dataset_path":"/home/kloros/assets/asr_eval/librispeech_eval_set"}'"'"''

# Check results
cat /home/kloros/src/dream/artifacts/candidates/*/pack.json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print(f'Dataset: {d[\"candidates\"][0][\"params\"].get(\"dataset_path\", \"NOT SET\")}')"
```

### After Whisper WER Fix (to be implemented):
```bash
# Run optimization - should show score variation
sudo -u kloros bash -c 'export DREAM_ARTIFACTS=/home/kloros/src/dream/artifacts && \
  export PYTHONPATH=/home/kloros:$PYTHONPATH && \
  export EPISODE_ID=whisper_wer_test && \
  /opt/kloros/tools/dream/run_hp_search '"'"'{"dataset_path":"/home/kloros/assets/asr_eval/librispeech_eval_set","domain":"asr_tts","generations":3,"population_size":6}'"'"''

# Expected: Score range 0.70-0.92 (variation based on hyperparameters)
```

---

## Summary

The zero variation issue has **three root causes**:
1. ✓ **FIXED**: Hardcoded dataset path
2. ✗ **CRITICAL**: WER measured by Vosk (not Whisper) - hyperparameters have no effect
3. ✗ **BLOCKING**: Port 8080 conflict - Vosk service unreachable

**Primary Fix Needed**: Implement Whisper-based WER measurement with hyperparameter support in `real_metrics.py`
