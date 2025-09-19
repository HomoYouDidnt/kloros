# KLoROS — Master Integration Instructions for Codex

This is the **single, comprehensive brief** for Codex. It unifies repo audit, environment checks, accuracy stack integration, extra bolt‑ons, and the RZERO hybrid self‑improvement loop. All modules must be toggleable, reversible, and verified via CI + eval.

---

## 0) Global Rules
- **Recency & Verification:** Use only current, verifiable methods and **official sources**. Every non‑trivial recommendation must include 1–2 official links with today’s accessed date in `AUDIT.md`. Record `--version`/`--help` excerpts in `ENVIRONMENT.md`.
- **Respect Existing Ecosystems:** Do not swap package managers/runtimes. Use what repo already uses (uv/poetry/pip, npm/pnpm/yarn).
- **Read‑Only System:** For environment checks, never change host config.
- **Fail Closed:** All new modules must be feature‑flagged and fallback to baseline path if disabled/failing.
- **Security:** Never expose secrets; only report presence + path.

Deliverables:
- `AUDIT.md` — issues, decisions, source links + dates, verification logs.
- `ENVIRONMENT.md` — versions, EOL table, command outputs, mismatch matrix.
- Code/config patches staged with tests + CI + docs.

---

## 1) Repo Audit & Hardening
- **Goals:** detect deprecated deps, conflicts, cross‑file risks, enforce lint/format, add fast CI.
- **Tools:** ruff, black (if used), mypy/pyright, pytest; eslint, prettier, tsc; semgrep, osv‑scanner, pip‑audit, npm audit, jscpd, ts‑prune, pycln, vulture, madge, shellcheck.
- **Formatting:** `.editorconfig` + `pre-commit` hooks.
- **CI:** jobs for lint/type/security/tests; keep runtime <10m.
- **Cross‑module checks:** call graph, mismatches, circulars, env drift.
- **Output:** `AUDIT.md` tables + fix plan.

---

## 2) Environment Add‑On (Debian 13 host)
- Collect OS/hardware (`uname`, `/etc/os-release`, `lscpu`, `nvidia-smi`), runtimes (`python3 --version`, node, uv/pip, ffmpeg, convert), services (systemd list, grep ollama/tailscale/etc.), networking (`ss -tulpn`), upgradable packages, containers (docker/podman).
- Parse repo manifests; build **Mismatch Matrix**.
- **Output:** append report to `AUDIT.md`; create `ENVIRONMENT.md` with trimmed logs + EOL table.

---

## 3) Accuracy Stack Integration
Pipeline: **RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → Verify (CoVe)**.

### Components
1. **Embedder:** FlagEmbedding `bge-m3`; fallback dual index.
2. **Reranker:** `bge-reranker-v2-m3` + Cohere provider.
3. **CRAG:** retrieval‑quality scoring + corrective loop.
4. **GraphRAG:** nightly graph build; query‑time synopsis.
5. **Decoding:**
   - **SLED:** Self‑Logits Evolution Decoding with α, layer window, top‑k clamp.
   - **CISC:** Confidence‑Informed Self‑Consistency (k=3–7).
6. **Verification:** **CoVe** (Chain‑of‑Verification); may abstain.
7. **Env awareness:** use mismatch matrix; repo‑side fixes.

### Config (`config/accuracy.yml`)
```yaml
retrieval:
  embedder: ["bge-m3", "baseline"]
  top_k: 30
  fallback_on_low_quality: true
rerank:
  provider: ["bge-m3", "cohere"]
  keep_top_k: 5
crag:
  enabled: true
  quality_threshold: 0.62
  actions: ["expand_query","multi_hop","web_fallback"]
graphrag:
  enabled: true
  nightly_build: "0 3 * * *"
  max_hops: 2
decoding:
  mode: ["greedy","topk","nucleus","sled","cisc"]
  sled:
    alpha: 0.2
    layer_frac_range: [0.3,0.7]
    keep_final_topk_union: 100
  cisc:
    samples: 5
verification:
  cove_enabled: true
  abstain_threshold: 0.55
```

### Modules
- `retrieval/embedder.py`, `reranker.py`, `crag.py`, `graphrag.py`
- `decoding/sled_decoding.py`, `cisc.py`
- `verify/cove.py`
- `pipeline/qa.py` (orchestrator)
- `bin/answer` CLI entrypoint

### Tests & Eval
- Unit + golden e2e (small fixture corpus).
- `scripts/eval_accuracy.py` comparing all toggles; output report + CSV.

### CI
- Lint/type/security/tests/eval‑smoke.

### Docs
- `docs/accuracy_stack.md` (diagram).
- `docs/sled.md`, `docs/cove.md`, `docs/graphrag.md`.

---

## 4) Extra Bolt‑Ons
- **RAPTOR hierarchical chunking** (retrieve leaves + ancestors).
- **Prompt compression (LLMLingua‑2)**.
- **Speculative decoding** path for speed.
- **Ragas + TruLens** for metrics + tracking.
- **OpenTelemetry** spans for timings/errors.
- **Guardrails** for schema‑validated outputs.
- **DSPy** modules for structured LLM programming.

---

## 5) RZERO Self‑Improvement (Sandboxed)
- **Purpose:** propose → evaluate → gate → stage → optional promote config/prompt/knob tweaks. No code rewrites.

### Config (`config/accuracy.yml`)
```yaml
self_improve:
  rzero_enabled: true
  mode: ["offline","shadow","canary"]
  max_parallel_candidates: 4
  win_criteria:
    em_delta_min: +2.0
    faithfulness_min: 0.93
    latency_delta_max_ms: 60
    abstain_rate_max: 8.0
    no_regressions_on: ["math","procedural","multi-hop"]
  knobs:
    sled_alpha: [0.1,0.2,0.3]
    cisc_k: [3,5,7]
    retrieval_topk: [20,30,40]
    rerank_keep: [3,5,7]
    crag_threshold: [0.55,0.62,0.7]
    graphrag_hops: [1,2]
    compress_budget: ["auto","-20%","-35%"]
  datasets:
    train: data/eval/train_qa.jsonl
    heldout: data/eval/heldout_qa.jsonl
    canary: data/eval/canary_qa.jsonl
  safety:
    max_prompt_delta_tokens: 120
    forbid_patterns: ["disable_verification","skip_citations"]
    require_citations: true
  promotion:
    require_two_pass: true
    human_approval_required: true
```

### Files
- `rzero/proposer.py`, `evaluator.py`, `gatekeeper.py`
- `scripts/rzero_run.py`
- `docs/rzero.md`

### CLI
```
python scripts/rzero_run.py propose --n 6 --seed 42
python scripts/rzero_run.py evaluate --candidates candidates/*.yml --dataset heldout
python scripts/rzero_run.py gatekeep --reports out/rzero/*/report.json --stage staged/
python scripts/rzero_run.py shadow --profile staged/profile-YYYYMMDD.yml --budget 100
python scripts/rzero_run.py canary --profile staged/profile-YYYYMMDD.yml --pct 5
```

### Safety Interlocks
- Abstention & verification never off.
- Schema/guardrail violations fail.
- Canary watchdog auto‑rollback.

---

## 6) Orchestrator Sketch
```python
def answer(q: str, cfg):
    trace = {}
    hits = retrieve(q, cfg, trace)
    reranked = rerank(q, hits, cfg, trace)
    if need_correction(reranked, cfg):
        reranked = corrective_loop(q, cfg, trace)
    synopsis = None
    if cfg.graphrag.enabled:
        subgraph, synopsis = graphrag_expand(q, reranked, cfg, trace)
    context = build_context(reranked, synopsis)
    draft, meta = decode(q, context, cfg, trace)
    final = cove_verify(q, draft, context, cfg, trace)
    return final, trace
```

---

## 7) Execution Flow
1. **Print PLAN**: detect ecosystems; list tools, versions, doc links.
2. **Repo audit** batch → `AUDIT.md`.
3. **Implement modules** incrementally; unit test; log results.
4. **Wire orchestrator** + CLI; add docs.
5. **Env phase**: run probes; build mismatch matrix → `AUDIT.md`.
6. **Eval**: run `scripts/eval_accuracy.py`; produce deltas.
7. **CI**: lint/type/security/tests/eval‑smoke.
8. **RZERO (offline)**: enable proposer/evaluator/gatekeeper only; stage profiles; no auto‑promotion without human signoff.

