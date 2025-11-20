# SPICA Advanced Features (Phase 4) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement advanced SPICA capabilities: C2C Level 3 (GPU KV cache sharing), prompt_graph evolutionary mutations, and multi-host coordination.

**Architecture:** Research-heavy implementation requiring llama.cpp integration, graph-based prompt representation, and distributed systems coordination. These are exploratory features with uncertain timelines.

**Tech Stack:** Python 3.11+, llama.cpp C++ bindings, NetworkX (graphs), etcd/Consul (distributed coordination), CUDA (GPU), pytest

**Prerequisites:**
- Phase 0-3 complete (✅ tournament mode, ResourceGovernor, observability, persistent services)
- llama.cpp built with CUDA support
- Multi-GPU or multi-host environment available

**Timeline Estimate:** 6-12 months (research + implementation)

**Status:** 🔮 Planned (design complete, awaiting research validation)

---

## Research Phase (6-8 weeks)

Before implementing, validate technical feasibility:

### Research Task 1: llama.cpp KV Cache Export/Import

**Goal:** Determine if llama.cpp supports KV cache serialization and GPU sharing.

**Investigation Steps:**

1. Review llama.cpp source code:
   - `llama.cpp/common/common.cpp` - context management
   - `llama.cpp/include/llama.h` - API for cache access
   - Search for `kv_cache`, `llama_get_kv_cache`, `llama_set_kv_cache`

2. Test KV cache access:
```python
import ctypes
from llama_cpp import Llama

llm = Llama(model_path="model.gguf", n_ctx=16384)

llm.eval([1, 2, 3, 4, 5])

# Attempt to access KV cache
# Research needed: does llama_cpp.Llama expose kv_cache?
# May need ctypes bindings to underlying C functions
```

3. Prototype serialization:
   - If accessible: serialize to bytes, write to file
   - Load in second instance, verify context continuity
   - Measure: serialization time, file size, restoration accuracy

**Decision Point:** If KV cache is not accessible or serialization fails, defer to llama.cpp upstream contribution or alternative approach.

**Estimated Time:** 2-3 weeks

---

### Research Task 2: GPU KV Cache Sharing Mechanisms

**Goal:** Identify method for cross-process GPU memory sharing (CUDA IPC or similar).

**Investigation Steps:**

1. CUDA IPC (Inter-Process Communication):
```python
import cupy as cp

arr = cp.array([1, 2, 3, 4, 5])
ipc_handle = arr.data.get_ipc_handle()

# IPC handle can be shared with other processes
# Other process imports handle and accesses GPU memory directly
```

2. Research constraints:
   - Same GPU required (no cross-GPU IPC)
   - Process synchronization (locks, barriers)
   - Memory lifecycle (who owns, who frees)

3. Prototype cross-process KV share:
   - Process A: allocate KV cache on GPU, export IPC handle
   - Process B: import IPC handle, read KV cache
   - Measure: latency overhead, memory efficiency

**Decision Point:** If CUDA IPC is insufficient, explore alternatives (shared memory + GPU copies, unified memory).

**Estimated Time:** 2-3 weeks

---

### Research Task 3: Prompt Graph Representation

**Goal:** Design graph structure for representing reasoning traces and enable crossover/mutation.

**Investigation Steps:**

1. Define graph schema:
```python
import networkx as nx

G = nx.DiGraph()

G.add_node("root", type="prompt", content="You are a helpful assistant.")
G.add_node("step1", type="reasoning", content="Let me think step by step...")
G.add_node("step2", type="reasoning", content="First, I need to...")
G.add_edge("root", "step1")
G.add_edge("step1", "step2")
```

2. Test prompt reconstruction:
   - Traverse graph (DFS or BFS)
   - Concatenate node contents
   - Generate full prompt string
   - Verify equivalent behavior

3. Design mutation operators:
   - Node substitution (replace reasoning step)
   - Edge rewiring (change flow)
   - Subgraph insertion (add intermediate steps)
   - Subgraph deletion (remove redundant steps)

4. Design crossover operators:
   - Select subgraphs from parent A and parent B
   - Merge at common nodes
   - Validate resulting graph (no cycles, valid flow)

**Decision Point:** If graph complexity becomes unmanageable, simplify to linear chain with insertions/deletions.

**Estimated Time:** 3-4 weeks

---

## Implementation Phase (4-6 months)

### Task 1: C2C Level 3 - KV Cache Serialization

**Goal:** Implement KV cache export/import for llama.cpp.

**Files:**
- Create: `/home/kloros/src/spica/kv_cache.py`
- Create: `/home/kloros/src/spica/llama_bindings.py` (ctypes wrappers if needed)
- Create: `/home/kloros/tests/spica/test_kv_cache.py`

**Prerequisite:** Research Task 1 completed successfully.

### Step 1: Write failing test for KV cache export

```python
import pytest
from src.spica.kv_cache import export_kv_cache, import_kv_cache
from llama_cpp import Llama

def test_export_kv_cache(tmp_path):
    llm = Llama(model_path="/path/to/model.gguf", n_ctx=16384)

    llm.eval([1, 2, 3, 4, 5])

    cache_path = tmp_path / "cache.bin"
    export_kv_cache(llm, cache_path)

    assert cache_path.exists()
    assert cache_path.stat().st_size > 0

def test_import_kv_cache_restores_context(tmp_path):
    llm1 = Llama(model_path="/path/to/model.gguf", n_ctx=16384)
    llm1.eval([1, 2, 3, 4, 5])

    cache_path = tmp_path / "cache.bin"
    export_kv_cache(llm1, cache_path)

    llm2 = Llama(model_path="/path/to/model.gguf", n_ctx=16384)
    import_kv_cache(llm2, cache_path)

    output1 = llm1.eval([6, 7, 8])
    output2 = llm2.eval([6, 7, 8])

    assert output1 == output2
```

### Step 2: Implement KV cache serialization

```python
import ctypes
from pathlib import Path
from llama_cpp import Llama

def export_kv_cache(llm: Llama, output_path: Path):
    # Research-dependent implementation
    # Pseudocode:
    # 1. Access llama context internal state
    # 2. Extract KV cache tensors (keys, values, cell counts)
    # 3. Serialize to binary format (numpy, pickle, custom)
    # 4. Write to file atomically

    raise NotImplementedError("Awaiting research validation")

def import_kv_cache(llm: Llama, cache_path: Path):
    # Research-dependent implementation
    # Pseudocode:
    # 1. Read binary cache file
    # 2. Deserialize tensors
    # 3. Access llama context internal state
    # 4. Overwrite KV cache with loaded data

    raise NotImplementedError("Awaiting research validation")
```

**Note:** Actual implementation requires low-level C API access to llama.cpp internals. May require upstream contribution or C extension module.

### Step 3: Integration with C2C Level 2

Modify `/home/kloros/experiments/spica/template/spica/core/runtime.py`:

```python
from src.spica.kv_cache import export_kv_cache, import_kv_cache

def save_continuity_with_kv_cache(llm, continuity_path: Path):
    continuity_data = load_existing_continuity(continuity_path)

    kv_cache_path = continuity_path.parent / "kv_cache.bin"
    export_kv_cache(llm, kv_cache_path)

    continuity_data["kv_state"] = str(kv_cache_path)
    save_continuity(continuity_path, continuity_data)

def load_continuity_with_kv_cache(llm, continuity_path: Path):
    continuity_data = load_continuity(continuity_path)

    if continuity_data.get("kv_state"):
        kv_cache_path = Path(continuity_data["kv_state"])
        import_kv_cache(llm, kv_cache_path)
```

**Estimated Time:** 6-8 weeks (with research)

---

### Task 2: C2C Level 3 - GPU KV Cache Sharing

**Goal:** Enable direct GPU memory sharing for KV caches between SPICA instances.

**Files:**
- Create: `/home/kloros/src/spica/gpu_kv_share.py`
- Create: `/home/kloros/tests/spica/test_gpu_kv_share.py`

**Prerequisite:** Research Task 2 completed, CUDA IPC validated.

### Step 1: Write failing test for GPU KV sharing

```python
import pytest
import multiprocessing as mp
from src.spica.gpu_kv_share import export_gpu_kv_handle, import_gpu_kv_handle
from llama_cpp import Llama

def process_a(queue):
    llm = Llama(model_path="/path/to/model.gguf", n_ctx=16384, n_gpu_layers=99)
    llm.eval([1, 2, 3, 4, 5])

    ipc_handle = export_gpu_kv_handle(llm)
    queue.put(ipc_handle)

def process_b(ipc_handle, result_queue):
    llm = Llama(model_path="/path/to/model.gguf", n_ctx=16384, n_gpu_layers=99)

    import_gpu_kv_handle(llm, ipc_handle)

    output = llm.eval([6, 7, 8])
    result_queue.put(output)

def test_gpu_kv_sharing():
    queue = mp.Queue()
    result_queue = mp.Queue()

    proc_a = mp.Process(target=process_a, args=(queue,))
    proc_a.start()

    ipc_handle = queue.get()

    proc_b = mp.Process(target=process_b, args=(ipc_handle, result_queue))
    proc_b.start()

    result = result_queue.get()
    proc_a.join()
    proc_b.join()

    assert result is not None
```

### Step 2: Implement GPU KV sharing

```python
import cupy as cp
from llama_cpp import Llama

def export_gpu_kv_handle(llm: Llama):
    # Research-dependent implementation
    # Pseudocode:
    # 1. Access llama KV cache GPU pointer
    # 2. Wrap in cupy array
    # 3. Get IPC handle
    # 4. Serialize handle metadata (shape, dtype, etc.)
    # 5. Return handle + metadata

    raise NotImplementedError("Awaiting research validation")

def import_gpu_kv_handle(llm: Llama, ipc_handle):
    # Research-dependent implementation
    # Pseudocode:
    # 1. Deserialize IPC handle + metadata
    # 2. Import GPU memory via cupy.cuda.memory.UnownedMemory
    # 3. Wrap as cupy array
    # 4. Access llama KV cache GPU pointer
    # 5. Copy data from IPC array to llama cache

    raise NotImplementedError("Awaiting research validation")
```

**Note:** Requires CUDA-enabled llama.cpp build and GPUs on same physical machine.

**Estimated Time:** 8-10 weeks (with research)

---

### Task 3: Prompt Graph Representation

**Goal:** Implement graph-based prompt representation for evolutionary operators.

**Files:**
- Create: `/home/kloros/src/dream/prompt_graph.py`
- Create: `/home/kloros/tests/dream/test_prompt_graph.py`

**Prerequisite:** Research Task 3 completed, graph schema validated.

### Step 1: Write failing test for prompt graph

```python
import pytest
from src.dream.prompt_graph import PromptGraph, mutate_graph, crossover_graphs

def test_create_prompt_graph():
    graph = PromptGraph()
    graph.add_node("root", content="You are a helpful assistant.", type="system")
    graph.add_node("step1", content="Let me think...", type="reasoning")
    graph.add_edge("root", "step1")

    assert len(graph.nodes) == 2
    assert graph.has_edge("root", "step1")

def test_graph_to_prompt_string():
    graph = PromptGraph()
    graph.add_node("root", content="System prompt", type="system")
    graph.add_node("step1", content="Step 1", type="reasoning")
    graph.add_edge("root", "step1")

    prompt_str = graph.to_prompt_string()
    assert "System prompt" in prompt_str
    assert "Step 1" in prompt_str

def test_mutate_graph_node_substitution():
    graph = PromptGraph()
    graph.add_node("root", content="Original", type="system")
    graph.add_node("step1", content="Step 1", type="reasoning")
    graph.add_edge("root", "step1")

    mutated = mutate_graph(graph, mutation_type="substitute_node")

    assert len(mutated.nodes) == len(graph.nodes)
    assert mutated != graph

def test_crossover_graphs():
    graph_a = PromptGraph()
    graph_a.add_node("root", content="A system", type="system")
    graph_a.add_node("step1", content="A step 1", type="reasoning")
    graph_a.add_edge("root", "step1")

    graph_b = PromptGraph()
    graph_b.add_node("root", content="B system", type="system")
    graph_b.add_node("step1", content="B step 1", type="reasoning")
    graph_b.add_edge("root", "step1")

    offspring = crossover_graphs(graph_a, graph_b)

    assert len(offspring.nodes) >= 2
    prompt_str = offspring.to_prompt_string()
    assert len(prompt_str) > 0
```

### Step 2: Implement prompt graph

```python
import networkx as nx
import random
from typing import List, Dict, Any

class PromptGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_node(self, node_id: str, content: str, type: str):
        self.graph.add_node(node_id, content=content, type=type)

    def add_edge(self, from_node: str, to_node: str):
        self.graph.add_edge(from_node, to_node)

    @property
    def nodes(self):
        return self.graph.nodes

    def has_edge(self, from_node, to_node):
        return self.graph.has_edge(from_node, to_node)

    def to_prompt_string(self) -> str:
        sorted_nodes = list(nx.topological_sort(self.graph))
        parts = []
        for node_id in sorted_nodes:
            node_data = self.graph.nodes[node_id]
            parts.append(node_data["content"])
        return "\n\n".join(parts)

    def copy(self):
        new_graph = PromptGraph()
        new_graph.graph = self.graph.copy()
        return new_graph

def mutate_graph(graph: PromptGraph, mutation_type: str = "substitute_node") -> PromptGraph:
    mutated = graph.copy()

    if mutation_type == "substitute_node":
        nodes = list(mutated.nodes)
        if len(nodes) > 1:
            node_to_mutate = random.choice([n for n in nodes if n != "root"])
            node_data = mutated.graph.nodes[node_to_mutate]

            mutated.graph.nodes[node_to_mutate]["content"] = node_data["content"] + " [mutated]"

    elif mutation_type == "add_node":
        nodes = list(mutated.nodes)
        parent = random.choice(nodes)
        new_id = f"step_{random.randint(1000, 9999)}"
        mutated.add_node(new_id, content="Inserted reasoning step", type="reasoning")
        mutated.add_edge(parent, new_id)

    elif mutation_type == "delete_node":
        nodes = [n for n in mutated.nodes if n != "root"]
        if nodes:
            node_to_delete = random.choice(nodes)
            mutated.graph.remove_node(node_to_delete)

    return mutated

def crossover_graphs(graph_a: PromptGraph, graph_b: PromptGraph) -> PromptGraph:
    offspring = PromptGraph()

    root_content_a = graph_a.graph.nodes["root"]["content"]
    root_content_b = graph_b.graph.nodes["root"]["content"]
    merged_root = root_content_a if random.random() < 0.5 else root_content_b
    offspring.add_node("root", content=merged_root, type="system")

    nodes_a = [n for n in graph_a.nodes if n != "root"]
    nodes_b = [n for n in graph_b.nodes if n != "root"]

    selected = nodes_a[:len(nodes_a)//2] + nodes_b[:len(nodes_b)//2]

    for i, node_id in enumerate(selected):
        source_graph = graph_a if node_id in nodes_a else graph_b
        node_data = source_graph.graph.nodes[node_id]
        new_id = f"step_{i+1}"
        offspring.add_node(new_id, content=node_data["content"], type=node_data["type"])

    sorted_nodes = [n for n in offspring.nodes if n != "root"]
    offspring.add_edge("root", sorted_nodes[0] if sorted_nodes else "root")
    for i in range(len(sorted_nodes) - 1):
        offspring.add_edge(sorted_nodes[i], sorted_nodes[i+1])

    return offspring
```

**Estimated Time:** 4-6 weeks

---

### Task 4: D-REAM Integration with Prompt Graphs

**Goal:** Integrate prompt_graph mutations into D-REAM evolutionary loop.

**Files:**
- Modify: `/home/kloros/src/dream/evolutionary_algorithm.py`
- Create: `/home/kloros/src/dream/graph_operators.py`
- Create: `/home/kloros/tests/dream/test_graph_evolution.py`

### Step 1: Extend genome representation

Current genome:
```python
genome = {
    "system_prompt": "...",
    "config": {...}
}
```

New genome with graph:
```python
genome = {
    "prompt_graph": PromptGraph(...),
    "config": {...}
}
```

### Step 2: Implement graph mutation operator

```python
from src.dream.prompt_graph import mutate_graph

def mutate_population(population: List[Dict]) -> List[Dict]:
    mutated = []
    for individual in population:
        if random.random() < MUTATION_RATE:
            new_individual = individual.copy()
            new_individual["prompt_graph"] = mutate_graph(
                individual["prompt_graph"],
                mutation_type=random.choice(["substitute_node", "add_node", "delete_node"])
            )
            mutated.append(new_individual)
        else:
            mutated.append(individual)
    return mutated
```

### Step 3: Implement graph crossover

```python
from src.dream.prompt_graph import crossover_graphs

def crossover(parent_a: Dict, parent_b: Dict) -> Dict:
    offspring = {
        "prompt_graph": crossover_graphs(
            parent_a["prompt_graph"],
            parent_b["prompt_graph"]
        ),
        "config": {**parent_a["config"], **parent_b["config"]}  # merge configs
    }
    return offspring
```

**Estimated Time:** 3-4 weeks

---

### Task 5: Multi-Host SPICA Coordination

**Goal:** Distribute SPICA instances across multiple machines with shared capability registry.

**Files:**
- Create: `/home/kloros/src/spica/distributed_registry.py`
- Create: `/home/kloros/tests/spica/test_distributed_registry.py`

**Prerequisite:** etcd or Consul deployed and accessible.

### Step 1: Replace local JSON registry with distributed store

```python
import etcd3

class DistributedCapabilityRegistry:
    def __init__(self, etcd_host: str, etcd_port: int):
        self.client = etcd3.client(host=etcd_host, port=etcd_port)

    def register(self, capability, specialization, provider, socket, version, state="INTEGRATED"):
        key = f"/spica/capabilities/{capability}/{specialization}"
        value = json.dumps({
            "provider": provider,
            "state": state,
            "socket": socket,
            "version": version,
            "last_heartbeat": time.time(),
            "host": socket.gethostname()
        })
        self.client.put(key, value)

    def query(self, capability, specialization):
        key = f"/spica/capabilities/{capability}/{specialization}"
        value, metadata = self.client.get(key)
        if value:
            return json.loads(value.decode())
        return None
```

### Step 2: Update RPC clients for remote sockets

Instead of Unix sockets, use HTTP RPC over network:

```python
import requests

def rpc_call_remote(host: str, port: int, method: str, params: dict):
    url = f"http://{host}:{port}/rpc"
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": "remote-call"
    }
    response = requests.post(url, json=request)
    return response.json()
```

### Step 3: Add HTTP RPC server alongside Unix socket

Modify `/home/kloros/src/spica/rpc_server.py`:

```python
from flask import Flask, request, jsonify

def start_http_rpc_server(manager: SPICAServiceManager, port: int):
    app = Flask(__name__)

    @app.route('/rpc', methods=['POST'])
    def handle_rpc():
        req = request.get_json()
        method = req.get("method")
        params = req.get("params", {})

        if method == "differentiate":
            result = manager.differentiate(params["recipe_path"])
        elif method == "query_state":
            result = manager.get_status()
        elif method == "reprogram":
            result = manager.reprogram()
        else:
            return jsonify({
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Method not found"},
                "id": req.get("id")
            })

        return jsonify({"jsonrpc": "2.0", "result": result, "id": req.get("id")})

    app.run(host='0.0.0.0', port=port)
```

**Estimated Time:** 6-8 weeks

---

## Integration & Testing (2-3 months)

### Integration Test Suite

Create `/home/kloros/tests/integration/test_phase4_features.py`:

```python
import pytest

def test_c2c_level3_kv_cache_handoff():
    # Test KV cache export/import preserves context
    pass

def test_c2c_level3_gpu_sharing():
    # Test GPU IPC KV cache sharing across processes
    pass

def test_prompt_graph_mutation():
    # Test graph mutations preserve validity
    pass

def test_prompt_graph_crossover():
    # Test graph crossover produces valid offspring
    pass

def test_d_ream_with_prompt_graphs():
    # Test full D-REAM cycle with graph genomes
    pass

def test_multi_host_registry():
    # Test capability registry across hosts
    pass

def test_multi_host_rpc():
    # Test RPC calls to remote SPICA instances
    pass
```

---

## Deployment Checklist (Phase 4)

```markdown
- [ ] Research phase complete (all 3 tasks validated)
- [ ] C2C Level 3 tests passing (KV cache + GPU sharing)
- [ ] Prompt graph tests passing (mutation + crossover)
- [ ] D-REAM integration tests passing
- [ ] Distributed registry deployed (etcd/Consul)
- [ ] Multi-host coordination tested (2+ machines)
- [ ] Performance benchmarks run (speedup vs Level 2)
- [ ] Documentation updated
- [ ] Phase 4 deployment guide created
```

---

## Success Metrics

**C2C Level 3:**
- KV cache export/import: <100ms overhead
- GPU sharing: 2-5x speedup vs re-computation
- Context continuity: 100% accuracy

**Prompt Graphs:**
- Mutation validity: 100% (no invalid graphs)
- Crossover validity: 100%
- Evolutionary improvement: fitness increase over baseline

**Multi-Host:**
- Registry latency: <50ms for query
- RPC latency: <100ms for remote call
- Scalability: 10+ hosts supported

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| llama.cpp KV cache not accessible | High | High | Contribute upstream or use alternative LLM runtime |
| CUDA IPC insufficient | Medium | High | Fall back to serialization + GPU copy |
| Prompt graphs too complex | Medium | Medium | Simplify to linear chains |
| etcd/Consul operational overhead | Low | Medium | Start with single-host, defer multi-host |
| Research takes longer than expected | High | Low | Accept extended timeline, iterative refinement |

---

## Alternative Approaches

**If C2C Level 3 proves infeasible:**
- Accept C2C Level 2 (serialization) as sufficient
- Explore alternative LLM runtimes (vLLM, TGI) with native KV cache APIs
- Defer to future when llama.cpp adds explicit cache management

**If Prompt Graphs prove too complex:**
- Use simpler template substitution (string-based)
- Focus on config evolution instead of prompt evolution
- Treat prompts as atomic units (no graph structure)

**If Multi-Host coordination is unnecessary:**
- Accept single-host limitation
- Scale vertically (more GPUs per machine)
- Use Phase 3 persistent services as sufficient

---

## Reference Documentation

- SPICA Architecture Spec v1.1.1: `/home/claude_temp/SPICA_ARCHITECTURE_SPEC_v1.1.1.md`
- Phase 3 Implementation Plan: `/home/kloros/docs/plans/2025-11-05-spica-persistent-services-phase3.md`
- llama.cpp Documentation: https://github.com/ggerganov/llama.cpp
- CUDA IPC Guide: https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#interprocess-communication
- NetworkX Documentation: https://networkx.org/documentation/stable/

---

## Notes

- Phase 4 is research-heavy; timelines are estimates with high uncertainty
- Features are decoupled; can implement independently (C2C Level 3, then prompt graphs, then multi-host)
- Research phase MUST complete before committing to implementation
- If any research task fails validation, that feature moves to "deferred" status
- Phase 3 provides substantial value; Phase 4 is optimization, not requirement
- Autopoiesis (self-improvement) can occur with Phases 0-3; Phase 4 accelerates it

---

**Status:** 🔮 Planned (awaiting research validation)
**Priority:** Low (optimization over Phase 3 foundation)
**Risk:** High (novel techniques, uncertain feasibility)
