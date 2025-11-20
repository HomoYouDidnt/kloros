# KLoROS GPU Allocation Strategy

**Date**: 2025-10-28 | **Status**: ✅ OPERATIONAL

---

## Executive Summary

Resolved PyTorch CUDA compatibility warnings and GPU memory exhaustion issues causing chat mode performance degradation. Reconfigured KLoROS to use only RTX 3060 (GPU 0) for all PyTorch workloads, excluding incompatible GTX 1080 Ti (GPU 1).

**Result**: Chat mode now operates with GPU acceleration, eliminating CPU fallback and restoring full performance.

---

## System Configuration

### Hardware
- **GPU 0**: NVIDIA GeForce RTX 3060 (12 GB, CUDA 7.5 / sm_86)
- **GPU 1**: NVIDIA GeForce GTX 1080 Ti (11 GB, CUDA 6.1 / sm_61)

### Software Stack
- **PyTorch**: 2.8.0+cu128 (requires compute capability 7.0+)
- **CUDA Driver**: 12.4 (550.163.01)
- **VLLM**: 0.11.0
- **OpenAI Whisper**: Various models (tiny to small)

---

## Root Cause Analysis

### Issue 1: PyTorch CUDA Compatibility
**Problem**: GTX 1080 Ti has CUDA compute capability 6.1 (Pascal architecture), below PyTorch 2.8.0 minimum requirement of 7.0 (Volta).

**Symptoms**:
```
UserWarning: Found GPU1 NVIDIA GeForce GTX 1080 Ti which is of cuda capability 6.1.
Minimum and Maximum cuda capability supported by this version of PyTorch is (7.0) - (12.0)
```

**Impact**: kloros.service was configured with `CUDA_VISIBLE_DEVICES=1` (GTX 1080 Ti), causing all PyTorch operations to fall back to CPU.

### Issue 2: GPU Memory Exhaustion (Before Fix)
**Problem**: RTX 3060 was saturated at 97% capacity with multiple competing processes.

**Memory Usage (Before)**:
- VLLM EngineCore: 6.7 GB (55% allocation)
- kloros_voice: Unable to allocate (OOM → CPU fallback)
- Ollama: 1.0 GB
- Other: 242 MB
- **Total**: 11.9 GB / 12.3 GB (97%)

**Impact**: Whisper STT could not allocate 152 MB, fell back to CPU with FP32 (FP16 not supported on CPU), causing severe performance degradation.

---

## Solution Implementation

### Changes Applied

#### 1. KLoROS Voice Service Configuration
**File**: `/etc/systemd/system/kloros.service`

**Changes**:
```diff
- Environment=CUDA_VISIBLE_DEVICES=1
+ Environment=CUDA_VISIBLE_DEVICES=0
+ Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

**Effect**:
- Excludes GTX 1080 Ti from PyTorch operations
- Enables expandable memory segments for better allocation
- All PyTorch workloads use RTX 3060

#### 2. VLLM Memory Optimization
**File**: `/etc/systemd/system/judge.service`

**Changes**:
```diff
- --gpu-memory-utilization 0.55
+ --gpu-memory-utilization 0.50
```

**Effect**:
- Reduced VLLM memory footprint from 55% to 50%
- Freed ~600 MB for kloros_voice
- Provides headroom for concurrent GPU operations

---

## Current GPU Allocation

### GPU 0 (RTX 3060 - 12 GB) - ACTIVE
**Usage**: 9.0 GB / 12.3 GB (73% utilization)

| Process | Memory | Purpose |
|---------|--------|---------|
| VLLM EngineCore | 6.1 GB | Judge service (Qwen 2.5 7B AWQ) |
| kloros_voice | 1.5 GB | Whisper STT + sentence transformers |
| Ollama | 1.0 GB | Local LLM serving |
| Standalone chat | 242 MB | Text-only chat interface |
| **Available** | **3.3 GB** | **Headroom for additional workloads** |

### GPU 1 (GTX 1080 Ti - 11 GB) - IDLE
**Usage**: 18 MB (baseline only)

**Status**: Excluded from PyTorch via `CUDA_VISIBLE_DEVICES=0`. Available for non-PyTorch CUDA workloads if needed.

**Limitation**: Cannot be used with PyTorch 2.8.0 due to compute capability 6.1 < 7.0 requirement.

**Options for Future Use**:
1. Downgrade PyTorch to 2.1.x or earlier (supports sm_61)
2. Create separate venv with older PyTorch for GTX 1080 Ti workloads
3. Use for non-PyTorch CUDA applications (TensorRT, raw CUDA, etc.)

---

## Verification Results

### PyTorch GPU Access
```bash
$ sudo -u kloros python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0)}')"
CUDA: True
Device: NVIDIA GeForce RTX 3060
```

### KLoROS Service Logs
```
[stt] Correction threshold: 0.75, GPU: 0
[openai-whisper] Loaded small model on cuda
INFO:sentence_transformers.SentenceTransformer:Use pytorch device_name: cuda:0
```

**Result**: ✅ No PyTorch compatibility warnings, GPU acceleration confirmed

---

## Service Configuration Summary

### kloros.service (Voice Assistant)
- **GPU**: CUDA_VISIBLE_DEVICES=0 (RTX 3060)
- **Memory Config**: PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
- **GPU Usage**: ~1.5 GB (Whisper + embeddings)
- **Performance**: GPU-accelerated STT, FP16 inference

### judge.service (VLLM)
- **GPU**: CUDA_VISIBLE_DEVICES=0 (RTX 3060)
- **Memory Limit**: 50% (--gpu-memory-utilization 0.50)
- **GPU Usage**: ~6.1 GB (Qwen 2.5 7B AWQ)
- **KV Cache**: ~370 MB (6,976 tokens)

### Shared Configuration
Both services coexist on GPU 0 with:
- Total allocation: ~9 GB / 12.3 GB (73%)
- Remaining headroom: 3.3 GB
- Memory allocation: Expandable segments enabled
- Restart policies: Automatic recovery on failure

---

## Performance Impact

### Before Fix
- **Whisper STT**: CPU fallback, FP32 inference
- **Latency**: High (CPU-bound)
- **Warnings**: PyTorch compatibility warnings on every startup
- **GPU Memory**: RTX 3060 at 97%, GTX 1080 Ti attempted but failed

### After Fix
- **Whisper STT**: GPU acceleration, FP16 inference
- **Latency**: Low (GPU-accelerated)
- **Warnings**: None (GTX 1080 Ti excluded)
- **GPU Memory**: RTX 3060 at 73%, GTX 1080 Ti idle

---

## Maintenance Guidelines

### Adding New GPU Workloads

**Check available memory**:
```bash
nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0
```

**Monitor real-time usage**:
```bash
watch -n 1 nvidia-smi
```

**Current headroom**: ~3.3 GB available on GPU 0

### Service Restart Sequence

When restarting GPU services:
```bash
# 1. Stop services in reverse dependency order
sudo systemctl stop kloros.service
sudo systemctl stop judge.service

# 2. Verify GPU is clear
nvidia-smi

# 3. Restart in dependency order
sudo systemctl start judge.service
sleep 15  # Wait for VLLM initialization
sudo systemctl start kloros.service
```

### Emergency GPU Release

If GPU runs out of memory:
```bash
# Stop non-critical GPU processes
sudo systemctl stop kloros.service  # Frees ~1.5 GB

# Or stop VLLM judge service
sudo systemctl stop judge.service  # Frees ~6 GB
```

### Adjusting VLLM Memory Allocation

Edit `/etc/systemd/system/judge.service`:
```bash
sudo systemctl edit --full judge.service
# Change --gpu-memory-utilization value (range: 0.30-0.90)
sudo systemctl daemon-reload
sudo systemctl restart judge.service
```

**Recommended ranges**:
- 0.50 (current): Balanced, leaves 6 GB for other workloads
- 0.40: Conservative, leaves 7.4 GB for other workloads
- 0.60: Aggressive, leaves 4.9 GB for other workloads

---

## Troubleshooting

### Symptom: PyTorch CUDA warnings return
**Check**: Verify `CUDA_VISIBLE_DEVICES=0` in service file
```bash
systemctl cat kloros.service | grep CUDA_VISIBLE_DEVICES
```

### Symptom: GPU out of memory errors
**Check**: Current GPU usage and identify memory hogs
```bash
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
```

**Action**: Reduce VLLM memory utilization or stop kloros.service temporarily

### Symptom: Whisper falls back to CPU
**Check**: Service logs for GPU initialization
```bash
sudo journalctl -u kloros.service -n 50 | grep -i "gpu\|cuda\|whisper"
```

**Expected output**: `[openai-whisper] Loaded small model on cuda`

### Symptom: Chat mode slow performance
**Check**: Verify GPU is being used
```bash
nvidia-smi dmon -s u -c 1
```

**Action**: If GPU utilization is 0%, restart kloros.service

---

## Future Optimization Opportunities

### 1. Model Quantization
- **Whisper**: Currently using FP16, could quantize to INT8 (smaller footprint)
- **Sentence Transformers**: Consider distilled models (e.g., all-MiniLM-L6-v2)

### 2. Dynamic GPU Scheduling
- Implement GPU scheduler to prioritize critical workloads
- Unload Whisper during idle periods
- Load models on-demand

### 3. GTX 1080 Ti Utilization
- Create separate venv with PyTorch 2.1.x for sm_61 support
- Offload specific workloads (e.g., D-REAM experiments) to GPU 1
- Use TensorRT for inference on GTX 1080 Ti

### 4. Memory-Efficient Alternatives
- **Whisper**: Faster-Whisper (CTranslate2 backend, 4x less VRAM)
- **VLLM**: Consider smaller models (1.5B-3B range) for judge tasks

---

## Related Documentation

- `/home/kloros/kloros_umbrella_permissions.txt` - Permission management
- `/home/kloros/ORCHESTRATION_IMPLEMENTATION.md` - Orchestration layer
- `/etc/systemd/system/kloros.service` - Voice assistant service
- `/etc/systemd/system/judge.service` - VLLM judge service

---

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 2025-10-28 | Set `CUDA_VISIBLE_DEVICES=0` in kloros.service | Exclude incompatible GTX 1080 Ti |
| 2025-10-28 | Added `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` | Improve memory allocation |
| 2025-10-28 | Reduced VLLM memory from 55% to 50% | Free headroom for kloros_voice |

---

**Status**: ✅ GPU allocation optimized, PyTorch warnings eliminated, chat mode performance restored
**Maintained By**: KLoROS Team | **Version**: 1.0
