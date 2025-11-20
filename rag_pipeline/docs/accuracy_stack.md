# Accuracy Stack

Pipeline: **RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → CoVe Verify**.
Each module is feature-flagged via `config/accuracy.yml`. Keep changes minimal and reversible.

## Retrieval

- `retrieval.provider`: `mock` (fixture corpus) or `faiss` by default.
- `retrieval.embedders.primary/baseline`: two sentence-transformer configs, each with
  `name` (HF identifier) and optional `path` for local checkpoints.
- `retrieval.fallback_on_low_quality`: when `true`, CRAG is allowed to switch to the
  baseline embedder if the primary path under-performs.
- Trace metadata records `active_embedder` and whether the fallback is armed.

## Rerank

- `rerank.rerankers`: ordered list of cross encoders to try. We ship with
  `bge-reranker-v2-m3` followed by `mock`, so failures cascade gracefully.
- `rerank.model_name` / `rerank.model_path`: still used when the chosen provider maps to
  a sentence-transformer cross encoder (e.g. BGE).

## GraphRAG

- `graphrag.provider`: `mock` or `local` (writes `graph.json`).
- `graphrag.nightly_build`: flag surfaced in traces for external schedulers; no-op in the
  mock implementation but kept in the config for compatibility.

## Decoding

- `decoding.mode` / `decoding.active`: now support `greedy`, `sled`, `cisc`, `topk`, and
  `nucleus`.
- `decoding.topk.k`: beam width for the sampling-free top-k snippet generator.
- `decoding.nucleus.p` + `decoding.nucleus.max_tokens`: nucleus sampling parameters.
- Existing `sled` and `cisc` blocks retain their alpha/sample knobs.

## Verification & RZERO

- `verification.provider`: `mock` or `local` (CoVe-style citation verifier). The local
  path abstains when citations lack `[DOC:id]` markers.
- `self_improve.rzero_enabled`: gated off by default; set `true` to enable the
  `scripts/rzero_run.py` flow.
- `scripts/rzero_run.py --dry-run` summaries the pipeline; `propose`, `evaluate`, and
  `gatekeep` commands use the existing `rzero/` stubs.

Mock providers rely on the deterministic fixture corpus under `fixtures/mini/`, keeping
CI runtimes under a minute. Real integrations simply swap provider values while the
interfaces remain stable.

## CI / audit

- `.github/workflows/ci.yml` runs linting, typing, security, unit tests, and the accuracy
  smoke suite on every push/PR.
- `.github/workflows/audit.yml` houses slower analyzers (`shellcheck`, `osv-scanner`,
  `npm audit --audit-level=high`, `madge`, `jscpd`, `ts-prune`). Execute it on demand when
  preparing releases or touching cross-language components.
