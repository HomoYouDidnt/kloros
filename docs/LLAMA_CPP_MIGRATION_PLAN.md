# KLoROS Migration Plan: Ollama to llama.cpp

## Executive Summary

This document analyzes the migration from Ollama to llama.cpp for KLoROS's LLM inference needs. The migration trades Ollama's convenience features for llama.cpp's lower-level control, better performance, and reduced resource overhead.

---

## Current Ollama Usage Analysis

### Files Affected (59 files reference Ollama)

Key integration points:
- `src/reasoning/base.py` - Primary OllamaReasoner class
- `src/reasoning/llm_router.py` - Multi-instance routing (live/think/deep/code modes)
- `src/config/models_config.py` - Model configuration and selection
- `src/kloros/interfaces/voice/llm_service.py` - Voice pipeline LLM integration
- `src/kloros/interfaces/voice/streaming.py` - Streaming response handler
- `src/dream/agent/llm.py` - Dream system LLM integration
- `src/kloros/mind/memory/condenser.py` - Memory condensation
- `src/kloros/mind/memory/simple_rag.py` - RAG system
- `src/kloros/mind/research/judge.py` - Research judge system

### API Endpoints Currently Used

| Endpoint | Purpose | Usage Count |
|----------|---------|-------------|
| `/api/generate` | Text completion | Primary (all LLM calls) |
| `/api/tags` | Health check / model listing | 7 locations |

### Ollama-Specific Parameters Used

```python
# GPU allocation
"num_gpu": 999      # Use all GPU layers
"main_gpu": 0       # Primary GPU index

# Context management
"num_ctx": 16384    # Context window (VRAM-aware)

# Sampling
"temperature": 0.6-0.8
"top_p": 0.9-0.95
"repeat_penalty": 1.1

# Streaming
"stream": True/False
```

---

## llama.cpp Server Capabilities

### OpenAI-Compatible Endpoints

| Endpoint | Purpose | Equivalent Ollama |
|----------|---------|-------------------|
| `POST /v1/chat/completions` | Chat completion | `/api/chat` |
| `POST /v1/completions` | Text completion | `/api/generate` |
| `POST /v1/embeddings` | Embeddings | `/api/embeddings` |
| `GET /v1/models` | Model info | `/api/tags` |

### Native llama.cpp Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /completion` | Native completion (more control) |
| `GET /health` | Health check |
| `GET /props` | Server properties |
| `GET /slots` | Slot status (concurrent requests) |
| `GET /metrics` | Prometheus metrics |
| `POST /tokenize` | Tokenization |
| `POST /detokenize` | Detokenization |
| `POST /embedding` | Native embeddings |
| `POST /reranking` | Document reranking |

### llama.cpp Server Parameters

```bash
# GPU layers (equivalent to num_gpu)
llama-server -ngl 99  # Number of layers to offload to GPU

# Context size (equivalent to num_ctx)
llama-server -c 16384

# Parallel slots (concurrent requests)
llama-server -np 4

# Flash attention (better memory efficiency)
llama-server -fa

# Continuous batching
llama-server -cb
```

---

## Features Lost in Migration

### 1. Model Management (HIGH IMPACT)

**Ollama provides:**
- `ollama pull model:tag` - Download models from registry
- `ollama list` - Show downloaded models
- Automatic model caching in `~/.ollama/models`
- Version tracking and updates
- Modelfile for custom configurations

**llama.cpp requires:**
- Manual GGUF file download and storage
- Manual model path specification
- No built-in registry or version management

**Replacement Strategy:**
```python
# New module: src/kloros/model_manager.py
class ModelManager:
    """
    Manages GGUF model files for llama.cpp.
    Replaces Ollama's model management.
    """

    MODEL_REGISTRY = {
        "qwen2.5:32b-instruct-q4_K_M": {
            "url": "https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-GGUF/resolve/main/qwen2.5-32b-instruct-q4_k_m.gguf",
            "filename": "qwen2.5-32b-instruct-q4_k_m.gguf",
            "size_gb": 18.5,
            "min_vram_gb": 12
        },
        # ... other models
    }

    def __init__(self, model_dir: str = "/home/kloros/models/gguf"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def get_model_path(self, model_name: str) -> Path | None:
        """Get local path for model, downloading if needed."""
        pass

    def list_models(self) -> list[dict]:
        """List available local models."""
        pass

    def download_model(self, model_name: str) -> bool:
        """Download model from HuggingFace."""
        pass
```

### 2. Multi-Model Hot Swapping (MEDIUM IMPACT)

**Ollama provides:**
- Load different models per request
- Automatic model loading/unloading
- Shared model cache across instances

**llama.cpp requires:**
- One model per server instance
- Server restart to change models
- Manual memory management

**Replacement Strategy:**
```python
# Multi-instance llama-server management
# Extend src/reasoning/llm_router.py

LLAMA_INSTANCES = {
    "live": {
        "port": 8080,
        "model": "qwen2.5-32b-instruct-q4_k_m.gguf",
        "ngl": 99,
        "ctx": 16384,
        "np": 2  # parallel slots
    },
    "code": {
        "port": 8081,
        "model": "qwen2.5-coder-32b-q4_k_m.gguf",
        "ngl": 99,
        "ctx": 32768,
        "np": 1
    }
}

# Systemd services for each instance:
# kloros-llama-live.service
# kloros-llama-code.service
```

### 3. Dynamic GPU Allocation (LOW IMPACT)

**Ollama provides:**
- `num_gpu: 999` per request
- `main_gpu: 0` per request
- Dynamic layer offloading

**llama.cpp requires:**
- `-ngl N` at server startup
- Fixed GPU allocation per instance

**Replacement Strategy:**
- Configure GPU layers at service startup
- Use systemd environment files for GPU configuration
- Remove per-request GPU parameters from code

### 4. Health Check Endpoint Format (LOW IMPACT)

**Ollama:** `GET /api/tags` returns model list
**llama.cpp:** `GET /health` returns status, `GET /v1/models` returns model info

**Replacement Strategy:**
```python
def check_llama_health(url: str) -> bool:
    """Health check compatible with both Ollama and llama.cpp."""
    try:
        # Try llama.cpp first
        r = requests.get(f"{url}/health", timeout=2)
        if r.status_code == 200:
            return r.json().get("status") == "ok"
    except:
        pass

    # Fallback to Ollama
    try:
        r = requests.get(f"{url}/api/tags", timeout=2)
        return r.status_code == 200
    except:
        return False
```

---

## API Adapter Layer

### Ollama-to-llama.cpp Request Translation

```python
# New module: src/reasoning/llama_adapter.py

class LlamaAdapter:
    """
    Adapts Ollama-style requests to llama.cpp server format.
    Provides drop-in replacement for OllamaReasoner.
    """

    def __init__(self, base_url: str, model_name: str = None):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name  # Not used per-request in llama.cpp

    def generate(self, text: str, **kwargs) -> str:
        """
        Ollama-compatible generate() method using llama.cpp /completion.

        Translates:
        - prompt -> prompt
        - system -> prepended to prompt (or use /v1/chat/completions)
        - temperature -> temperature
        - num_ctx -> ignored (set at server startup)
        - num_gpu -> ignored (set at server startup)
        - stream -> stream
        """
        # Option 1: Use native /completion
        payload = {
            "prompt": text,
            "temperature": kwargs.get("temperature", 0.8),
            "top_p": kwargs.get("top_p", 0.95),
            "repeat_penalty": kwargs.get("repeat_penalty", 1.1),
            "n_predict": kwargs.get("num_predict", -1),
            "stream": kwargs.get("stream", False),
        }

        if kwargs.get("stream"):
            return self._stream_completion(payload)

        r = requests.post(
            f"{self.base_url}/completion",
            json=payload,
            timeout=kwargs.get("timeout", 120)
        )
        r.raise_for_status()
        return r.json().get("content", "").strip()

    def _stream_completion(self, payload: dict):
        """Handle streaming responses."""
        r = requests.post(
            f"{self.base_url}/completion",
            json=payload,
            stream=True,
            timeout=120
        )

        complete = ""
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line)
                token = chunk.get("content", "")
                complete += token
                if chunk.get("stop"):
                    break

        return complete.strip()
```

---

## Migration Implementation Plan

### Phase 1: Foundation (Week 1-2)

1. **Create model manager module**
   - `src/kloros/model_manager.py`
   - GGUF download from HuggingFace
   - Local model inventory
   - Model path resolution

2. **Create llama adapter module**
   - `src/reasoning/llama_adapter.py`
   - Ollama-compatible interface
   - Request translation
   - Response normalization

3. **Create systemd service templates**
   - `kloros-llama-live.service`
   - `kloros-llama-code.service`
   - Environment file configuration

### Phase 2: Integration (Week 2-3)

4. **Update reasoning backend factory**
   - Add `llama` backend type to `create_reasoning_backend()`
   - Support both Ollama and llama.cpp during transition

5. **Update LLM router**
   - Modify `LLMRouter.SERVICES` for llama.cpp ports
   - Update health check logic
   - Update model selection logic

6. **Update config module**
   - Add llama.cpp-specific configuration
   - Update `get_ollama_url()` -> `get_llm_url()`
   - Deprecate Ollama-specific options

### Phase 3: Migration (Week 3-4)

7. **Migrate voice pipeline**
   - Update `llm_service.py`
   - Update `streaming.py`
   - Test voice interaction end-to-end

8. **Migrate dream system**
   - Update `dream/agent/llm.py`
   - Test code generation workflows

9. **Migrate memory/RAG systems**
   - Update `condenser.py`
   - Update `simple_rag.py`
   - Update `judge.py`

### Phase 4: Cleanup (Week 4)

10. **Remove Ollama dependencies**
    - Remove Ollama-specific code paths
    - Update documentation
    - Remove Ollama services

11. **Performance testing**
    - Benchmark latency
    - Memory usage comparison
    - Concurrent request handling

---

## Systemd Service Configuration

### kloros-llama-live.service

```ini
[Unit]
Description=KLoROS LLaMA Live Instance
After=network.target

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros

# GPU 0, 32k context, 2 parallel slots, flash attention
ExecStart=/usr/local/bin/llama-server \
    -m /home/kloros/models/gguf/qwen2.5-32b-instruct-q4_k_m.gguf \
    --host 127.0.0.1 \
    --port 8080 \
    -ngl 99 \
    -c 32768 \
    -np 2 \
    -fa \
    -cb \
    --metrics

Environment=CUDA_VISIBLE_DEVICES=0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### kloros-llama-code.service

```ini
[Unit]
Description=KLoROS LLaMA Code Instance
After=network.target

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros

# GPU 1, 32k context, 1 slot for code generation
ExecStart=/usr/local/bin/llama-server \
    -m /home/kloros/models/gguf/qwen2.5-coder-32b-q4_k_m.gguf \
    --host 127.0.0.1 \
    --port 8081 \
    -ngl 99 \
    -c 32768 \
    -np 1 \
    -fa \
    -cb

Environment=CUDA_VISIBLE_DEVICES=1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Benefits of Migration

### Performance
- **Lower latency**: llama.cpp has less overhead than Ollama
- **Flash attention**: Built-in support for memory-efficient attention
- **Continuous batching**: Better throughput under load
- **Speculative decoding**: Available for compatible model pairs

### Resource Efficiency
- **No model reload**: Eliminates Ollama's model load time on first request
- **Predictable memory**: Fixed GPU allocation, no dynamic shuffling
- **Reduced CPU overhead**: No Ollama daemon overhead

### Observability
- **Prometheus metrics**: Built-in `/metrics` endpoint
- **Slot monitoring**: Track concurrent request status
- **Detailed timing**: Per-token timing information

### Control
- **Direct GGUF access**: No abstraction layer
- **Custom quantization**: Load any GGUF variant
- **LoRA adapters**: Hot-swap LoRA without model reload

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Model download complexity | Medium | Create ModelManager with HF integration |
| Multi-model switching | Medium | Run separate instances per model |
| API compatibility breaks | Low | Thorough adapter layer testing |
| Performance regression | Low | Benchmark before/after migration |
| Service management complexity | Low | Systemd template automation |

---

## Success Criteria

1. All 59 affected files updated and functional
2. Voice pipeline latency <= current Ollama latency
3. No increase in GPU memory usage
4. Dream system code generation working
5. RAG/memory systems functioning
6. All existing tests passing
7. Prometheus metrics accessible

---

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Foundation | 1-2 weeks | ModelManager, LlamaAdapter, systemd templates |
| Integration | 1 week | Updated router, config, factory |
| Migration | 1 week | All systems migrated |
| Cleanup | 0.5 week | Ollama removal, documentation |

**Total estimated time: 3.5-4.5 weeks**

---

## References

- [llama.cpp Server Documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [llama-cpp-python OpenAI Server](https://llama-cpp-python.readthedocs.io/en/latest/server/)
- [llama.cpp GitHub](https://github.com/ggml-org/llama.cpp)
- [Mastering llama.cpp Guide](https://danielkliewer.com/blog/2025-11-12-mastering-llama-cpp-local-llm-integration-guide)

---

*Document created: 2025-11-26*
*Author: Claude (Opus 4.5) during autonomous research session*
