# ChromaDB Integration for KLoROS - Implementation Blueprint

**Status:** Ready for Implementation
**Confidence:** 93.5%
**Estimated Effort:** 9-15 hours
**Date Prepared:** October 9, 2025

---

## Executive Summary

Add semantic memory substrate (ChromaDB) to KLoROS for enhanced RAG, episodic recall, and D-REAM evolution while maintaining clean migration path to alternate vector stores. This implementation builds on existing memory architecture without disrupting operational systems.

**Key Benefits:**
- Semantic search for memory retrieval (vs current keyword-only)
- D-REAM candidate diversity sampling to avoid mode collapse
- Foundation for Phase 3 semantic/linguistic evolution
- Improved conversation continuity through context fusion

---

## Dependencies & Compatibility

### Required Packages

```bash
# Primary dependencies
chromadb>=0.4.15              # Vector database
sentence-transformers>=2.2.2  # Embedding models

# Transitive dependencies (auto-installed)
onnxruntime>=1.16.0          # For sentence-transformers
torch>=2.0.0                 # Already installed (PyTorch for Whisper/Resemblyzer)
numpy>=1.24.0                # Already installed
pydantic>=2.0.0              # Already installed (kloros_memory uses it)
```

### Compatibility Matrix

| Component | Current Version | ChromaDB Requirement | Status |
|-----------|----------------|---------------------|--------|
| Python | 3.11+ | ≥3.8 | ✅ Compatible |
| PyTorch | 2.x (cuda) | ≥1.13 | ✅ Compatible |
| NumPy | 2.3.3 | ≥1.22 | ✅ Compatible |
| Pydantic | 2.x | ≥1.10 | ✅ Compatible |
| SQLite | 3.x | N/A (independent) | ✅ No conflict |

### GPU Compatibility

**Hardware:** RTX 3060 (12GB VRAM), GTX 1080 Ti (11GB VRAM)

**Embedding Model Allocation:**
- BGE-small-en-v1.5: ~400MB VRAM, 384-dim embeddings
- Fallback: all-MiniLM-L6-v2: ~120MB VRAM, 384-dim embeddings
- **Strategy:** Use cuda:0 (RTX 3060) for embeddings alongside Whisper

**VRAM Budget (RTX 3060):**
```
Whisper tiny:        ~1GB   (STT backend)
Resemblyzer:         ~500MB (speaker identification)
BGE-small:           ~400MB (new - embeddings)
Qwen2.5 (Ollama):    Runs on CPU/separate context
---------------------------------------------
Total GPU usage:     ~2GB / 12GB available
Status:              ✅ 10GB headroom, safe
```

### Disk Space Requirements

```
ChromaDB installation:       ~150MB
BGE-small-en-v1.5 model:     ~133MB (cached in ~/.cache/huggingface)
Chroma persist directory:    ~50MB per 10k vectors (estimate)
---------------------------------------------
Total for 100k events:       ~800MB
Status:                      ✅ Acceptable for NVMe storage
```

---

## Architecture Integration Points

### Existing Systems to Preserve

**1. Memory System** (`/home/kloros/src/kloros_memory/`)
- ✅ SQLite WAL mode storage (no changes)
- ✅ Event/Episode/Summary models (extend, not replace)
- ✅ ContextRetriever scoring (enhance with semantic)
- ✅ MemoryLogger (add dual-write hook)

**2. RAG System** (`/home/kloros/src/reasoning/local_rag_backend.py`)
- ✅ Current 384-dim embeddings (match with BGE)
- ✅ Voice sample retrieval (parallel path, not replacement)
- ✅ SentenceTransformer pattern (reuse lines 62-87)

**3. D-REAM System** (`/home/kloros/src/dream/`)
- ✅ CandidatePack v2 schema (add embedding metadata)
- ✅ Evaluation artifacts (store embeddings alongside JSON)
- ✅ Domain evaluators (no changes)

**4. Voice Pipeline** (`/home/kloros/src/kloros_voice.py`)
- ✅ No direct changes (memory integration is transparent)
- ✅ Memory-enhanced wrapper handles Chroma (integration.py)

### New Module Structure

```
/home/kloros/src/vector_store/
├── __init__.py              # Module exports
├── base.py                  # VectorStore protocol (migration seam)
├── chroma_adapter.py        # ChromaDB implementation
├── embedder.py              # BGE wrapper with caching
└── fusion.py                # Retrieval fusion logic (optional - may inline)
```

---

## Implementation Phases

### Phase 0: Environment Setup (30 minutes, 98% confidence)

**Installation Commands:**
```bash
# Activate KLoROS venv
source /home/kloros/kloros_venv/bin/activate

# Install packages
pip install chromadb sentence-transformers

# Download and cache embedding model
python3 << 'PYEOF'
from sentence_transformers import SentenceTransformer
print("Downloading BGE-small-en-v1.5...")
model = SentenceTransformer('BAAI/bge-small-en-v1.5')
print(f"Model loaded: {model.get_sentence_embedding_dimension()} dimensions")
PYEOF

# Verify installation
python3 -c "import chromadb; print('ChromaDB:', chromadb.__version__)"
```

**Environment Variables:**
Add to `/home/kloros/.kloros_env`:
```bash
# ChromaDB Configuration
export KLR_CHROMA_DIR=/home/kloros/.kloros/chroma
export KLR_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
export KLR_ENABLE_CHROMA=1
export KLR_CHROMA_BATCH_SIZE=50
export KLR_CHROMA_COLLECTION=kloros_memory

# Fusion Weights (tunable)
export KLR_FUSION_SEMANTIC_WEIGHT=0.6
export KLR_FUSION_RECENCY_WEIGHT=0.25
export KLR_FUSION_IMPORTANCE_WEIGHT=0.15
```

**Validation:**
- [ ] chromadb imports successfully
- [ ] sentence_transformers imports successfully
- [ ] BGE model downloads (~133MB)
- [ ] Model produces 384-dim vectors
- [ ] Environment variables loaded

---

### Phase A: Vector Store Adapter (2-3 hours, 95% confidence)

#### File 1: `/home/kloros/src/vector_store/__init__.py`
```python
"""Vector store abstraction for KLoROS semantic memory."""

from .base import VectorStore
from .chroma_adapter import ChromaAdapter
from .embedder import Embedder

__all__ = ["VectorStore", "ChromaAdapter", "Embedder"]
```

#### File 2: `/home/kloros/src/vector_store/base.py`
**Purpose:** Protocol for backend independence (migration seam)

**Key Methods:**
```python
class VectorStore(Protocol):
    def upsert(self, collection: str, ids: List[str],
               texts: List[str], metadatas: List[dict],
               embeddings: Optional[List[List[float]]]) -> None

    def query(self, collection: str, query_texts: List[str],
              n_results: int, where: Optional[dict]) -> dict

    def delete(self, collection: str, where: Optional[dict],
               ids: Optional[List[str]]) -> None

    def get_stats(self) -> dict
```

**Design Notes:**
- Mirror blueprint §5 interface exactly
- Type hints for Qdrant/Milvus future compatibility
- Stats method for observability

#### File 3: `/home/kloros/src/vector_store/embedder.py`
**Purpose:** BGE model wrapper with caching

**Key Features:**
- Reuse SentenceTransformer pattern from local_rag_backend.py:62-87
- Thread-local model instance (like MemoryStore._local)
- Batch encoding for efficiency
- Dimension validation (384 required)

**Integration Pattern:**
```python
class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self._local = threading.local()  # Thread safety
        self.model_name = model_name

    def _get_model(self) -> SentenceTransformer:
        if not hasattr(self._local, 'model'):
            self._local.model = SentenceTransformer(self.model_name)
        return self._local.model

    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        return model.encode(texts, normalize_embeddings=True).tolist()
```

#### File 4: `/home/kloros/src/vector_store/chroma_adapter.py`
**Purpose:** ChromaDB implementation of VectorStore protocol

**Key Features:**
- Persistent mode: `Settings(persist_directory=KLR_CHROMA_DIR)`
- HNSW cosine similarity: `metadata={"hnsw:space": "cosine"}`
- Auto-create collection on first use
- Batch upsert optimization (default 50 items)

**Critical Configuration:**
```python
import chromadb
from chromadb.config import Settings

client = chromadb.Client(Settings(
    persist_directory="/home/kloros/.kloros/chroma",
    anonymized_telemetry=False  # Offline-first
))

collection = client.get_or_create_collection(
    name="kloros_memory",
    metadata={"hnsw:space": "cosine"}  # Blueprint requirement
)
```

**Validation:**
- [ ] Creates collection with cosine similarity
- [ ] Persists to disk correctly
- [ ] Handles batch upserts (50+ items)
- [ ] Query returns distances in [0, 2] range (cosine)
- [ ] Thread-safe operations

---

### Phase B: Dual-Write Integration (3-4 hours, 92% confidence)

#### Modification 1: `/home/kloros/src/kloros_memory/logger.py`

**Location:** After SQLite insert in `log_event()` method (~line 200)

**Integration Point:**
```python
def log_event(self, event: Event) -> Optional[int]:
    # Existing SQLite insert
    event_id = self.store.insert_event(event)

    # NEW: Dual-write to Chroma (non-blocking)
    if self.chroma_enabled:
        self._async_upsert_to_chroma(event, event_id)

    return event_id

def _async_upsert_to_chroma(self, event: Event, event_id: int):
    """Non-blocking Chroma upsert via thread pool."""
    self._chroma_queue.append((event, event_id))

    # Batch when queue reaches threshold
    if len(self._chroma_queue) >= self.chroma_batch_size:
        self._flush_chroma_queue()
```

**Metadata Mapping:**
```python
# Event → Chroma metadata
metadata = {
    "event_id": str(event_id),
    "ts_iso": datetime.fromtimestamp(event.timestamp).isoformat(),
    "type": event.event_type.value,
    "actor": "user" if event.event_type == EventType.USER_INPUT else "kloros",
    "session_id": event.conversation_id or "unknown",
    "importance": event.metadata.get("importance", 0.0),
    "tags": event.metadata.get("tags", []),
    "embedder": "bge-small-en-v1.5",
    "embedder_ver": "1.5.0"
}
```

**Batch Strategy:**
- Queue size: 50 events (configurable via `KLR_CHROMA_BATCH_SIZE`)
- Timeout flush: 60 seconds if queue doesn't fill
- Thread pool: 1-2 workers for async upserts

**Validation:**
- [ ] Events appear in both SQLite and Chroma
- [ ] Batch upserts work correctly
- [ ] No blocking on main thread
- [ ] event_id linkage preserved
- [ ] Metadata fields match blueprint

#### Modification 2: `/home/kloros/src/kloros_memory/integration.py`

**Location:** `MemoryEnhancedKLoROS.__init__()` method (line 40-43)

**Integration:**
```python
def __init__(self, kloros_instance):
    self.kloros = kloros_instance

    # Existing memory components
    self.memory_store = MemoryStore()
    self.memory_logger = MemoryLogger(self.memory_store)

    # NEW: Initialize Chroma components
    if int(os.getenv("KLR_ENABLE_CHROMA", "1")):
        from src.vector_store.chroma_adapter import ChromaAdapter
        from src.vector_store.embedder import Embedder

        self.embedder = Embedder()
        self.chroma = ChromaAdapter(embedder=self.embedder)

        # Pass Chroma adapter to logger
        self.memory_logger.set_chroma_adapter(self.chroma)
    else:
        self.chroma = None

    # ... rest of initialization
```

**Validation:**
- [ ] ChromaAdapter initializes without errors
- [ ] Embedder loads BGE model successfully
- [ ] Graceful degradation if KLR_ENABLE_CHROMA=0
- [ ] No impact on existing memory operations

---

### Phase C: Retrieval Fusion (2-3 hours, 94% confidence)

#### Modification: `/home/kloros/src/kloros_memory/retriever.py`

**Location:** `retrieve_context()` method (line 54)

**Enhanced Retrieval Logic:**
```python
def retrieve_context(self, request: ContextRetrievalRequest) -> ContextRetrievalResult:
    # Existing time window calculation
    time_cutoff = self._calculate_time_cutoff(request)

    # NEW: Chroma semantic retrieval (overfetch)
    if self.chroma_enabled:
        chroma_results = self._query_chroma(
            query_text=request.query,
            n_results=request.max_events * 3,  # Overfetch for fusion
            time_cutoff=time_cutoff
        )
    else:
        chroma_results = []

    # Existing episodic retrieval (time window)
    episodic_results = self._get_candidate_events(
        conversation_id=request.conversation_id,
        time_cutoff=time_cutoff,
        limit=request.max_events * 3
    )

    # NEW: Fusion scoring
    fused_results = self._fuse_results(
        chroma_results=chroma_results,
        episodic_results=episodic_results,
        query=request.query
    )

    # Dedupe and return top-k
    return self._build_result(fused_results[:request.max_events])
```

**Fusion Formula (Blueprint §3):**
```python
def _fuse_results(self, chroma_results, episodic_results, query):
    now = time.time()
    scored = []

    for result in chroma_results + episodic_results:
        # Normalize Chroma distance to similarity (0..1)
        semantic_sim = 1.0 - (result.get('distance', 1.0) / 2.0)

        # Recency boost (existing formula)
        recency = self._recency_boost(result['timestamp'], now)

        # Importance from metadata
        importance = result.get('importance', 0.0)

        # Weighted fusion
        final_score = (
            self.semantic_weight * semantic_sim +
            self.recency_weight * recency +
            self.importance_weight * importance
        )

        scored.append((final_score, result))

    # Sort by score, dedupe by event_id
    scored.sort(reverse=True)
    return self._dedupe_by_event_id(scored)
```

**Configuration:**
```python
# Scoring weights (from env or defaults)
self.semantic_weight = float(os.getenv("KLR_FUSION_SEMANTIC_WEIGHT", "0.6"))
self.recency_weight = float(os.getenv("KLR_FUSION_RECENCY_WEIGHT", "0.25"))
self.importance_weight = float(os.getenv("KLR_FUSION_IMPORTANCE_WEIGHT", "0.15"))
```

**Validation:**
- [ ] Semantic results from Chroma
- [ ] Episodic results from SQLite
- [ ] Fusion scores calculated correctly
- [ ] Deduplication by event_id works
- [ ] Top-k results returned
- [ ] Fallback to SQLite-only if Chroma disabled

---

### Phase D: D-REAM Candidate Indexing (2-3 hours, 91% confidence)

#### New File: `/home/kloros/src/dream/chroma_integration.py`

**Purpose:** Index D-REAM candidates for diversity sampling

**Key Functions:**

1. **Candidate Embedding:**
```python
def index_candidate(candidate_pack: CandidatePack, chroma: ChromaAdapter):
    """Index a candidate pack in Chroma."""
    # Create canonical text representation
    text = _canonicalize_candidate(candidate_pack)

    # Metadata for filtering
    metadata = {
        "event_id": candidate_pack.cand_id,
        "run_id": candidate_pack.run_id,
        "gen": candidate_pack.generation,
        "domain": candidate_pack.domain,
        "score": candidate_pack.fitness,
        "status": "best" if candidate_pack.fitness > 0 else "failed",
        "ts_iso": datetime.now().isoformat(),
        "type": "candidate",
        "tags": list(candidate_pack.genome.keys())  # Genome parameters as tags
    }

    # Upsert to dedicated collection
    chroma.upsert(
        collection="kloros_dream_candidates",
        ids=[candidate_pack.cand_id],
        texts=[text],
        metadatas=[metadata]
    )

def _canonicalize_candidate(pack: CandidatePack) -> str:
    """Create embedable text from candidate."""
    # Deterministic JSON representation
    genome_str = json.dumps(pack.genome, sort_keys=True)

    # Add human-readable context
    context = f"Domain: {pack.domain}\n"
    context += f"Generation: {pack.generation}\n"
    context += f"Fitness: {pack.fitness:.4f}\n"
    context += f"Genome: {genome_str}\n"

    # Add regime KPIs for semantic richness
    for regime in pack.regimes:
        context += f"{regime.regime}: {regime.kpis}\n"

    return context
```

2. **Diversity Sampling:**
```python
def sample_diverse_candidates(
    seed_genome: dict,
    k: int,
    chroma: ChromaAdapter,
    domain: str
) -> List[CandidatePack]:
    """Sample diverse candidates for mutation/crossover."""

    # Query for semantic neighbors
    query_text = _canonicalize_genome(seed_genome)
    results = chroma.query(
        collection="kloros_dream_candidates",
        query_texts=[query_text],
        n_results=k * 5,  # Overfetch
        where={"domain": domain, "status": "best"}
    )

    # Extract embeddings for clustering
    embeddings = [r['embedding'] for r in results]

    # K-means diversity sampling
    clusters = kmeans_diversity_sample(embeddings, k)

    # Return one candidate per cluster
    diverse_ids = [results[idx]['event_id'] for idx in clusters]
    return load_candidates_by_id(diverse_ids)
```

**Integration Points:**
- Hook into domain evaluators after fitness calculation
- Add to candidate_pack.py write method
- Use in selection phase of evolution loop

**Validation:**
- [ ] Candidates indexed with genome + telemetry
- [ ] Metadata filtering works (domain, status, gen)
- [ ] Diversity sampling returns varied genomes
- [ ] Better than random sampling (test with metrics)

---

### Phase E: Testing & Validation (2 hours, 90% confidence)

#### Test 1: Golden Query Set

**Create:** `/home/kloros/tests/chroma_golden_queries.json`
```json
[
  {
    "query": "audio pipeline xruns",
    "expected_event_ids": ["evt_123", "evt_456"],
    "min_recall": 0.8
  },
  {
    "query": "memory system condensation",
    "expected_event_ids": ["evt_789"],
    "min_recall": 1.0
  }
]
```

**Test Script:**
```python
def test_golden_queries():
    for test_case in load_golden_queries():
        results = retriever.retrieve_context(
            ContextRetrievalRequest(query=test_case['query'], max_events=10)
        )

        retrieved_ids = {e.id for e in results.events}
        expected_ids = set(test_case['expected_event_ids'])

        recall = len(retrieved_ids & expected_ids) / len(expected_ids)
        assert recall >= test_case['min_recall'], f"Recall {recall} < {test_case['min_recall']}"
```

#### Test 2: RAG Precision Measurement

**Baseline:** Current keyword-based RAG precision
**Target:** +10-20% improvement with semantic search

**Metrics:**
- Precision@5: Relevant results in top 5
- Recall@10: Coverage of relevant results
- Mean Reciprocal Rank (MRR)

#### Test 3: D-REAM Diversity

**Test:** Compare random vs semantic diversity sampling
**Metric:** Genome parameter variance across selected candidates
**Expected:** 30-50% higher variance with semantic sampling

#### Test 4: Performance

**Load Test:**
- Insert 1000 events
- Query 100 times
- Measure p95 latency

**Target:** <50ms p95 query latency (blueprint requirement)

**Validation:**
- [ ] Golden queries pass
- [ ] RAG precision improved
- [ ] Diversity sampling better than random
- [ ] Performance targets met
- [ ] No memory leaks (long-running test)

---

## Risk Mitigation & Contingencies

### Risk 1: BGE Model Download Failure
**Probability:** Low (5%)
**Impact:** High (blocks Phase 0)
**Mitigation:** Fallback to all-MiniLM-L6-v2 (already in RAG code)
**Recovery:** Manual model download from HuggingFace

### Risk 2: VRAM Exhaustion
**Probability:** Low (10%)
**Impact:** Medium (embeddings fail)
**Mitigation:** Force CPU mode for embeddings: `device='cpu'`
**Recovery:** BGE-small is fast enough on CPU (~100ms per batch)

### Risk 3: Chroma Performance Degradation
**Probability:** Medium (20%)
**Impact:** Medium (slow queries)
**Mitigation:**
- Batch writes (50+ items)
- Monitor collection size
- Vacuum/compact periodically
**Recovery:** VectorStore abstraction allows Qdrant migration

### Risk 4: Thread Safety Issues
**Probability:** Low (10%)
**Impact:** High (crashes, data corruption)
**Mitigation:** Use threading.local pattern (proven in MemoryStore)
**Recovery:** Add connection pooling if needed

### Risk 5: Embedding Dimension Mismatch
**Probability:** Very Low (2%)
**Impact:** Critical (incompatible vectors)
**Mitigation:** Validate dimensions on startup (384 required)
**Recovery:** Re-embed entire corpus with correct model

---

## Environment Variable Reference

```bash
# ChromaDB Core
KLR_CHROMA_DIR=/home/kloros/.kloros/chroma         # Persist directory
KLR_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5          # HuggingFace model ID
KLR_ENABLE_CHROMA=1                                 # Enable/disable
KLR_CHROMA_BATCH_SIZE=50                            # Batch upsert size
KLR_CHROMA_COLLECTION=kloros_memory                 # Collection name

# Retrieval Fusion Weights (sum to 1.0)
KLR_FUSION_SEMANTIC_WEIGHT=0.6                      # Semantic similarity
KLR_FUSION_RECENCY_WEIGHT=0.25                      # Time decay
KLR_FUSION_IMPORTANCE_WEIGHT=0.15                   # User/agent importance

# Performance Tuning
KLR_CHROMA_QUERY_OVERFETCH=3                        # Overfetch multiplier
KLR_EMBEDDING_BATCH_SIZE=32                         # Encode batch size
KLR_EMBEDDING_DEVICE=cuda:0                         # CPU or cuda:N

# D-REAM Integration
KLR_DREAM_CHROMA_ENABLED=1                          # Index candidates
KLR_DREAM_DIVERSITY_K=5                             # Diversity sample size
```

---

## Success Criteria

### Functional Requirements
- [ ] Dialogue events dual-written to SQLite + Chroma
- [ ] Semantic search returns relevant results
- [ ] Retrieval fusion combines semantic + episodic
- [ ] D-REAM candidates indexed and searchable
- [ ] Diversity sampling produces varied genomes

### Performance Requirements
- [ ] Query latency p95 < 50ms (1-5M vectors)
- [ ] No blocking on main voice pipeline thread
- [ ] VRAM usage < 3GB total (embeddings + STT)
- [ ] Disk usage < 1GB per 100k events

### Quality Requirements
- [ ] RAG precision +10-20% vs baseline
- [ ] Conversation continuity improved (fewer "lost context" events)
- [ ] D-REAM convergence 20-30% faster
- [ ] No crashes or data loss in 72-hour stress test

---

## Post-Implementation: Phase 3 Enablement

ChromaDB provides foundation for Phase 3 (Semantic/Linguistic Evolution):

**Enabled Capabilities:**
1. **Baseline Embeddings:** Capture current KLoROS response style
2. **Evolution Metrics:** Measure semantic drift of evolved responses
3. **Diversity Preservation:** Prevent mode collapse in prompt evolution
4. **Quality Scoring:** Embedding-based coherence/personality metrics

**Phase 3 will leverage:**
- Same embedding model (BGE) for consistency
- Same fusion formula for fitness calculation
- Same diversity sampling for prompt variation
- Chroma collections for evolved prompts/RAG configs

---

## Appendix: File Inventory

### New Files (7 total)
1. `/home/kloros/src/vector_store/__init__.py`
2. `/home/kloros/src/vector_store/base.py`
3. `/home/kloros/src/vector_store/chroma_adapter.py`
4. `/home/kloros/src/vector_store/embedder.py`
5. `/home/kloros/src/dream/chroma_integration.py`
6. `/home/kloros/tests/chroma_golden_queries.json`
7. `/home/kloros/tests/test_chroma_integration.py`

### Modified Files (3 total)
1. `/home/kloros/src/kloros_memory/logger.py` (dual-write)
2. `/home/kloros/src/kloros_memory/retriever.py` (fusion)
3. `/home/kloros/src/kloros_memory/integration.py` (initialization)

### Configuration Files (1 total)
1. `/home/kloros/.kloros_env` (add ChromaDB variables)

**Total Implementation Surface:** 11 files

---

## Execution Checklist

### Pre-Implementation
- [ ] Review this blueprint thoroughly
- [ ] Verify token budget availability
- [ ] Backup current memory.db
- [ ] Document current RAG precision baseline

### Phase 0
- [ ] Install chromadb and sentence-transformers
- [ ] Download BGE-small-en-v1.5 model
- [ ] Add environment variables to .kloros_env
- [ ] Verify GPU compatibility

### Phase A
- [ ] Create vector_store module structure
- [ ] Implement VectorStore protocol
- [ ] Implement ChromaAdapter
- [ ] Implement Embedder with thread safety
- [ ] Unit test: upsert, query, delete

### Phase B
- [ ] Add dual-write to MemoryLogger
- [ ] Implement batch queue with flush
- [ ] Initialize ChromaAdapter in integration.py
- [ ] Test: events appear in both stores

### Phase C
- [ ] Enhance ContextRetriever with Chroma query
- [ ] Implement fusion scoring
- [ ] Add deduplication logic
- [ ] Test: golden queries pass

### Phase D
- [ ] Create chroma_integration.py
- [ ] Implement candidate indexing
- [ ] Implement diversity sampling
- [ ] Hook into domain evaluators
- [ ] Test: diversity > random sampling

### Phase E
- [ ] Run golden query tests
- [ ] Measure RAG precision improvement
- [ ] Load test (1000 events, 100 queries)
- [ ] Stress test (72 hours)
- [ ] Document results

### Post-Implementation
- [ ] Update CLAUDE.md with ChromaDB status
- [ ] Create performance baseline report
- [ ] Plan Phase 3 integration points
- [ ] Archive this blueprint

---

**End of Blueprint**
