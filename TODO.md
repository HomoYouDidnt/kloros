# Accuracy Stack TODO

- [x] BGE/FAISS retrieval adapter + index builder script
- [x] BGE reranker cross-encoder integration
- [x] Local citation verifier with `[DOC:id]` markers
- [x] GraphRAG local graph builder + synopsis
- [x] Decoding selection with safe SLED/CISC fallback
- [x] Tiny evaluation harness + expanded fixtures
- [x] CI/docs updates (deps, eval step, docs refresh)

## Next Master-Phase Tasks

- [ ] Broaden CI analyzers (shellcheck, osv-scanner, npm audit, madge, jscpd, ts-prune)
- [ ] Expand `accuracy.yml` with dual embedders, multi-provider rerank, and fallbacks
- [ ] Add top-k and nucleus decoding modes alongside SLED/CISC
- [ ] Implement RZERO runner (`scripts/rzero_run.py`) plus proposer/evaluator wiring and docs updates
