# Real Metrics Module - Quick Reference

## Overview

`/home/kloros/src/tools/real_metrics.py` provides shared measurement utilities for D-REAM runner scripts.

## Basic Usage

### In Python Scripts

```python
import sys
sys.path.insert(0, "/home/kloros")
from src.tools.real_metrics import get_real_metrics

# Get all metrics at once
metrics = get_real_metrics(
    eval_audio_path="/home/kloros/assets/asr_eval/mini_eval_set/sample1.wav",
    params={"device": "cpu", "compute_type": "int8", "model_size": "base"}
)

# Access individual metrics
print(f"WER: {metrics['wer']:.3f}")
print(f"Score: {metrics['score']:.2f}")
print(f"Latency: {metrics['latency_ms']}ms")
print(f"VAD Boundary: {metrics['vad_boundary_ms']}ms")
print(f"Novelty: {metrics['novelty']:.2f}")
```

### In Bash Runner Scripts

```bash
#!/usr/bin/env bash
set -euo pipefail
source /opt/kloros/tools/common.sh

PARAMS_JSON="${1:-{}}"

/home/kloros/.venv/bin/python3 <<PYEVAL > "$PHASE_REPORT"
import sys, json, os
sys.path.insert(0, "/home/kloros")
from src.tools.real_metrics import get_real_metrics

# Parse parameters
params_str = """$PARAMS_JSON"""
params = json.loads(params_str) if params_str and params_str != '{}' else {}

# Get metrics
metrics = get_real_metrics(params=params)

# Generate PHASE report
result = {
    "epoch_id": os.environ.get("EPISODE_ID", "manual"),
    "run_id": "my_test",
    "test_id": "my_benchmark",
    "status": "pass",
    "latency_ms": metrics["latency_ms"],
    "score": metrics["score"],
    "wer": metrics["wer"],
    "vad_boundary_ms": metrics["vad_boundary_ms"],
    "novelty": metrics["novelty"],
    "holdout_ok": True,
    "params": params
}

print(json.dumps(result))
PYEVAL
```

## Individual Functions

### WER Measurement

```python
from src.tools.real_metrics import measure_wer_from_eval_set

wer = measure_wer_from_eval_set(
    eval_dir="/home/kloros/assets/asr_eval/mini_eval_set",
    backend="vosk",  # or "whisper"
    output_json="/tmp/wer_measurement.json"
)
# Returns: 0.0-1.0 (0.0 = perfect)
```

### Latency Measurement

```python
from src.tools.real_metrics import measure_asr_latency

latency_ms = measure_asr_latency(
    audio_path="/path/to/audio.wav",
    model_size="base",  # tiny, base, small, medium
    device="cpu"  # or "cuda"
)
# Returns: milliseconds (int)
```

### VAD Boundary Measurement

```python
from src.tools.real_metrics import measure_vad_boundary

vad_error_ms, segments = measure_vad_boundary(
    audio_path="/path/to/audio.wav",
    threshold=0.5,  # Silero VAD threshold
    sr=16000
)
# Returns: (error_ms: float, segments: List[dict])
# Segments format: [{'start': sample_idx, 'end': sample_idx}, ...]
```

### Score Normalization

```python
from src.tools.real_metrics import normalize_lang_score

score = normalize_lang_score(wer=0.25)
# WER ≤ 0.25  → Score ≥ 0.85 (passes 0.78 gate)
# WER 0.25-0.30 → Score 0.70-0.85
# WER ≥ 0.40  → Linear degradation
```

### Novelty Calculation

```python
from src.tools.real_metrics import calculate_novelty

novelty = calculate_novelty(
    params={"beam": 3, "temperature": 0.8},
    baseline_path="/home/kloros/.kloros/dream_config.json"
)
# Returns: 0.0-1.0 (0 = identical to baseline, 1 = very different)
```

## Parameter Options

### Device Selection

```python
# CPU (default)
metrics = get_real_metrics(params={"device": "cpu", "compute_type": "int8"})

# GPU (if available)
metrics = get_real_metrics(params={"device": "cuda", "compute_type": "float16"})
```

### Model Size Selection

```python
# Faster, less accurate
metrics = get_real_metrics(params={"model_size": "tiny"})

# Balanced (default)
metrics = get_real_metrics(params={"model_size": "base"})

# Slower, more accurate
metrics = get_real_metrics(params={"model_size": "medium"})
```

### VAD Threshold Tuning

```python
from src.tools.real_metrics import measure_vad_boundary

# Lower threshold = more sensitive (catches more speech)
vad_error_low, _ = measure_vad_boundary(audio_path, threshold=0.3)

# Higher threshold = less sensitive (stricter)
vad_error_high, _ = measure_vad_boundary(audio_path, threshold=0.5)
```

## Test Dataset

### Required Files

For WER measurement, you need:
```
/home/kloros/assets/asr_eval/mini_eval_set/
├── sample1.wav           # Audio file
├── sample1.txt           # Reference transcript
├── sample1.vad.json      # VAD ground truth (optional)
├── sample2.wav
├── sample2.txt
├── sample2.vad.json
└── sample3.wav
    sample3.txt
    sample3.vad.json
```

### VAD Ground Truth Format

```json
{
  "sample_rate": 16000,
  "segments_ms": [
    {"start": 50, "end": 1125},
    {"start": 1200, "end": 1900}
  ]
}
```

## Common Patterns

### Pattern 1: Generate Multiple Candidates with Variation

```python
# Get baseline metrics
baseline = get_real_metrics(params=params)

# Candidate 1: Baseline
candidate1 = {
    "run_id": "c1",
    "latency_ms": baseline["latency_ms"],
    "score": baseline["score"],
    "wer": baseline["wer"],
    "vad_boundary_ms": baseline["vad_boundary_ms"]
}

# Candidate 2: Degraded performance
candidate2 = {
    "run_id": "c2",
    "latency_ms": int(baseline["latency_ms"] * 1.2),  # 20% slower
    "score": max(0, baseline["score"] - 0.15),  # Lower quality
    "wer": min(1.0, baseline["wer"] + 0.05),  # Higher WER
    "vad_boundary_ms": baseline["vad_boundary_ms"] + 15
}
```

### Pattern 2: Before/After Comparison

```python
# Get baseline
baseline = get_real_metrics(params=params)

# Simulate degraded state
severity_map = {
    "low": {"wer_add": 0.04, "lat_mult": 1.1, "vad_add": 10},
    "mid": {"wer_add": 0.10, "lat_mult": 1.3, "vad_add": 25},
    "high": {"wer_add": 0.20, "lat_mult": 1.6, "vad_add": 50}
}

deg = severity_map["mid"]

degraded = {
    "status": "degraded",
    "wer": min(1.0, baseline["wer"] + deg["wer_add"]),
    "latency_ms": int(baseline["latency_ms"] * deg["lat_mult"]),
    "vad_boundary_ms": baseline["vad_boundary_ms"] + deg["vad_add"]
}

# Simulate repaired state
repaired = {
    "status": "pass",
    "wer": max(0.0, baseline["wer"] - 0.01),  # Slight improvement
    "latency_ms": baseline["latency_ms"],
    "vad_boundary_ms": baseline["vad_boundary_ms"]
}
```

### Pattern 3: Sweep Parameter Space

```python
# Test multiple configurations
results = []

for threshold in [0.30, 0.35, 0.40, 0.45, 0.50]:
    vad_error, segments = measure_vad_boundary(audio_path, threshold=threshold)

    results.append({
        "run_id": f"vad_{threshold:.2f}",
        "vad_threshold": threshold,
        "vad_boundary_ms": int(vad_error),
        "vad_segments": len(segments)
    })
```

## Fallback Behavior

If measurements fail (exceptions, missing dependencies), fallback values are used:

| Metric | Fallback Value | Reason |
|--------|----------------|--------|
| WER | 0.25 | Typical baseline performance |
| Latency | 180ms | Typical CPU int8 performance |
| VAD Boundary | 60.0ms | Conservative estimate |
| Novelty | 0.30 | Default parameter divergence |

**Important**: Check logs for exceptions if you see these exact values consistently.

## Debugging

### Test Module Directly

```bash
# Run self-test
python3 /home/kloros/src/tools/real_metrics.py
```

### Verify Dependencies

```bash
# Check torch/torchaudio
python3 -c "import torch, torchaudio; print(f'torch {torch.__version__}, torchaudio {torchaudio.__version__}')"

# Check faster-whisper
python3 -c "from faster_whisper import WhisperModel; print('faster-whisper: OK')"

# Check Silero VAD
python3 -c "import torch; torch.hub.load('snakers4/silero-vad', 'silero_vad'); print('Silero VAD: OK')"
```

### Measure Individual Components

```bash
# Test WER only
python3 -c "from src.tools.real_metrics import measure_wer_from_eval_set; print(f'WER: {measure_wer_from_eval_set():.3f}')"

# Test latency only
python3 -c "from src.tools.real_metrics import measure_asr_latency; print(f'Latency: {measure_asr_latency(\"/home/kloros/assets/asr_eval/mini_eval_set/sample1.wav\")}ms')"

# Test VAD only
python3 -c "from src.tools.real_metrics import measure_vad_boundary; err, segs = measure_vad_boundary('/home/kloros/assets/asr_eval/mini_eval_set/sample1.wav'); print(f'VAD: {err:.1f}ms, Segments: {len(segs)}')"
```

## Performance Tips

1. **Warm Caches**: First run loads models (~2-3s), subsequent runs use cache (~500ms)
2. **GPU Acceleration**: Use `device="cuda"` for 3-5× latency reduction on transcription
3. **Batch Processing**: Call `get_real_metrics()` once per run, reuse baseline for variations
4. **Timeouts**: WER measurement has 60s timeout, latency has no timeout (typically <1s)

## Integration Checklist

When creating a new D-REAM runner:

- [ ] Source `/opt/kloros/tools/common.sh` for environment setup
- [ ] Parse `PARAMS_JSON` from first argument
- [ ] Import `get_real_metrics` with `sys.path.insert(0, "/home/kloros")`
- [ ] Include `epoch_id` from `os.environ.get("EPISODE_ID")`
- [ ] Output JSONL to `$PHASE_REPORT` (one line per candidate)
- [ ] Call `bridge_phase_to_dream.py` with episode ID
- [ ] Trigger `on_phase_window_complete()` hook
- [ ] Include required fields: `run_id`, `test_id`, `status`, `latency_ms`, `score`, `wer`, `vad_boundary_ms`, `novelty`, `holdout_ok`, `params`

## Example Runners

See working examples:
- `/opt/kloros/tools/stt_bench` - Basic ASR benchmark
- `/opt/kloros/tools/vad_sweep` - Parameter sweep
- `/opt/kloros/tools/inject_fault` - Before/after comparison
