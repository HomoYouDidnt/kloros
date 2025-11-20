# KLoROS Dual-GPU Architecture

**Last Updated**: 2025-10-23

## Hardware Configuration

| GPU | Model | VRAM | Compute Capability | PyTorch Compatible |
|-----|-------|------|-------------------|--------------------|
| GPU 0 | NVIDIA GeForce RTX 3060 | 12GB | 8.6 (Ampere) | ✅ YES |
| GPU 1 | NVIDIA GeForce GTX 1080 Ti | 11GB | 6.1 (Pascal) | ❌ NO |

## The Compatibility Problem

**PyTorch 2.8.0+cu128** only supports:
- Compute capabilities: sm_70, sm_75, sm_80, sm_86, sm_90, sm_100, sm_120
- GPU 0 (sm_86): ✅ Supported
- GPU 1 (sm_61): ❌ TOO OLD - not supported

**Ollama** uses its own bundled CUDA library:
- Supports both GPU 0 and GPU 1
- Each Ollama service configured to use specific GPU via systemd

## Configuration

### Environment Variable
```bash
CUDA_VISIBLE_DEVICES=0  # PyTorch apps can ONLY see GPU 0
```

**Why restricted to GPU 0?**
- Prevents PyTorch errors when it tries to use incompatible GPU 1
- GPU 1 is exclusively for Ollama (which has compatible CUDA library)

### GPU Allocation

```
GPU 0 (12GB RTX 3060):
├── Ollama Live (port 11434): ~9GB
│   └── qwen2.5:14b-instruct-q4_0
└── PyTorch apps: ~3GB available
    ├── Semantic embedder (46MB)
    ├── Whisper ASR (variable)
    └── Future models

GPU 1 (11GB GTX 1080 Ti):
└── Ollama Think (port 11435): ~5GB
    └── deepseek-r1:7b
```

## Automatic CPU Fallback

When GPU 0 is full, PyTorch apps automatically fall back to CPU:

**File**: `/home/kloros/src/reasoning/local_rag_backend.py:279-290`

```python
try:
    self._embedder = SentenceTransformer(model_name, device='cuda')
except RuntimeError as e:
    if 'CUDA out of memory' in str(e):
        # Automatic CPU fallback
        self._embedder = SentenceTransformer(model_name, device='cpu')
        print(f"[semantic] GPU full, retrying {model_name} on CPU")
```

## DO NOT Change These

❌ **Don't set `CUDA_VISIBLE_DEVICES=0,1`**
- PyTorch will see GPU 1 and throw errors
- GPU 1 is incompatible (compute capability too old)

❌ **Don't remove `CUDA_VISIBLE_DEVICES=0` from env files**
- Required to restrict PyTorch to compatible GPU

✅ **Current setup is optimal** for this hardware configuration

## Future: Autonomous GPU Management

When KLoROS's autonomous learning matures, she should:
1. Detect GPU memory pressure before loading models
2. Choose CPU vs GPU based on available VRAM
3. Propose PyTorch version changes if needed for multi-GPU support
4. Self-manage CUDA_VISIBLE_DEVICES based on capability detection

**Status**: Fix applied (2025-10-23) - semantic embedder now has graceful CPU fallback
