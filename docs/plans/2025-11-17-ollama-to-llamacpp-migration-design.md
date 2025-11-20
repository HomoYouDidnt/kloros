# Ollama to llama.cpp Migration Design

**Date:** 2025-11-17
**Status:** Design Phase - Implementation Deferred
**Dependencies:** ChemBus unification, GPU topology stabilization
**Owner:** KLoROS Architecture Team

---

## 1. Executive Summary

### Why This Migration

**Primary Driver:** Access to llama.cpp's advanced multi-GPU tensor control for heterogeneous GPU configurations (RTX 5080 + RTX 3060 + GTX 1080 Ti), with the 5080 being intermittently available.

**Secondary Benefits:**
- Fix broken failover logic (AltimitOS remote gets stuck, no fallback to local)
- Implement proper task-based routing (code vs reasoning vs RAG models)
- Establish architectural clarity by replacing scattered HTTP calls with ChemBus-native abstraction
- Enable fine-grained VRAM pooling via `gguf-tensor-overrider` tool

### What We're Building

Replace Ollama with llama.cpp as the inference backend, plus 12 supporting microservices to recreate Ollama's convenience features while adding new capabilities:

**Critical Components (5):**
1. Model/Agent Directory Service - Discovery, allocation, release
2. Model Registry & Artifact Manager - GGUF catalog and versioning
3. Runtime/Daemon Supervisor - Keep llama.cpp instances running
4. GPU Topology & Profile Manager - Adaptive GPU configuration
5. Tensor Layout Orchestrator - Integration with gguf-tensor-overrider

**Important Components (4):**
6. Persona/Prompt Template Store - Modelfile replacement
7. OpenAI-Style API Shim - Unified interface
8. Developer UX CLI - `modelctl` tooling

**Enhancement Components (3):**
9. Observability & Telemetry Layer - Metrics and health
10. KV-Cache & Session Manager - Context continuity
11. Security & Policy Gate - Access control

### When This Happens

**Implementation Trigger:** ChemBus unification complete across all KLoROS services

**Current State:** Design-ready, not implementation-ready. This document serves as a time-capsule specification to be validated and executed once the foundation (ChemBus) is solid.

---

## 2. Current State Analysis

### Problem 1: Broken Failover to Remote Ollama

**Issue:** `models_config.py:get_ollama_url()` attempts remote (AltimitOS gaming rig) first, then falls back to local on initial check. However, once a URL is cached (30-second TTL), failures mid-request do not trigger fallback.

**Evidence:**
- `_check_remote_ollama()` has 2-second timeout for initial connectivity check
- Once `_remote_ollama_cache["url"]` is set, downstream code uses it blindly
- `simple_rag.py`, `kloros_voice.py`, `kloros_memory/condenser.py` make direct `requests.post(ollama_url)` calls with no retry/fallback logic

**Impact:**
- KLoROS gets stuck when AltimitOS becomes slow or unavailable mid-request
- No circuit-breaker pattern to detect persistent failures
- User experiences hangs instead of graceful degradation to local inference

### Problem 2: No Task-Based Routing

**Issue:** `select_best_model_for_task()` exists in `models_config.py` but is never called by actual consumers.

**Evidence:**
```python
# models_config.py has this function:
def select_best_model_for_task(task_type: str, ollama_url: str = None) -> str:
    preferences = {
        'code': ['qwen2.5-coder:32b', 'qwen2.5-coder:14b', 'qwen2.5-coder:7b', ...],
        'reasoning': ['deepseek-r1:14b', 'qwen2.5:14b-instruct-q4_0', ...],
        ...
    }

# But actual call sites do:
ollama_url = get_ollama_url()  # Always returns same endpoint
response = requests.post(ollama_url, json={"model": "qwen2.5:7b-instruct", ...})
```

**Impact:**
- Code analysis tasks use generic reasoning models
- Heavy reasoning tasks don't leverage deepseek-r1
- Two Ollama services (ports 11434, 11435) exist but are underutilized

### Problem 3: Scattered Direct API Calls

**Issue:** At least 20+ locations make direct HTTP calls to Ollama with no centralized abstraction.

**Evidence:**
| File | Pattern | Abstraction Level |
|------|---------|-------------------|
| `simple_rag.py` | `requests.post(ollama_url, json=payload)` | None |
| `kloros_voice.py` | `requests.post(self.ollama_url, json={...})` | None |
| `kloros_memory/condenser.py` | `requests.post(self.ollama_url, json=payload)` | None |
| `tumix/judge.py` | `requests.post(self.ollama_url, json={...})` | Partial (uses `get_ollama_url()`) |

**Impact:**
- Cannot fix failover/routing in one place
- Difficult to instrument, monitor, or change backends
- Inconsistent error handling across call sites

### Current Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    KLoROS Components                            │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │ simple_rag  │  │ kloros_voice │  │ kloros_memory/      │   │
│  │             │  │              │  │ condenser           │   │
│  └──────┬──────┘  └──────┬───────┘  └──────┬──────────────┘   │
│         │                │                   │                  │
│         └────────────────┴───────────────────┘                  │
│                          │                                      │
│                   Direct HTTP calls                             │
│                  (no abstraction)                               │
└──────────────────────────┼──────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │   models_config.py (partial routing)     │
        │   - get_ollama_url()                     │
        │   - _check_remote_ollama() [30s cache]   │
        │   - select_best_model_for_task() [unused]│
        └──────────────┬───────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
  ┌─────────────┐           ┌─────────────────┐
  │  AltimitOS  │           │  Local Ollama   │
  │  (Remote)   │           │  (2 services)   │
  │  :11434     │           │  :11434, :11435 │
  └─────────────┘           └─────────────────┘
      ↓ (stuck)                   ↓ (fallback broken)
   RTX 4090                    RTX 3060 + 1080 Ti
```

**Pain Points Highlighted:**
1. No circuit breaker when AltimitOS fails mid-request
2. Task routing logic exists but unused
3. Scattered call sites prevent centralized fixes
4. GPU resources underutilized (no multi-GPU pooling)

---

## 3. Design Drivers & Requirements

### Functional Requirements

**FR-1: Multi-GPU Tensor Pooling**
- Support RTX 5080 (24GB) + RTX 3060 (12GB) + GTX 1080 Ti (11GB) as unified VRAM pool
- Use `gguf-tensor-overrider` to automate tensor → device assignment
- Priority: Attention tensors → FFN → Gate → Norm → Experts

**FR-2: Adaptive GPU Profiles**
- Detect when 5080 is unavailable (gaming, passed to VM, etc.)
- Automatically select appropriate profile:
  - **max**: 5080 + 3060 + 1080 Ti (biggest models, best quant)
  - **mid**: 3060 + 1080 Ti (medium models, tighter context)
  - **fallback**: 3060 only (small models, safety)
- Transition between profiles without manual intervention

**FR-3: Task-Based Model Selection**
- Route requests to appropriate specialist models:
  - `code_understanding` → qwen2.5-coder:7b or deepseek-coder
  - `reasoning` → deepseek-r1:7b or qwen2.5:14b-instruct
  - `fast` → qwen2.5:7b-instruct
  - `deep` → qwen2.5-coder:32b (if available on max profile)
- Expose capabilities via Model Directory Service

**FR-4: Robust Failover with Circuit Breaker**
- Detect remote endpoint failures within 2 seconds
- Implement circuit breaker states: closed, open, half-open
- Fall back to local endpoint on persistent failures
- TTS announcements for state changes (already exists in models_config.py)

**FR-5: ChemBus-Native Integration**
- All LLM requests published to `llm.request` topic
- Responses delivered via `llm.response.{request_id}` topic
- Health monitoring via `llm.health` topic
- Backward compatibility for non-ChemBus services during transition

### Non-Functional Requirements

**NFR-1: Zero Downtime Migration**
- Parallel run: llama.cpp alongside Ollama during validation
- Incremental cutover by service/workload
- Instant rollback capability

**NFR-2: Observability**
- Per-model metrics: TTFT, tokens/sec, context utilization, GPU memory
- Request tracing: task type → model selection → GPU profile → latency
- Health dashboards for proactive intervention

**NFR-3: Developer Experience**
- CLI tooling (`modelctl`) on par with `ollama` commands
- Clear logs and error messages
- Self-documenting model registry

**NFR-4: Security**
- Access control around model endpoints (ChemBus topics)
- Data classification policies (which models handle which data)
- Audit trail for model usage

### Technical Constraints

**TC-1: NVIDIA-Only GPU Support**
- `gguf-tensor-overrider` currently supports NVIDIA GPUs only
- All three GPUs (5080, 3060, 1080 Ti) are NVIDIA → compatible

**TC-2: GGUF Model Format**
- All models must be in GGUF format (from Hugging Face or converted)
- Existing Ollama models are already GGUF-based → portable

**TC-3: llama.cpp Architecture Support**
- Not all architectures supported equally by llama.cpp
- Current models (Qwen, DeepSeek, Llama) are well-supported

**TC-4: ChemBus as Prerequisite**
- Design assumes ChemBus unification complete
- Services not yet on ChemBus require interim shim (HTTP → ChemBus bridge)

---

## 4. Target Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      KLoROS Components                              │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ Reasoning  │  │ Code Agent  │  │ RAG System   │  │ Voice I/O │ │
│  └─────┬──────┘  └──────┬──────┘  └──────┬───────┘  └─────┬─────┘ │
│        │                │                 │                 │       │
│        └────────────────┴─────────────────┴─────────────────┘       │
│                                 │                                   │
│                          ChemBus Publish                            │
│                     Topic: llm.request                              │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                              ▼
        ┌──────────────────────────────────────────────────────┐
        │     Model Directory Service (ChemBus Subscriber)     │
        │  - Subscribe to: llm.request                         │
        │  - Allocate specialist model by purpose              │
        │  - Check GPU profile (max/mid/fallback)              │
        │  - Route to appropriate llama.cpp runtime            │
        │  - Publish response to: llm.response.{request_id}    │
        └──────────────┬───────────────────────────────────────┘
                       │
         ┌─────────────┴──────────────────┐
         │                                │
         ▼                                ▼
  ┌─────────────────┐          ┌──────────────────┐
  │ GPU Profile Mgr │          │ Model Registry   │
  │ - Detect GPUs   │          │ - GGUF catalog   │
  │ - Choose profile│          │ - Versions       │
  │ - Update state  │          │ - Capabilities   │
  └─────────────────┘          └──────────────────┘
         │                                │
         ▼                                ▼
  ┌────────────────────────────────────────────────┐
  │    Runtime Supervisor (systemd services)       │
  │  ┌──────────────┐  ┌──────────────────────┐   │
  │  │ llama-code@  │  │ llama-reasoning@     │   │
  │  │ max.service  │  │ mid.service          │   │
  │  │ Port: 8601   │  │ Port: 8602           │   │
  │  └──────┬───────┘  └──────┬───────────────┘   │
  │         │                  │                    │
  └─────────┼──────────────────┼────────────────────┘
            │                  │
            ▼                  ▼
    ┌───────────────┐  ┌────────────────┐
    │ Tensor Layout │  │ Tensor Layout  │
    │ Orchestrator  │  │ Orchestrator   │
    │ (max profile) │  │ (mid profile)  │
    └───────┬───────┘  └────────┬───────┘
            │                   │
            ▼                   ▼
  ┌──────────────────┐  ┌──────────────┐
  │ llama-server     │  │ llama-server │
  │ --tensor-split   │  │ --tensor-    │
  │ 80,15,5 (%)      │  │ split 70,30  │
  └────────┬─────────┘  └──────┬───────┘
           │                    │
           ▼                    ▼
  ┌──────────────────┐  ┌──────────────┐
  │ 5080+3060+1080Ti │  │ 3060+1080Ti  │
  │ (47GB total)     │  │ (23GB total) │
  └──────────────────┘  └──────────────┘
```

### Request Flow

**Step-by-step for a code understanding request:**

1. **KLoROS Code Agent** needs to analyze Python code
2. **Publishes to ChemBus:**
   ```json
   {
     "topic": "llm.request",
     "request_id": "req_01HXYZ123",
     "purpose": "code_understanding",
     "prompt": "Explain this function: ...",
     "constraints": {
       "min_context_tokens": 16000,
       "max_latency_ms": 5000,
       "cost_tier": "medium"
     }
   }
   ```

3. **Model Directory Service** receives request:
   - Queries GPU Profile Manager → returns "max" (5080 available)
   - Queries Model Registry → matches purpose="code_understanding"
   - Finds candidates: `qwen2.5-coder:7b`, `deepseek-coder:33b`
   - Selects `qwen2.5-coder:7b` (best fit for max profile + constraints)
   - Checks if runtime is running on port 8601 → yes, healthy

4. **Makes OpenAI-compatible call:**
   ```http
   POST http://localhost:8601/v1/chat/completions
   {
     "model": "qwen2.5-coder:7b",
     "messages": [...],
     "max_tokens": 2048
   }
   ```

5. **llama-server** (port 8601) processes request:
   - Uses cached tensor overrides for max profile (5080+3060+1080Ti)
   - Attention tensors on 5080, FFN on 3060, rest on 1080 Ti
   - Streams response back

6. **Directory Service** publishes response:
   ```json
   {
     "topic": "llm.response.req_01HXYZ123",
     "success": true,
     "response": "This function implements...",
     "metadata": {
       "model_id": "qwen2.5-coder:7b",
       "profile": "max",
       "ttft_ms": 234,
       "tokens_per_sec": 45.2
     }
   }
   ```

7. **Code Agent** receives response via ChemBus subscription

### ChemBus Topics

| Topic | Publisher | Subscriber | Purpose |
|-------|-----------|------------|---------|
| `llm.request` | All KLoROS services | Model Directory | Request specialist model |
| `llm.response.{id}` | Model Directory | Requesting service | Deliver LLM response |
| `llm.health` | Model Directory | Monitoring services | Runtime health status |
| `llm.allocation` | Model Directory | Observability | Allocation/release events |
| `llm.gpu_profile` | GPU Profile Manager | Model Directory | GPU topology changes |

---

## 5. Component Designs

### 5.1 Model/Agent Directory Service (Critical)

**Responsibility:** Central discovery, allocation, and release of specialist models based on task purpose.

**Interfaces:**

ChemBus Subscriptions:
- `llm.request` → allocate model for task

ChemBus Publications:
- `llm.response.{request_id}` → deliver LLM response
- `llm.health` → periodic health updates
- `llm.allocation` → allocation/release events

Internal Dependencies:
- GPU Profile Manager (get current profile)
- Model Registry (get available models + capabilities)
- Runtime Supervisor (check if model is running, start if needed)

**Data Structures:**

Model Definition:
```python
{
  "id": "qwen2.5-coder-7b-q4_0",
  "display_name": "Qwen 2.5 Coder 7B Q4_0",
  "backend": "llama_cpp",
  "purpose_tags": ["code_understanding", "code_generation"],
  "context_tokens": 32000,
  "cost_tier": "medium",  # compute cost: low/medium/high
  "profiles": {
    "max": {
      "port": 8601,
      "gpu_percentages": [80, 15, 5],  # 5080, 3060, 1080Ti
      "endpoint": "http://localhost:8601/v1/chat/completions"
    },
    "mid": {
      "port": 8602,
      "gpu_percentages": [70, 30],  # 3060, 1080Ti
      "endpoint": "http://localhost:8602/v1/chat/completions"
    },
    "fallback": null  # too big for single 3060
  }
}
```

Allocation Record:
```python
{
  "allocation_id": "alloc_01HXYZ123",
  "request_id": "req_01HXYZ123",
  "model_id": "qwen2.5-coder-7b-q4_0",
  "profile": "max",
  "endpoint": "http://localhost:8601/v1/chat/completions",
  "created_at": "2025-11-17T18:05:00Z",
  "ttl": 600  # seconds
}
```

**Selection Algorithm:**

```python
def select_model(purpose: str, constraints: dict, current_profile: str):
    # 1. Filter by purpose
    candidates = [m for m in registry if purpose in m.purpose_tags]

    # 2. Filter by profile availability
    candidates = [m for m in candidates if current_profile in m.profiles]

    # 3. Filter by constraints
    if "min_context_tokens" in constraints:
        candidates = [m for m in candidates
                      if m.context_tokens >= constraints["min_context_tokens"]]

    if "cost_tier" in constraints:
        tier_map = {"low": 1, "medium": 2, "high": 3}
        max_cost = tier_map[constraints["cost_tier"]]
        candidates = [m for m in candidates
                      if tier_map[m.cost_tier] <= max_cost]

    # 4. Score remaining candidates
    # Prefer: lower cost tier, higher context, specialist over generalist
    def score(model):
        s = 0
        s += 10 if purpose == model.purpose_tags[0] else 5  # specialist bonus
        s += model.context_tokens / 10000  # higher context preferred
        s -= tier_map[model.cost_tier] * 2  # lower cost preferred
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0] if candidates else None
```

**Lifecycle Management:**

- Allocations have TTL (default 600s = 10 minutes)
- Background janitor runs every 60s:
  - Finds expired allocations with no recent activity
  - Marks models as idle
  - After 5 minutes idle → calls Runtime Supervisor to stop model
  - Frees VRAM for other workloads

**Failover Logic:**

```python
def call_model(allocation, prompt, max_retries=2):
    endpoint = allocation.endpoint

    for attempt in range(max_retries):
        try:
            response = requests.post(
                endpoint,
                json={"model": allocation.model_id, "prompt": prompt},
                timeout=allocation.max_latency_ms / 1000
            )
            if response.status_code == 200:
                return response.json()
        except (RequestException, Timeout) as e:
            log_error(f"Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))  # exponential backoff

    # All retries failed
    mark_model_unhealthy(allocation.model_id, allocation.profile)
    return {"error": "Model unavailable after retries"}
```

---

### 5.2 Model Registry & Artifact Manager (Critical)

**Responsibility:** Maintain catalog of available models, handle GGUF download/versioning, support rollbacks.

**Storage:** `/var/lib/llama-models/` with structure:
```
/var/lib/llama-models/
├── registry.yaml          # Master catalog
├── qwen2.5-coder-7b/
│   ├── 2025-11-17-01/
│   │   ├── model.gguf
│   │   ├── metadata.json
│   │   └── sha256sum
│   └── 2025-12-01-01/    # Newer version
│       ├── model.gguf
│       └── ...
└── deepseek-r1-7b/
    └── 2025-11-10-01/
        └── model.gguf
```

**registry.yaml Format:**

```yaml
models:
  - id: qwen2.5-coder-7b-q4_0
    display_name: "Qwen 2.5 Coder 7B Q4_0"
    purpose_tags:
      - code_understanding
      - code_generation
    languages:
      - python
      - typescript
      - rust
    context_tokens: 32000
    cost_tier: medium

    current_version: "2025-11-17-01"
    versions:
      - version_id: "2025-11-17-01"
        gguf_url: "hf://Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/qwen2.5-coder-7b-instruct-q4_0.gguf"
        local_path: "/var/lib/llama-models/qwen2.5-coder-7b/2025-11-17-01/model.gguf"
        sha256: "a1b2c3d4..."
        created_at: "2025-11-17T10:00:00Z"
        notes: "Initial deployment"

      - version_id: "2025-12-01-01"
        gguf_url: "hf://Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/qwen2.5-coder-7b-instruct-q6_k.gguf"
        local_path: "/var/lib/llama-models/qwen2.5-coder-7b/2025-12-01-01/model.gguf"
        sha256: "e5f6g7h8..."
        created_at: "2025-12-01T14:30:00Z"
        notes: "Q6_K for better quality on max profile"

    profiles:
      max:
        port: 8601
        gpu_percentages: [80, 15, 5]
      mid:
        port: 8602
        gpu_percentages: [70, 30]
      fallback: null
```

**CLI Commands (`modelctl`):**

```bash
# List models
modelctl list
# Output:
# ID                        VERSION         SIZE    PROFILE    STATUS
# qwen2.5-coder-7b-q4_0    2025-11-17-01   4.7GB   max        running
# deepseek-r1-7b           2025-11-10-01   4.7GB   mid        stopped

# Pull new model
modelctl pull qwen2.5-coder:32b --quant q4_0
# Downloads GGUF from Hugging Face, verifies checksum, adds to registry

# Promote to new version
modelctl promote qwen2.5-coder-7b-q4_0 --to 2025-12-01-01
# Updates current_version in registry.yaml
# Triggers Runtime Supervisor restart for affected services

# Rollback to previous version
modelctl rollback qwen2.5-coder-7b-q4_0 --to 2025-11-17-01

# Show detailed info
modelctl show qwen2.5-coder-7b-q4_0
# Displays: versions, capabilities, current profile, memory usage, etc.

# Garbage collect old versions
modelctl gc --keep 2
# Keeps only the 2 most recent versions per model, deletes rest
```

**Download Logic:**

```python
def pull_model(model_name: str, quant: str = "q4_0"):
    # 1. Resolve Hugging Face URL
    hf_url = f"hf://Qwen/{model_name}-GGUF/{model_name}-{quant}.gguf"

    # 2. Generate version ID
    version_id = datetime.now().strftime("%Y-%m-%d-%H")

    # 3. Download with progress bar
    local_path = f"/var/lib/llama-models/{model_name}/{version_id}/model.gguf"
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    download_file(hf_url, local_path)

    # 4. Verify checksum (from HuggingFace metadata)
    expected_sha256 = get_hf_checksum(hf_url)
    actual_sha256 = compute_sha256(local_path)

    if expected_sha256 != actual_sha256:
        raise ValueError(f"Checksum mismatch: {actual_sha256} != {expected_sha256}")

    # 5. Add to registry
    add_version_to_registry(model_name, version_id, hf_url, local_path, actual_sha256)

    print(f"✓ Model {model_name} version {version_id} pulled successfully")
```

---

### 5.3 Runtime/Daemon Supervisor (Critical)

**Responsibility:** Start/stop llama-server instances via systemd, enforce health checks, auto-restart on crash.

**systemd Service Template:**

File: `/etc/systemd/system/llama@.service`

```ini
[Unit]
Description=llama.cpp Server - %i
After=network-online.target kloros-chem-proxy.service
Wants=network-online.target
Requires=kloros-chem-proxy.service

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/opt/llama.cpp

# Environment from /etc/llama/profiles/%i.env
EnvironmentFile=/etc/llama/profiles/%i.env

ExecStart=/opt/llama.cpp/llama-server \
  -m ${MODEL_PATH} \
  -c ${CONTEXT} \
  --port ${PORT} \
  ${TENSOR_OVERRIDES}

Restart=always
RestartSec=5

# Resource limits
LimitNOFILE=65535
MemoryMax=16G

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

**Profile Environment Files:**

File: `/etc/llama/profiles/code-max.env`

```bash
MODEL_PATH=/var/lib/llama-models/qwen2.5-coder-7b/2025-11-17-01/model.gguf
CONTEXT=32000
PORT=8601
TENSOR_OVERRIDES=-ot "blk.0.attn_q.weight=cuda:0" -ot "blk.0.attn_k.weight=cuda:0" ...
# (Generated by Tensor Layout Orchestrator)
```

File: `/etc/llama/profiles/reasoning-mid.env`

```bash
MODEL_PATH=/var/lib/llama-models/deepseek-r1-7b/2025-11-10-01/model.gguf
CONTEXT=24000
PORT=8602
TENSOR_OVERRIDES=-ot "blk.0.attn_q.weight=cuda:0" -ot "blk.1.ffn_gate.weight=cuda:1" ...
```

**Runtime Control API:**

Exposed via ChemBus topics or simple HTTP API (for `modelctl` CLI):

```python
# Start a runtime
POST /runtimes/start
{
  "profile": "code-max",
  "model_id": "qwen2.5-coder-7b-q4_0"
}
# Calls: systemctl start llama@code-max.service

# Stop a runtime
POST /runtimes/stop
{
  "profile": "code-max"
}
# Calls: systemctl stop llama@code-max.service

# Health check
GET /runtimes/health
{
  "runtimes": [
    {
      "profile": "code-max",
      "status": "running",
      "pid": 12345,
      "port": 8601,
      "uptime_seconds": 3600,
      "last_request_at": "2025-11-17T18:30:00Z"
    }
  ]
}
```

**Health Monitoring:**

- Every 30 seconds, ping each running llama-server:
  ```http
  GET http://localhost:8601/health
  ```
- Expected response: `{"status": "ok"}`
- If 3 consecutive failures → mark unhealthy, publish to `llm.health` topic
- Model Directory Service removes from available pool

---

### 5.4 GPU Topology & Profile Manager (Critical)

**Responsibility:** Detect available GPUs, choose appropriate profile (max/mid/fallback), handle transitions when 5080 appears/disappears.

**Detection Logic:**

```python
import pynvml

def detect_gpus() -> List[Dict]:
    pynvml.nvmlInit()
    device_count = pynvml.nvmlDeviceGetCount()

    gpus = []
    for i in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle).decode()
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)

        gpus.append({
            "index": i,
            "name": name,
            "vram_total_gb": mem_info.total / (1024**3),
            "vram_free_gb": mem_info.free / (1024**3),
            "utilization_percent": util.gpu,
            "eligible": util.gpu < 50 and mem_info.free > 2 * (1024**3)  # <50% util, >2GB free
        })

    pynvml.nvmlShutdown()
    return gpus
```

**Profile Selection:**

```python
def select_profile(gpus: List[Dict]) -> str:
    eligible = [g for g in gpus if g["eligible"]]

    # Check for 5080
    has_5080 = any("5080" in g["name"] for g in eligible)
    has_3060 = any("3060" in g["name"] for g in eligible)
    has_1080ti = any("1080" in g["name"] for g in eligible)

    if has_5080 and has_3060 and has_1080ti:
        return "max"
    elif has_3060 and has_1080ti:
        return "mid"
    elif has_3060:
        return "fallback"
    else:
        return "cpu_only"  # Last resort
```

**Transition Handling:**

```python
def monitor_gpu_topology():
    previous_profile = None

    while True:
        gpus = detect_gpus()
        current_profile = select_profile(gpus)

        if current_profile != previous_profile:
            log_info(f"GPU profile changed: {previous_profile} → {current_profile}")

            # Publish to ChemBus
            chembus.publish("llm.gpu_profile", {
                "profile": current_profile,
                "gpus": gpus,
                "timestamp": datetime.now().isoformat()
            })

            # Update state file for Runtime Supervisor
            with open("/run/kloros_gpu_profile", "w") as f:
                f.write(current_profile)

            # Optionally restart affected runtimes
            # (Or let them restart on next allocation)

            previous_profile = current_profile

        time.sleep(10)  # Check every 10 seconds
```

**Manual Override:**

File: `/etc/kloros/gpu_lockout`

```json
{
  "lockout_gpus": ["0"],  // GPU index 0 (5080) locked out
  "reason": "Gaming session",
  "until": "2025-11-17T22:00:00Z"  // Unlock at 10 PM
}
```

If this file exists, GPU Profile Manager excludes locked GPUs from detection.

---

### 5.5 Tensor Layout Orchestrator (Critical)

**Responsibility:** Integrate `gguf-tensor-overrider` to generate optimal tensor placement for each model/profile combination.

**Workflow:**

```python
def generate_tensor_overrides(
    model_id: str,
    gguf_url: str,
    context: int,
    profile: str,
    gpu_percentages: List[int]
) -> str:
    # 1. Check cache
    cache_key = hashlib.sha256(
        f"{model_id}-{context}-{profile}-{gpu_percentages}".encode()
    ).hexdigest()

    cache_path = f"/var/cache/llama-tensor-overrides/{cache_key}.txt"

    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return f.read()

    # 2. Run gguf-tensor-overrider
    cmd = [
        "gguf-tensor-overrider",
        "-g", gguf_url,
        "-c", str(context),
        "--granular-gpu-percentage", ",".join(map(str, gpu_percentages)),
        "--check",  # Verify it fits
        "--verbose"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        raise RuntimeError(f"Tensor override generation failed: {result.stderr}")

    overrides = result.stdout.strip()

    # 3. Cache for future use
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        f.write(overrides)

    return overrides
```

**Integration with Runtime Supervisor:**

When starting a llama-server instance:

```bash
# Runtime Supervisor generates profile env file dynamically
MODEL_PATH=/var/lib/llama-models/qwen2.5-coder-7b/2025-11-17-01/model.gguf
CONTEXT=32000
PORT=8601

# Call Tensor Layout Orchestrator
TENSOR_OVERRIDES=$(python3 -c "
from kloros.llm.tensor_orchestrator import generate_tensor_overrides
print(generate_tensor_overrides(
    model_id='qwen2.5-coder-7b-q4_0',
    gguf_url='hf://Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/qwen2.5-coder-7b-instruct-q4_0.gguf',
    context=32000,
    profile='max',
    gpu_percentages=[80, 15, 5]
))
")

# Write to profile env file
echo "TENSOR_OVERRIDES=\"$TENSOR_OVERRIDES\"" >> /etc/llama/profiles/code-max.env

# Start service
systemctl start llama@code-max.service
```

**Example Generated Overrides:**

```bash
-ot "blk.0.attn_q.weight=cuda:0" \
-ot "blk.0.attn_k.weight=cuda:0" \
-ot "blk.0.attn_v.weight=cuda:0" \
-ot "blk.0.attn_output.weight=cuda:0" \
-ot "blk.1.ffn_gate.weight=cuda:1" \
-ot "blk.1.ffn_up.weight=cuda:1" \
-ot "blk.1.ffn_down.weight=cuda:1" \
-ot "blk.2.attn_norm.weight=cuda:2" \
...
```

Assigns:
- Attention tensors (critical, needs fast memory) → cuda:0 (5080, 80%)
- FFN tensors → cuda:1 (3060, 15%)
- Norm/other → cuda:2 (1080 Ti, 5%)

---

## 6. Important Components (Brief Overview)

### 6.1 Persona/Prompt Template Store

**Purpose:** Replace Ollama's Modelfile concept with YAML-based persona definitions.

**Format:**

```yaml
personas:
  - id: kairos-code-doctor
    base_model: qwen2.5-coder-7b-q4_0
    system_prompt: |
      You are a code analysis expert. Provide clear explanations, identify bugs,
      and suggest refactorings. Always cite line numbers when referencing code.
    chat_template: chatml  # Format: <|im_start|>system\n...
    sampling:
      temperature: 0.2
      top_p: 0.9
      repeat_penalty: 1.1
```

Model Directory Service loads personas and applies system prompt + sampling params when allocating.

---

### 6.2 OpenAI-Style API Shim

**Purpose:** Normalize llama-server's OpenAI-compatible API and add missing features (e.g., tool calling).

**Features:**
- Translate between different chat formats (ChatML, Llama3, etc.)
- Add tool/function calling shim for models that don't natively support it
- Consistent error codes and retry behavior

---

### 6.3 Developer UX CLI (`modelctl`)

**Purpose:** Provide `ollama`-like CLI for model management.

**Commands:**
- `modelctl list` - Show all models
- `modelctl pull <model>` - Download GGUF
- `modelctl promote/rollback` - Version management
- `modelctl status` - Show running runtimes
- `modelctl logs <profile>` - View llama-server logs

---

### 6.4 Embedding & RAG Profile Manager

**Purpose:** Manage dedicated embedding model endpoints for RAG workloads.

**Design:**
- Separate llama-server instances for embedding models (e.g., nomic-embed-text)
- Expose via `/v1/embeddings` endpoint
- Model Directory Service routes embedding requests separately from generation

---

## 7. ChemBus Integration Points

### Message Schemas

**llm.request:**
```json
{
  "request_id": "req_01HXYZ123",
  "purpose": "code_understanding",
  "prompt": "Explain this function...",
  "constraints": {
    "min_context_tokens": 16000,
    "max_latency_ms": 5000,
    "cost_tier": "medium"
  },
  "metadata": {
    "source_service": "kloros-code-agent",
    "user_id": "kloros",
    "session_id": "sess_abc123"
  }
}
```

**llm.response.{request_id}:**
```json
{
  "request_id": "req_01HXYZ123",
  "success": true,
  "response": "This function implements a binary search...",
  "metadata": {
    "model_id": "qwen2.5-coder-7b-q4_0",
    "profile": "max",
    "allocation_id": "alloc_01HXYZ123",
    "ttft_ms": 234,
    "tokens_per_sec": 45.2,
    "total_tokens": 512
  }
}
```

**llm.health:**
```json
{
  "timestamp": "2025-11-17T18:30:00Z",
  "runtimes": [
    {
      "profile": "code-max",
      "status": "healthy",
      "model_id": "qwen2.5-coder-7b-q4_0",
      "port": 8601,
      "uptime_seconds": 3600,
      "active_requests": 2
    }
  ],
  "gpu_profile": "max"
}
```

**llm.gpu_profile:**
```json
{
  "profile": "max",
  "gpus": [
    {"index": 0, "name": "RTX 5080", "vram_free_gb": 18.2, "eligible": true},
    {"index": 1, "name": "RTX 3060", "vram_free_gb": 9.1, "eligible": true},
    {"index": 2, "name": "GTX 1080 Ti", "vram_free_gb": 8.5, "eligible": true}
  ],
  "timestamp": "2025-11-17T18:30:00Z"
}
```

### Backward Compatibility During Transition

For services not yet on ChemBus:

**Option 1: HTTP→ChemBus Bridge Service**

Expose HTTP endpoint that internally publishes to ChemBus:

```python
# http_bridge.py
@app.post("/v1/chat/completions")
def chat_completions(request: ChatRequest):
    request_id = generate_id()

    # Publish to ChemBus
    chembus.publish("llm.request", {
        "request_id": request_id,
        "purpose": infer_purpose(request),  # heuristic
        "prompt": request.messages,
        ...
    })

    # Wait for response
    response = chembus.wait_for(f"llm.response.{request_id}", timeout=30)

    return {
        "id": request_id,
        "choices": [{"message": {"content": response["response"]}}],
        ...
    }
```

Run on port 11434 (fake Ollama) so legacy code works unchanged.

---

## 8. GPU Profile Management

### Profile Definitions

| Profile | GPUs | Total VRAM | Use Case | Example Models |
|---------|------|------------|----------|----------------|
| **max** | 5080 + 3060 + 1080 Ti | ~47GB | Largest models, best quant, long context | qwen2.5-coder:32b Q5, deepseek-r1:14b |
| **mid** | 3060 + 1080 Ti | ~23GB | Medium models, moderate context | qwen2.5-coder:7b Q4, deepseek-r1:7b |
| **fallback** | 3060 only | ~12GB | Small models, safety | qwen2.5:7b Q4 |
| **cpu_only** | CPU | System RAM | Emergency mode | qwen2.5:7b Q2 |

### Detection Logic

```python
def select_profile(gpus: List[GPU]) -> str:
    # Filter eligible GPUs (<50% util, >2GB free)
    eligible = [g for g in gpus if g.utilization < 50 and g.vram_free_gb > 2]

    gpu_names = [g.name for g in eligible]

    if "5080" in gpu_names and "3060" in gpu_names and "1080" in gpu_names:
        return "max"
    elif "3060" in gpu_names and "1080" in gpu_names:
        return "mid"
    elif "3060" in gpu_names:
        return "fallback"
    else:
        return "cpu_only"
```

### Failover Sequence

**Scenario:** User starts gaming on 5080, GPU becomes ineligible.

1. GPU Profile Manager detects: 5080 utilization jumps to 95%
2. Marks 5080 as ineligible → profile changes `max` → `mid`
3. Publishes to `llm.gpu_profile` topic
4. Model Directory Service receives update:
   - New requests route to `mid` profile models
   - Running `max` profile runtimes continue until idle
5. After 5 minutes idle → Runtime Supervisor stops `max` runtimes
6. User stops gaming → 5080 becomes eligible again
7. Profile changes `mid` → `max`
8. Next code request allocates `max` profile model

**User Experience:** Transparent. Requests slower during gaming but no failures.

---

## 9. Implementation Sequence

### Phase 1: Sandbox (Critical 5 Components)

**Goal:** Prove the architecture works end-to-end with one model in isolation.

**Steps:**
1. Install llama.cpp, gguf-tensor-overrider
2. Implement Model Registry (YAML-based, single model)
3. Implement Tensor Layout Orchestrator (wrapper around gguf-tensor-overrider)
4. Create systemd service template (`llama@.service`)
5. Implement GPU Profile Manager (detection only, no transitions yet)
6. Implement Model Directory Service (minimal, ChemBus-native)
7. Test end-to-end: ChemBus request → allocation → llama.cpp → response

**Success Criteria:**
- ✓ Single model (`qwen2.5-coder:7b`) runs on `max` profile
- ✓ Tensor overrides generated correctly (5080+3060+1080Ti split)
- ✓ ChemBus request/response flow works
- ✓ GPU profile detection accurate

**Timeline:** 1-2 weeks (focused dev time)

---

### Phase 2: Parallel Run

**Goal:** Run llama.cpp alongside Ollama in production, route specific workloads (e.g., code tasks).

**Steps:**
1. Add models to registry: reasoning, fast, deep
2. Implement profile transitions (max→mid→fallback)
3. Add observability (metrics, health checks)
4. Route code tasks to llama.cpp, everything else to Ollama
5. Monitor for 1 week, compare quality/performance

**Success Criteria:**
- ✓ Code tasks use llama.cpp, others use Ollama
- ✓ No regressions in code task quality
- ✓ Multi-GPU utilization visible in metrics
- ✓ Profile transitions work (manual test: start gaming)

**Timeline:** 2 weeks

---

### Phase 3: Incremental Cutover

**Goal:** Migrate all workloads from Ollama to llama.cpp.

**Steps:**
1. Implement HTTP→ChemBus bridge for legacy services
2. Migrate workloads one by one:
   - Week 1: Code tasks (already done)
   - Week 2: RAG tasks
   - Week 3: Reasoning tasks
   - Week 4: Voice I/O (kloros_voice.py)
3. Monitor each migration for 3 days before next
4. Stop Ollama services once all traffic migrated

**Success Criteria:**
- ✓ All KLoROS services using llama.cpp
- ✓ Ollama services stopped
- ✓ No user-visible regressions

**Timeline:** 4-6 weeks

---

### Phase 4: Enhancements

**Goal:** Add nice-to-have features.

**Steps:**
1. Implement KV-Cache session manager
2. Add security/policy layer
3. Build dashboard UI (optional)
4. Optimize tensor layouts based on real usage

**Timeline:** Ongoing

---

## 10. Validation & Testing Strategy

### Sandbox Verification Checklist

Before Phase 2:
- [ ] llama.cpp compiles and runs
- [ ] gguf-tensor-overrider generates valid overrides
- [ ] Single model loads across 3 GPUs (verify with nvidia-smi)
- [ ] ChemBus request/response roundtrip <2s
- [ ] GPU profile detection detects all 3 GPUs
- [ ] systemd service auto-restarts on crash

### Production Readiness Checklist

Before Phase 3:
- [ ] 3+ models in registry with different profiles
- [ ] Profile transitions tested (manual GPU lockout)
- [ ] Metrics visible in dashboard
- [ ] Error rate <1% over 1 week
- [ ] Latency p95 within 20% of Ollama baseline
- [ ] No memory leaks (monitor for 7 days)

### Rollback Procedures

**Phase 2 Rollback:**
- Change Model Directory Service to route all tasks to Ollama
- Stop llama.cpp runtimes
- No code changes required (ChemBus abstraction preserved)

**Phase 3 Rollback:**
- Re-enable Ollama services
- Point HTTP bridge to Ollama instead of llama.cpp
- Restart affected KLoROS services

**Phase 4 Rollback:**
- Enhancements are additive, no rollback needed

---

## 11. Migration Decision Tree

### When to Proceed with Implementation

**Prerequisite Checks:**

1. **ChemBus Unification:**
   - [ ] All critical services on ChemBus (consciousness, orchestration, reasoning)
   - [ ] ChemBus proxy stable (no crashes in 1 week)
   - [ ] Message throughput adequate (<100ms p95 latency)

2. **GPU Topology Stability:**
   - [ ] All 3 GPUs visible and healthy
   - [ ] NVIDIA drivers up to date
   - [ ] No thermal throttling under load

3. **Resource Availability:**
   - [ ] 2-4 weeks of focused dev time
   - [ ] Test environment available (don't break prod)

**Go/No-Go Decision:**

- **GO** if all prerequisite checks pass
- **NO-GO** if:
  - ChemBus still has instability
  - GPU hardware issues
  - Critical KLoROS services under active development

### Pre-Flight Checks (Day of Implementation)

Before starting Phase 1:
- [ ] Backup current Ollama models: `cp -r /var/lib/ollama/models /backup/`
- [ ] Document current Ollama port allocations
- [ ] Take system snapshot (if VM)
- [ ] Notify user: "Starting llama.cpp sandbox, Ollama stays active"

---

## 12. Appendices

### Appendix A: External Dependencies

**Required Software:**
- llama.cpp (build from source or release binary)
- gguf-tensor-overrider (https://github.com/k-koehler/gguf-tensor-overrider)
- Python 3.10+ with pynvml, pyyaml, requests
- systemd (already present)

**Disk Space:**
- Models: ~50GB for full catalog (4-5 models at Q4/Q5)
- Cache: ~5GB for tensor overrides
- Total: 60GB recommended

### Appendix B: Glossary

- **GGUF:** Model format used by llama.cpp (replaces GGML)
- **Tensor Override:** Manually specifying which GPU hosts which tensor
- **ChemBus:** KLoROS ZeroMQ pub/sub message bus
- **Profile:** GPU configuration (max, mid, fallback)
- **Allocation:** Temporary assignment of model to task

### Appendix C: References

- llama.cpp: https://github.com/ggerganov/llama.cpp
- gguf-tensor-overrider: https://github.com/k-koehler/gguf-tensor-overrider
- ChatGPT conversation (referenced): https://chatgpt.com/share/691b6672-6bc0-800a-b408-87a02896e08f
- KLoROS ChemBus migration: /home/kloros/docs/CHEM_PROXY_MIGRATION.md

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2025-11-17 | Claude + User | Initial design based on brainstorming session |

---

**END OF DOCUMENT**
