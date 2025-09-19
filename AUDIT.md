# Repository Audit

## Summary
| Severity | Files | Tool | Recommended fix | Sources (accessed 2025-09-19) |
| --- | --- | --- | --- | --- |
| Resolved | src/rag.py | bandit 1.8.6 / semgrep 1.137.0 | Completed Pickle loaders removed; `_load_embeddings` now enforces npy/npz/json inputs with `allow_pickle=False`, metadata rejects pickle formats. | [numpy.load allow_pickle](https://numpy.org/doc/stable/reference/generated/numpy.load.html), [Bandit B301/B403](https://bandit.readthedocs.io/en/1.8.6/blacklists/), [Semgrep rule](https://semgrep.dev/r/python.lang.security.deserialization.pickle.avoid-pickle) |
| Medium | tests/test_export.py etc. | pytest 8.4.2 | Provide optional clip_scout stubs or document Node build dependency; add CI job to install/skip deterministically. | clip_scout test failures (local pytest run, 2025-09-19) |
| Medium | requirements.txt / pyproject.toml | pip list --outdated | Refresh numpy (2.3.2->2.3.3) and pycparser (2.22->2.23) before release; rerun regression audio pipeline after upgrade. | [NumPy releases](https://numpy.org/devdocs/release/2.3.0-notes.html), [pycparser releases](https://pypi.org/project/pycparser/2.23/) |
| Medium | src/kloros_voice.py | mypy 1.18.2 / vulture 2.14 | Tighten RAG lifecycle: add explicit doctor check, ensure `self.rag` loaded before use, prune unused helpers (`vosk_rec` slots). | Internal analysis; mypy+vulture runs (2025-09-19) |
| Low | repo root | pre-commit plan | Adopt new `.pre-commit-config.yaml`, `.editorconfig`, and CI workflow to enforce lint/type/audit checks. | [pre-commit docs](https://pre-commit.com/), [GitHub Actions workflow syntax](https://docs.github.com/actions) |

## Dependency Report (Python)
- Runtime stack pinned via `pyproject.toml` and `requirements.txt`; now share `requires-python = ">=3.10"` to match numpy 2.x floor.
- Outdated direct deps: `numpy 2.3.2 -> 2.3.3` (2025-09-17 release), `pycparser 2.22 -> 2.23` (2025-02-18). Tools behind latest: `pip-audit 2.9.0` (2025-04-07), `bandit 1.8.6` (2025-07-06), `semgrep 1.137.0` (2025-09-18).
- `pip-audit --format json` and `osv-scanner --lockfile requirements.txt` returned no known CVEs.
- `pipdeptree --warn silence` highlights editable package metadata duplication; keep `pip install -e .` or consider trimming stale `src/kloros.egg-info` before packaging.
- Licenses (`pip-licenses --format json`) remain MIT/BSD-compatible; rerun before distribution.

## Cross-Module Risks
- **Audio loop call map**: `KLoROS.chat()` -> `requests.post` (Ollama) and optionally `KLoROS.answer_with_rag()` -> `RAG.answer()` -> `requests.post`. Missing Ollama raises string error; add retry/backoff and distinguish HTTP vs connection failures.
- **RAG ingestion**: `_load_embeddings/_load_metadata` now refuse pickle input and only accept npy/npz/json/csv/parquet, but still rely on local files being trustworthy. Add hash/signature checks for `rag_data` before loading in production.
- **Wake/stt pipeline**: `KLoROS.audio_callback()` depends on `self.vosk_rec` reinitialised in `_ensure_vosk` else branch; guard before use to avoid AttributeError when model missing.
- **Tests vs. external services**: Seven pytest modules now skip when `clip_scout` absent. Document Node/ffmpeg expectations and consider smoke stubs to keep regression coverage meaningful.
- **Packaging**: Added `src/__init__.py` to stabilise namespace; ensure importers transition to `from kloros import ...` long-term to avoid `sys.path` patching.

## Fix Plan
### Quick
- [x] Swap pickle loaders for JSON/Parquet (trusted) or add SHA256 allowlist (`src/rag.py`).
- [ ] Add `ffmpeg`/`node` detection to `scripts/doctor.sh` exit codes; document in README.
- [ ] Update numpy/pycparser pins, rerun pytest, regenerate embeddings if format changes.

### Medium
- [ ] Introduce `kloros/rag_store.py` wrapper with signature validation and safe deserialization.
- [ ] Provide lightweight `clip_scout` stub package for CI or move tests behind feature flag.
- [ ] Add retry/backoff and structured logging around Ollama `requests.post` calls.

### Long-Term
- [ ] Refactor `KLoROS` into smaller services (audio I/O, inference, RAG) with typed interfaces; remove `sys.path` hacking.
- [ ] Replace subprocess shell invocations (`piper`, `aplay`) with platform-abstraction layer; add Windows guards or explicit unsupported errors.
- [ ] Generate SBOM (syft/grype or osv-scanner CI job) for release artifacts.

## Verification Logs
- `ruff --version` -> 0.13.1 (PyPI 2025-09-18T19:52:44Z).
- `bandit --version` -> 1.8.6 (PyPI 2025-07-06T03:10:50Z).
- `pip-audit --version` -> 2.9.0 (PyPI 2025-04-07T16:45:23Z).
- `semgrep --version` -> 1.137.0 (PyPI 2025-09-18T23:45:50Z).
- `vulture --version` -> 2.14 (PyPI 2024-12-08T17:39:43Z).
- `pycln --version` -> 2.5.0 (PyPI 2025-01-06T19:21:36Z).
- `pipdeptree --version` -> 2.28.0 (PyPI 2025-07-20T19:47:26Z).
- `pip-licenses --version` -> 5.0.0 (PyPI 2024-07-23T10:48:29Z).
- `mypy --version` -> 1.18.2 (PyPI 2025-09-19T00:11:10Z).
- `osv-scanner --version` -> 2.2.2 (GitHub release 2025-08-27T03:34:15Z).
- `pytest -q` -> `3 passed, 6 skipped` (clip_scout-dependent suites skipped intentionally).

## KLoROS Environment Report
- **OS/Kernel**: `uname`, `cat /etc/os-release`, `systemctl`, `ss`, `sed`, `lscpu` unavailable in capture host (Windows). Debian 13 target must confirm via live doctor script.
- **GPU**: `nvidia-smi` present (driver 581.29, WDDM, CUDA 13.0). `nvcc`/`ldconfig` checks missing; validate CUDA toolkit on Debian host.
- **Toolchains**: `python3` missing on path; local venv reports 3.13.7 (confirm `python3.12` on deployment). Node/pnpm/yarn absent. `ffmpeg`/`convert` not installed.
- **Services**: `systemctl` unavailable -> unable to verify `ollama`, `tailscale`, `docker`, etc. Plan to re-run `scripts/doctor.sh` on actual Debian host.
- **Ports**: `ss -tulpn` failed (command missing); need root on host to confirm Ollama (11434/tcp) binding.

### Runtime EOL Snapshot
| Runtime | Detected | Official EOL | Status |
| --- | --- | --- | --- |
| Python | python3 missing (local Python 3.13.7) | 3.13 security ends 2029-10 ([schedule](https://devguide.python.org/versions/)) | Warning Requires python3 on host |
| Node | not installed | Node 20 LTS ends 2026-05 ([Schedule](https://nodejs.org/en/about/previous-releases)) | Missing Install Node 20.x |

### Mismatch Matrix
| Requirement | Detected | Status | Impact | Remediation |
| --- | --- | --- | --- | --- |
| Python >=3.10 (pyproject) | `python3` missing; local venv 3.13.7 | Warning | Systemd services/scripts will fail on host | Install python3.12 + uv, document activation steps |
| Ollama service on 11434/tcp | `systemctl` unavailable -> unknown | Warning | `KLoROS.chat` blocks without LLM | Verify `ollama.service` active on Debian; add doctor check |
| ffmpeg CLI for review/export | Command missing | Missing | `clip_scout` exports, `test_components` degrade | Install `ffmpeg` package; add check in `doctor.sh` |
| Node.js >=20 for clip_scout | not installed | Missing | Tests & review pipeline rely on CLI bundler | Ship `.nvmrc`=20, install Node 20.x |
| CUDA toolkit for faiss (optional) | `nvcc`/`ldconfig` not run | Warning | GPU-accelerated retrieval may be disabled | Confirm toolkit on Debian host; update docs |

### Environment Action List
1. Install python3.12, ffmpeg, and Node 20.x on Debian host; rerun `scripts/doctor.sh`.
2. Enable/verify `ollama.service`, `tailscaled.service`, and GPU persistence mode via `nvidia-persistenced`.
3. Restrict Ollama bind to loopback (`ListenAddress=127.0.0.1`) and confirm firewall rules.
4. Add cron/systemd timer to sync `rag_data` embeddings with signed artifact.

---

See `ENVIRONMENT.md` for raw command output (captured 2025-09-18).
