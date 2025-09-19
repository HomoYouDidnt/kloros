# PLAN (bootstrap snapshot) — 2025-09-19
## Objectives (current cycle)
- Ship accuracy stack quickstart (Phases 0–4) ✅
- Stabilize CI smoke eval ✅
- Next: broaden CI analyzers and enrich accuracy config

## Module boundaries (edit-only for this cycle)
- Orchestrator: kloROS_accuracy_stack/pipeline/qa.py
- Retrieval: kloROS_accuracy_stack/retrieval/*
- Decoding: kloROS_accuracy_stack/decoding/{sled_decoding.py,cisc.py}
- Verify: kloROS_accuracy_stack/verify/cove.py
- Config: kloROS_accuracy_stack/config/{accuracy.yml,accuracy_ci.yml}

## Active task (T-###)
- Title: Capture PLAN + set next-phase TODOs
- Done when: PLAN.md exists; TODO.md has Master-phase tasks; CI passes

## Known gaps to schedule next
- CI analyzers: shellcheck, osv-scanner, npm audit, madge, jscpd, ts-prune
- accuracy.yml: dual embedder + multi-provider rerank + fallbacks
- Decoding: add top-k/nucleus modes
- RZERO: scripts/rzero_run.py + wiring + docs

## Decision log (concise)
- Kept quickstart Python-first; non-Python analyzers deferred to Master phase.
