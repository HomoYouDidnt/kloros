# Accuracy Stack

Pipeline: **RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → CoVe Verify**.
Each module is feature-flagged via `config/accuracy.yml`. Keep changes minimal and reversible.
