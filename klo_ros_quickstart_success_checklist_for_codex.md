# KLoROS — Quickstart & Success Checklist for Codex

A slim, execution-first brief to maximize success and minimize scope creep. Use this BEFORE the full Master Integration plan. Keep all changes minimal, reversible, and behind flags.

---

## Phase 0 — Sanity & Plan (15–20 min)
**Goal:** Detect stack, print PLAN, and create branches.

1. Detect ecosystems and versions (Python, Node/PM, CUDA, FFmpeg). Save to `ENVIRONMENT.md`.
2. Print a one-screen PLAN listing: tools you will run, configs you will add, and the exact commands.
3. Create feature branch: `feat/accuracy-stack-bootstrap`.

**Checkpoint (must produce):** `ENVIRONMENT.md` with versions + PLAN snippet.

---

## Phase 1 — Minimal Audit & CI Skeleton (≤30 min)
**Goal:** Add only the fastest health checks and make CI green.

1. Add `.editorconfig` + `pre-commit` with ruff/ruff-format (or black if repo uses it), eslint/prettier, yamllint, shellcheck.
2. Add `.github/workflows/ci.yml` with jobs:
   - Python: ruff, format check, mypy/pyright, `pytest -q` (skip heavy tests).
   - Node: eslint, prettier `--check`, `tsc --noEmit`.
   - Security: `semgrep --config auto` (fast rules), `pip-audit` / `npm audit --audit-level=moderate`.
3. Run locally, paste short logs to `AUDIT.md`.

**Checkpoint:** CI passes on branch (or single actionable TODO if blocked).

---

## Phase 2 — Wire the Core Pipeline (Happy Path Only)
**Goal:** End-to-end answer path working on a tiny fixture corpus.

1. Create config file `config/accuracy.yml` with the baseline schema (retrieval, rerank, crag, graphrag, decoding, verification). Use defaults from the Master doc.
2. Create modules (stubs OK if fast):
   - `retrieval/embedder.py` (bge-m3 + baseline), `retrieval/reranker.py` (local bge + provider interface), `retrieval/crag.py` (score + branch), `retrieval/graphrag.py` (stub builder + query synopsis).
   - `decoding/sled_decoding.py` (SLED class with alpha, layer window, clamp), `decoding/cisc.py` (k samples + weighted vote).
   - `verify/cove.py` (plan → verify against provided spans → abstain on fail).
   - `pipeline/qa.py` (orchestrator) and `bin/answer` CLI.
3. Add tiny fixture under `fixtures/mini/` (10–20 docs, 10–20 QA pairs) with expected answers + citations.
4. Implement a **golden e2e test** using the fixture.

**Checkpoint:** `bin/answer --question '…' --config config/accuracy.yml` returns an answer with citations on the fixture corpus; golden e2e test passes.

---

## Phase 3 — Add Accuracy Toggles Incrementally
**Goal:** Enable features one by one, proving they work.

Order of toggles:
1) **Reranker** → keep top-5.
2) **CRAG** → threshold 0.62; allow expand/decompose.
3) **GraphRAG** → synopsis appended to context; tag provenance.
4) **SLED** → `alpha=0.2`, mid-layer 30–70%, clamp union top-k.
5) **CISC** → `k=5` with confidence-weighted vote.
6) **CoVe** → must cite RAG spans or abstain.

After each toggle:
- Run unit tests for that module.
- Run golden e2e.
- Append a 3–5 line note + any `--version` proof links to `AUDIT.md`.

**Checkpoint:** All toggles work on fixture; failure causes automatic fallback.

---

## Phase 4 — Minimal Eval & Report
**Goal:** Produce small but honest metrics.

1. Add `scripts/eval_accuracy.py` to compare: baseline → +rerank → +CRAG → +GraphRAG → +SLED → +CISC → +CoVe on 100–300 QA items.
2. Output `out/eval_report.md` + CSV; include EM/F1/faithfulness/latency.

**Checkpoint:** Eval report artifact uploaded in CI (smoke: 25 items if runtime is tight).

---

## Phase 5 — Environment Mismatch Matrix (Read‑Only)
**Goal:** Catch “works on my machine” issues.

1. Run read-only probes (OS, runtimes, GPU, services, ports).
2. Parse repo manifests and build **Mismatch Matrix** with repo‑first remedies (e.g., add `.nvmrc`).
3. Append top 10 mismatches with one‑liners to `AUDIT.md`.

**Checkpoint:** `AUDIT.md` includes Environment Report + one-line fixes.

---

## Phase 6 — Optional Bolt‑Ons (Guarded by Flags)
- **RAPTOR** tree builder + retrieval of leaves+ancestors.
- **LLMLingua‑2** compression when near token budget.
- **Speculative decoding** mode for speed.
- **Ragas + TruLens** (metrics & tracking).
- **OpenTelemetry** spans (stage timings and errors).
- **Guardrails** schema for structured outputs.
- **DSPy** modules (A/B against prompt code).

**Checkpoint:** Each added behind a flag; golden e2e remains green.

---

## Phase 7 — RZERO (Offline Only at First)
**Goal:** Safe, measurable self‑improvement.

1. Add `rzero/` proposer, evaluator, gatekeeper, `scripts/rzero_run.py`.
2. Configure `self_improve` block in `config/accuracy.yml` (offline mode).
3. Run `propose → evaluate → gatekeep` on held‑out; emit `staged/profile.yml`.

**Checkpoint:** Candidate profile produced; no runtime changes yet.

---

## Success Criteria (Definition of Done)
- CI green (lint/type/security/tests/e2e/eval‑smoke).
- `AUDIT.md` contains: issue tables, source links (with accessed dates), short verification logs, and the Environment Report with Mismatch Matrix.
- `ENVIRONMENT.md` contains tool versions and `--help`/`--version` excerpts.
- `bin/answer` works end‑to‑end on fixture and sample real queries.
- All features are toggleable; baseline path remains stable.

---

## Canonical Commands (Copy/Paste)
```bash
# create venv, install fast dev deps
python -m venv .venv && source .venv/bin/activate || .\.venv\Scripts\Activate.ps1
pip install -U pip
pip install ruff black mypy bandit pip-audit vulture pycln pytest semgrep

# node tools (use repo’s PM)
npm i || pnpm i || yarn
echo "// checks" && npx eslint --version && npx prettier --version

# run fast checks
ruff . && black --check . && mypy . || true
semgrep scan --config auto || true
pip-audit || true
npm audit --audit-level=moderate || true

# golden e2e
pytest -q -k e2e || true

# answer CLI (fixture)
bin/answer --question "What is X?" --config config/accuracy.yml --trace out/trace.json --mode e2e
```

---

## Final Instruction to Codex (paste at the end of your chat)
> **Execute Phases 0–4 exactly in order.** After each phase, pause and summarize: what changed, what passed, and what’s next, with links to files you created. Keep diffs small and reversible. If any step fails, propose two minimal fixes and pick one. Only after Phase 4 passes should you proceed to Phases 5–7.

