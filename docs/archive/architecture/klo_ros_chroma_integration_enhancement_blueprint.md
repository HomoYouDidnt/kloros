# KLoROS × Chroma: Integration & Enhancement Blueprint

> Goal: Add a semantic memory substrate (ChromaDB) to KLoROS to enhance RAG, episodic recall, D‑REAM evolution, and cross‑domain retrieval—while keeping a clean migration seam to alternate vector stores.

---

## 0) High‑Level Architecture

**Existing (simplified):**
- STT/ASR → Dialogue Orchestrator → Tools/Agents → Logger → Episodic Store (SQL/Parquet) → Summarizer → RAG (FTS/keywords) → TTS

**With Chroma:**
- **Dual‑write**: Every meaningful artifact (utterance, tool result, doc chunk, candidate) → (a) Episodic store (time series) and (b) **Chroma collection** with embeddings + rich metadata.
- **Retrieval Fusion**: Query planner retrieves from Chroma (semantic) and Episodic (time window), then fuses by *semantic similarity + recency + importance*.
- **D‑REAM Augmentation**: Candidate genomes/telemetry are embedded and stored in a dedicated collection; variation/selection use semantic neighbors/diversity sampling.

```
User ↔ STT → Orchestrator → Tools → Logs
                          ↘ dual-write ↙
                       Episodic DB   ChromaDB
                                   ↑   ↓
                         Retrieval Fusion Layer
                                   ↓
                              LLM Reasoner
```

---

## 1) Collections & Schemas (Chroma)

### 1.1 Collections
- `kloros_dialogue` — user/agent utterances, tool replies
- `kloros_docs` — long‑form docs, configs, READMEs, code chunks
- `kloros_summaries` — session/day/week rollups
- `kloros_dream_candidates` — D‑REAM genomes, manifests, telemetry notes
- `kloros_errors` — stack traces, error analyses, remedies

> You may begin with a single collection `kloros_memory` and branch later; collections are a performance/ops boundary, tags can still differentiate.

### 1.2 Shared metadata fields
```json
{
  "event_id": "evt_2025-10-09T21:04:31Z_8421",
  "type": "dialog|tool|doc|summary|candidate|error",
  "ts_iso": "2025-10-09T21:04:31Z",
  "session_id": "voice_2025-10-09",
  "actor": "user|kloros|system",
  "domain": "cpu|audio|streaming|greenhouse|general",
  "importance": 0.0,
  "tags": ["audio", "pipeline", "bugfix"],
  "source_uri": "kloros://voice/turn_154" ,
  "hash": "sha256:...",
  "embedder": "bge-small-en-v1.5",
  "embedder_ver": "1.5.0",
  "rels": ["evt_...", "doc_..."],
  "run_id": "dream_r317",         
  "gen": 0,                         
  "score": 0.0,                     
  "status": "ok|fail|aborted|best"
}
```

### 1.3 Candidate genome payload (stored as document text)
- **Preferred**: canonical JSON string of genome + salient telemetry + commentary (compact, deterministic key order) → embed.
- Keep raw JSON file in object storage / disk; Chroma stores the *embedded* textual representation + metadata above.

---

## 2) Dual‑Write Ingestion

**Ingest points** (non‑blocking, via async task queue):
1. **Dialogue turn**: user text, assistant reply, tool output (summarized if >2k tokens)
2. **File/doc scan**: chunk (512–1,000 tokens) with `source_uri` and content hash
3. **Session summaries**: rolling hourly/daily/weekly notes
4. **D‑REAM events**: candidate genome, performance notes, errors

**Rules**
- Assign stable `event_id` and store identical IDs in episodic + Chroma.
- Batch upserts (1–5k items) for throughput during bulk indexing.
- Compute SHA256 of raw content; if hash or `embedder_ver` changed → re‑embed/upsert.

---

## 3) Retrieval Fusion (recency × relevance × importance)

**QueryPath:**
1. Generate query embedding (same embedder as corpus).
2. **Chroma query**: `n_results = k * 3` (overfetch).
3. **Episodic window**: select by time/session (e.g., last 48–72h) and any mandatory filters (actor=User, domain=audio).
4. **Score fusion** per item:

```
final = α * semantic_similarity
      + β * recency_boost(ts)
      + γ * importance
```

- `semantic_similarity`: normalized (0..1) from Chroma distances.
- `recency_boost(ts) = exp(-(now - ts) / τ)` with τ ≈ 3–7 days for conversation, 14–45 days for docs.
- `importance`: user/agent‑assigned (pins = 1.0).

**Deduping & hydration**: Return top‑N unique `event_id`s and fetch full text from episodic store; include `source_uri` for chain‑of‑custody.

---

## 4) D‑REAM Integration

**Write‑time:**
- On candidate creation/evaluation:
  - Embed compact genome JSON + commentary
  - `metadata = {run_id, gen, domain, score, status, tags}`
  - Upsert into `kloros_dream_candidates`

**Read‑time (during selection/mutation):**
- Query for: "top semantic neighbors of best candidates but with diverse tags/telemetry"
- Diversity sampling: cluster results (k‑means on vectors or metadata bucketing) and pick across clusters to avoid mode collapse.
- Failure learning: search `status=fail` for recurring patterns (e.g., "CUDA", "sample rate 48kHz") and auto‑generate guardrails.

**Analysis dashboards:**
- Cluster maps (UMAP/t‑SNE offline) to visualize candidate families by generation.
- Reports: conserved genome keys vs score deltas across gens.

---

## 5) Repository Interface (Migration Seam)

Define a thin abstraction so you can swap Chroma ↔ Milvus/Qdrant/Pinecone.

```python
class VectorStore:
    def upsert(self, collection: str, ids: list[str], texts: list[str], metadatas: list[dict], embeddings: list[list[float]]|None=None): ...
    def query(self, collection: str, query_texts: list[str], n_results: int, where: dict|None=None): ...
    def delete(self, collection: str, where: dict|None=None, ids: list[str]|None=None): ...
```

**Adapters**: `ChromaAdapter`, `QdrantAdapter`, `MilvusAdapter` each implement the interface.

- Start with `ChromaAdapter` and keep everything else ignorant of the backend.
- Place adapter behind a DI container or factory keyed by env var.

---

## 6) Embedding Strategy

- **Model**: local BGE-small/large (English); multilingual variant if needed.
- **Chunking**: 512–1,000 tokens, overlap 64–128.
- **Store both** raw chunks and summaries. Tag summaries with `type="summary"` and link via `rels`. Retrieval can prefer summaries first for token budgets.
- **Versioning**: capture `embedder` and `embedder_ver` in metadata. Re‑embed on version changes via a migration job.

---

## 7) Operational Concerns

**Performance**
- Use Chroma persistent mode on fast NVMe; set `hnsw:space = "cosine"`.
- Batch writes; avoid per‑item upserts in tight loops.
- Periodically `vacuum/compact` (per Chroma guidance).

**Observability**
- Log: upsert counts, latency, query hit distributions, fusion weights.
- Add tracing spans around: embedding → upsert → query → fuse.

**Quality Control**
- Golden sets: canned queries with expected hits (IDs). Track recall@k post‑changes.
- False‑positive sampler: randomly inspect low‑score hits included in top‑k.

**Privacy & Security**
- Run Chroma locally (UNIX socket or loopback) unless you need remote.
- If using server mode, require mTLS or Tailscale ACLs; encrypt snapshots.

**Backups**
- Snapshot persist directory (filesystem snapshot) + export metadata tables from episodic DB for rebuilds.
- Rebuild recipe = restore files + re‑embed if embedder changed.

---

## 8) Example Code Snippets

### 8.1 Client & collection
```python
import chromadb
from chromadb.config import Settings

db = chromadb.Client(Settings(persist_directory="/data/chroma"))
mem = db.get_or_create_collection(
    name="kloros_memory",
    metadata={"hnsw:space":"cosine"}
)
```

### 8.2 Dual‑write helper
```python
def index_event(ev, embed_fn):
    vec = embed_fn([ev.text])[0]
    md = {**ev.meta,
          "event_id": ev.id,
          "ts_iso": ev.ts_iso,
          "importance": ev.importance}
    mem.upsert(ids=[ev.id], documents=[ev.text], metadatas=[md], embeddings=[vec])
    episodic_insert(ev)  # your SQL/DuckDB call
```

### 8.3 Retrieval fusion
```python
import math, time

def recency_boost(ts_epoch, now=None, tau_days=5):
    now = now or time.time()
    return math.exp(-(now - ts_epoch) / (tau_days*86400))

def retrieve(query_text, k, embed_fn):
    now = time.time()
    res = mem.query(query_texts=[query_text], n_results=k*3)
    hits = []
    for i in range(len(res["ids"][0])):
        eid = res["ids"][0][i]
        md  = res["metadatas"][0][i]
        dist = res.get("distances", [[1]])[0][i]
        sem  = 1.0 - dist
        rec  = recency_boost(ts_to_epoch(md["ts_iso"]))
        imp  = float(md.get("importance", 0.0))
        final = 0.6*sem + 0.25*rec + 0.15*imp
        hits.append((final, eid))
    hits.sort(reverse=True)
    ids = dedupe_take([eid for _,eid in hits], k)
    return episodic_hydrate(ids)
```

### 8.4 D‑REAM candidate indexing & diversity sampling (sketch)
```python
def index_candidate(cand, embed_fn):
    text = canonicalize_genome(cand.genome, cand.telemetry, cand.notes)
    vec = embed_fn([text])[0]
    md = {
      "event_id": cand.id,
      "run_id": cand.run_id,
      "gen": cand.gen,
      "domain": cand.domain,
      "score": cand.score,
      "status": cand.status,
      "tags": cand.tags,
      "ts_iso": cand.ts_iso
    }
    db.get_or_create_collection("kloros_dream_candidates").upsert(
        ids=[cand.id], documents=[text], metadatas=[md], embeddings=[vec]
    )

def sample_diverse_neighbors(seed_query, k):
    res = db.get_collection("kloros_dream_candidates").query(
        query_texts=[seed_query], n_results=k*5
    )
    # run a quick k-means or metadata bucketing to pick diverse k
    return pick_across_clusters(res, k)
```

---

## 9) Rollout Plan

1. **Phase A (1–2 days)**: Stand up Chroma locally; implement adapter + dual‑write for dialogue turns only; basic retrieval fusion.
2. **Phase B**: Add docs/code chunk indexing; add daily/weekly summaries; plug retrieval fusion into RAG.
3. **Phase C**: Index D‑REAM candidates; add diversity sampling in selection; create failure‑pattern queries.
4. **Phase D**: Golden set tests, dashboards, and decay policies (re‑embed/purge strategy).

---

## 10) Success Criteria

- RAG answer quality: +X% top‑k precision on golden queries.
- Conversation continuity: reduced “lost context” events per 100 turns.
- D‑REAM: higher best‑of‑gen scores and faster convergence; fewer repeated failure modes.
- Ops: stable p95 latency < 50ms for Chroma queries on N≈1–5M vectors (local NVMe).

---

## 11) Notes & Options

- Start with **one collection** and rely on tags until scale demands separation.
- Keep **embedder pinning** and record versions for deterministic rebuilds.
- Maintain a **cold storage** of raw artifacts (files/JSON) separate from Chroma so re‑indexing is easy.
- If you later need multi‑node/HA, the adapter enables drop‑in migration to Qdrant/Milvus/Pinecone.

