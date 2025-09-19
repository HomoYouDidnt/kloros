# KLoROS Accuracy Stack — Starter Suite

This repository add-on provides a **toggleable, reversible, CI-verified** accuracy stack for KLoROS:
**RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → CoVe Verify**, plus environment checks and a sandboxed **RZERO** self-improvement loop.

**Start here:**
1. Create/activate your Python env (uv/poetry/pip — use your repo's choice).
2. Install dev deps (see `requirements-dev.txt` if you want a quick start).
3. Run the golden e2e test on the mini fixture corpus.
4. Use `bin/answer --question "..." --config config/accuracy.yml --trace out/trace.json --mode e2e`.

See `docs/accuracy_stack.md` for the pipeline and toggles.
