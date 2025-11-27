# Agentic Parallelism Patterns - Design Document

**Date**: 2025-11-24
**Status**: Approved, Ready for Implementation
**Scope**: Foundation layer implementations (core algorithms, integration points defined)

---

## Overview

Five parallelism patterns to bring KLoROS from 10/14 to 14/14 on the Agentic Parallelism checklist.

| # | Pattern | Approach | File |
|---|---------|----------|------|
| 4 | Speculative Execution | Background prefetch | `speculative_executor.py` |
| 9 | Redundant Execution | Retry + fallback chain | `redundant_executor.py` |
| 10 | Parallel Query Expansion | Hybrid (rule + LLM) | `query_expander.py` |
| 11 | Sharded Retrieval | Domain-based routing | `sharded_retriever.py` |
| 14 | Multi-Hop Retrieval | Query decomposition | `multihop_retriever.py` |

---

## Pattern 1: Parallel Query Expansion

**File**: `/home/kloros/src/rag/query_expander.py`

### Architecture
```
QueryExpander
├── RuleBasedExpander (fast, always runs)
│   ├── synonym_expansion() - WordNet/custom synonyms
│   ├── stem_variations() - porter stemmer variants
│   └── entity_expansion() - known entity aliases
└── LLMExpander (optional, complexity threshold)
    └── generate_variants() - 3-5 semantic variants
```

### Flow
1. Input query arrives
2. Rule-based expander generates 2-4 variants (< 10ms)
3. If query complexity score > threshold OR rule expansion yields < 2 variants:
   - LLM generates 3 additional semantic variants (~200ms)
4. Deduplicate expanded queries
5. Return list of 3-6 queries for parallel retrieval

### Integration
- `HybridRetriever.retrieve()` calls `QueryExpander.expand()` first
- Retrieves for each expanded query in parallel using `ThreadPoolExecutor`
- Merges results with RRF

### Complexity Scoring
- Query length > 10 words → triggers LLM expansion
- Contains "how", "why", "compare", "difference" → triggers LLM expansion

---

## Pattern 2: Sharded Retrieval (Domain-Based)

**File**: `/home/kloros/src/rag/sharded_retriever.py`

### Architecture
```
ShardedRetriever
├── shards: Dict[str, HybridRetriever]
│   ├── "general" → general knowledge (docs, external)
│   ├── "self" → system knowledge (config, architecture)
│   ├── "code" → codebase index
│   ├── "memory" → conversation/episodic memory
│   └── "procedures" → procedural knowledge (how-tos)
├── shard_router: ShardRouter
│   └── route_to_shards(query) → List[str]
└── parallel_retrieve(query, shards) → merged results
```

### Flow
1. Query arrives
2. `ShardRouter.route_to_shards()` determines relevant shards (1-3 typically)
3. `ThreadPoolExecutor` queries all relevant shards in parallel
4. Results merged via RRF across shards
5. Final reranking on merged results

### Shard Routing Heuristics
- Contains "code", "function", "class", "import" → `code` shard
- Contains "config", "setting", "kloros" → `self` shard
- Contains "remember", "last time", "conversation" → `memory` shard
- Default → `general` shard (always included as fallback)

### Integration
- Replaces `RAGRouter` or wraps it as the new top-level retriever

---

## Pattern 3: Redundant Execution (Retry + Fallback)

**File**: `/home/kloros/src/kloros/orchestration/redundant_executor.py`

### Architecture
```
RedundantExecutor
├── primary_executor: Callable
├── fallback_chain: List[Callable]
├── retry_config: RetryConfig
│   ├── max_retries: int = 2
│   ├── backoff_ms: int = 100
│   └── timeout_ms: int = 30000
└── execute_with_redundancy(task) → Result
```

### Flow
1. Execute with primary executor
2. On failure: retry up to `max_retries` with exponential backoff
3. If still failing: walk `fallback_chain` in order
4. Return first success OR raise after all options exhausted
5. Log which executor succeeded (for fitness tracking)

### Fallback Chain Examples
- LLM operations: `ollama_32b` → `ollama_8b` → `cached_response` → `graceful_error`
- RAG operations: `hybrid_retriever` → `vector_only` → `bm25_only` → `empty_context`
- External APIs: `primary_endpoint` → `backup_endpoint` → `cached_data`

### Integration Points
- Wrap `InvestigationConsumer` LLM calls
- Wrap `TournamentConsumer` evaluation calls
- Wrap external API calls in tools

### Metrics
- `redundant_execution_primary_success`
- `redundant_execution_fallback_used`
- `redundant_execution_total_failure`

---

## Pattern 4: Speculative Execution (Background Prefetch)

**File**: `/home/kloros/src/kloros/orchestration/speculative_executor.py`

### Architecture
```
SpeculativeExecutor
├── prefetch_cache: Dict[str, PrefetchResult]
├── pending_prefetches: Dict[str, Future]
├── prediction_model: NextActionPredictor
│   └── predict_next(context) → List[(action, confidence)]
├── confidence_threshold: float = 0.7
└── executor: ThreadPoolExecutor(max_workers=2)
```

### Flow
1. After completing action A, call `predict_next(context)`
2. For predictions with confidence > threshold:
   - Spawn background thread to pre-execute
   - Store Future in `pending_prefetches`
3. When action B is requested:
   - Check `prefetch_cache` for hit → return immediately
   - Check `pending_prefetches` for in-progress → await Future
   - Miss → execute normally
4. Cache eviction: LRU with 60-second TTL

### Prediction Model (Heuristic v1)
- After `curiosity_question` → predict `investigation` (confidence 0.9)
- After `code_search` → predict `file_read` for top result (confidence 0.8)
- After `error_detection` → predict `stack_trace_analysis` (confidence 0.85)

### Integration
- Hook into `CuriosityProcessor`
- When question is queued, spawn speculative investigation

### Metrics
- `speculative_hit_rate`
- `speculative_waste_rate` (prefetched but unused)

---

## Pattern 5: Multi-Hop Retrieval (Query Decomposition)

**File**: `/home/kloros/src/rag/multihop_retriever.py`

### Architecture
```
MultiHopRetriever
├── decomposer: QueryDecomposer
│   └── decompose(query) → List[SubQuery]
├── base_retriever: ShardedRetriever
├── synthesizer: ResultSynthesizer
│   └── synthesize(query, sub_results) → final_context
└── executor: ThreadPoolExecutor(max_workers=4)
```

### Flow
1. Complex query arrives (detected by length/complexity or explicit flag)
2. `QueryDecomposer.decompose()` breaks into 2-5 sub-questions
   - Uses LLM: "Break this question into independent sub-questions"
3. All sub-queries execute in parallel via `ThreadPoolExecutor`
4. Each sub-query goes through full pipeline (expansion → sharded retrieval → rerank)
5. `ResultSynthesizer.synthesize()` merges sub-results:
   - Deduplicate overlapping chunks
   - Re-score based on coverage of original query
   - Return top-k unified context

### Decomposition Example
- Input: "How does KLoROS handle errors and what logging system does it use?"
- Sub-queries:
  1. "How does KLoROS handle errors?"
  2. "What logging system does KLoROS use?"
  3. "KLoROS error handling architecture"

### Integration
- Called by `RAGRouter` when query complexity exceeds threshold
- Or explicitly via `multihop=True` parameter

---

## Implementation Order

1. **Query Expansion** - Foundation for all retrieval improvements
2. **Sharded Retrieval** - Builds on expansion, enables parallel domain search
3. **Multi-Hop Retrieval** - Uses sharded retrieval for sub-queries
4. **Redundant Execution** - Independent, can be done in parallel
5. **Speculative Execution** - Independent, can be done in parallel

---

## Success Criteria

After implementation, KLoROS should score **14/14** on the Agentic Parallelism checklist:

| # | Pattern | Target Status |
|---|---------|---------------|
| 4 | Speculative Execution | ✅ FULL |
| 9 | Redundant Execution | ✅ FULL |
| 10 | Parallel Query Expansion | ✅ FULL |
| 11 | Sharded Retrieval | ✅ FULL |
| 14 | Multi-Hop Retrieval | ✅ FULL |

---

**Document Version**: 1.0
**Approved**: 2025-11-24
