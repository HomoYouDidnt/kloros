# Accuracy Stack

Pipeline: **RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → CoVe Verify**.
Each module is feature-flagged via `config/accuracy.yml`. Keep changes minimal and reversible.

## Providers
- `retrieval.provider`: mock | faiss | elastic … (default mock)
- `rerank.provider`: mock | bge-m3 | cohere …
- `graphrag.provider`: mock | <graph-service>
- `decoding.active`: greedy | sled | cisc
- `verification.provider`: mock | cove
- `self_improve.rzero_enabled`: default `false` (enable via real evaluators later)

Mock providers use the tiny fixture corpus under `fixtures/mini/` and are deterministic so CI stays fast (<60s).
Switching to real backends only requires swapping the provider values; the interfaces remain unchanged.
