# KLoROS System Audit - Quick Reference Index

**Generated:** October 28, 2025
**Version:** 2.0 (Verified)
**Full Report:** `/home/kloros/KLOROS_SYSTEM_AUDIT_COMPREHENSIVE.md`
**Executive Summary:** `/home/kloros/AUDIT_SUMMARY.md`

---

## Quick Navigation

### System Components
- **Voice Loop** → `src/kloros_voice.py` (3,907 lines)
- **D-REAM Evolution** → `src/dream/runner/__main__.py` (575 lines)
- **PHASE Testing** → `src/phase/run_all_domains.py` (156 lines)
- **SPICA Template** → `src/spica/base.py` (309 lines)
- **RAG Pipeline** → `src/simple_rag.py` (if exists)

### Major Subsystems (Verified)

| Subsystem | Purpose | Status | Config |
|-----------|---------|--------|--------|
| D-REAM (Darwinian-RZero Evolution & Anti-collapse Module) | Continuous evolution | ⏸️ Disabled | `src/dream/config/dream.yaml` |
| PHASE (Phased Heuristic Adaptive Scheduling Engine) | Scheduled testing | ⏸️ Scheduled (timer enabled) | `src/phase/configs/*.yaml` |
| SPICA (Self-Progressive Intelligent Cognitive Archetype) | Template foundation | ✅ Active | N/A (code: `src/spica/base.py`) |
| Voice | Hybrid STT/TTS/LLM | ✅ Active | `src/config/kloros.yaml` |
| RAG | Hybrid retrieval | ✅ Active | `src/config/kloros.yaml` |
| Memory | Persistent state | ✅ Active | `~/.kloros/` |

### 11 SPICA Test Domains (Verified)

| # | Domain | File | Lines | Focus |
|---|--------|------|-------|-------|
| 1 | TTS | spica_tts.py | 858 | Synthesis latency, voice quality, throughput |
| 2 | Turn Management | spica_turns.py | 683 | VAD boundaries, echo suppression, barge-in |
| 3 | RAG | spica_rag.py | 520 | Retrieval precision, grounding, relevance |
| 4 | ToolGen | spica_toolgen.py | 449 | Tool synthesis, repair strategies |
| 5 | Conversation | spica_conversation.py | 445 | Intent accuracy, turn latency, context |
| 6 | Code Repair | spica_code_repair.py | 366 | Test pass rate, linting, bug fixes |
| 7 | Planning | spica_planning.py | 351 | Accuracy, latency, token cost |
| 8 | Bug Injector | spica_bug_injector.py | 327 | Fault injection, recovery |
| 9 | System Health | spica_system_health.py | 303 | Memory, CPU, recovery time |
| 10 | MCP | spica_mcp.py | 276 | Tool discovery, routing, compliance |
| 11 | RepairLab | spica_repairlab.py | 187 | Meta-repair patterns |

**Total:** 4,765 lines across 11 domains

---

## System Scale (All Verified)

```bash
# Verified Statistics
Python modules:     529 files
Lines of code:      122,841 lines
Source size:        264M
Runtime state:      453M (.kloros/)
SPICA domains:      11 domains
SPICA instances:    10 snapshots
Epoch logs:         4,466 files
```

---

## Key Files by Type

### Configuration (All Verified)
- **Global:** `src/config/kloros.yaml` ✓
- **D-REAM:** `src/dream/config/dream.yaml` ✓
- **PHASE:** `src/phase/configs/*.yaml` ✓
- **Systemd:** `systemd/*.service`, `systemd/*.timer` ✓

### Source Code (Top 10 by lines)
1. `dream/` - 22,468 lines (D-REAM engine)
2. `phase/` - 8,595 lines (PHASE framework)
3. `tool_synthesis/` - 7,153 lines
4. `idle_reflection/` - 5,033 lines
5. `kloros_voice.py` - 3,907 lines
6. `audio/` - 3,579 lines
7. `reasoning/` - 2,725 lines
8. `registry/` - 2,690 lines
9. `stt/` - 2,206 lines
10. `rag/` - 1,686 lines

### Data Storage (Verified)
- **Evolution:** `/home/kloros/artifacts/dream/` ✓
- **PHASE:** `/home/kloros/src/phase/phase_report.jsonl` ✓
- **SPICA:** `/home/kloros/experiments/spica/instances/` (10 snapshots) ✓
- **Logs:** `/home/kloros/logs/epoch_*.log` (4,466 files) ✓
- **Memory:** `~/.kloros/kloros_memory.db` (may not exist on all nodes)
- **Vectors:** `~/.kloros/chroma_data/` ✓

---

## Architecture Patterns

### 1. Hyperbolic Time Chamber
```
D-REAM (Fast Loop)          PHASE (Slow Loop)
    ↓                            ↓
Minutes per gen    ←sync→    4 hours nightly
Rapid exploration           Statistical rigor
Adaptive timing             Multi-replica tests
    ↓                            ↓
Continuous evolution    Results feed back
```

### 2. Multi-Objective Fitness (6 Dimensions)
```
Performance (0.40) ─┐
Stability (0.20)    ├─→ Weighted Sum → Fitness Score
Drawdown (0.15)     │
Turnover (0.10)     │   Hard Constraints:
Correlation (0.10)  │   • drawdown ≤ 0.6
Risk (0.05) ────────┘   • risk ≤ 0.8
```

### 3. SPICA Uniform Interface
```
SpicaBase (309 lines)
├── Telemetry (JSONL)
├── Manifest (SHA256)
├── Lineage (HMAC)
└── Lifecycle (spawn/prune)
      ↓
11 Derivatives (4,765 lines total)
├── spica_tts.py (858)
├── spica_turns.py (683)
├── spica_rag.py (520)
└── ... (8 more)
```

### 4. Tool Evolution Loop
```
ToolGen → RepairLab → PHASE → D-REAM
   ↓         ↓         ↓        ↓
Synthesize  Repair   Evaluate  Evolve
Tools      Failures  Metrics   Patterns
   ↑                            ↓
   └────────────────────────────┘
         Promoted Winners
```

---

## Current Status

### Active (Production Ready)
- ✅ `kloros.service` - Voice loop
- ✅ SPICA framework (11 domains, 100% migrated)
- ✅ ChromaDB + SQLite (memory/vectors)
- ✅ ToolGen + RepairLab (tool evolution)
- ✅ Telemetry (JSONL logging)

### Disabled (Awaiting Implementation)
- ⏸️ `dream.service` - D-REAM evolution
  - **Needs:** Adaptive timer
  - **Needs:** PHASE completion signaling
  - **Needs:** Result collapse
- ⏸️ PHASE orchestration (timer enabled, waiting for D-REAM)

### Timers (Enabled, Waiting)
- ✅ `dream-sync-promotions.timer` - Every 5 min
- ✅ `phase-heuristics.timer` - Waiting for D-REAM
- ✅ `spica-phase-test.timer` - 3 AM nightly (waiting for D-REAM)

---

## Deployment Quick Start

### Check System Status
```bash
# Services
systemctl status kloros.service dream.service

# Timers
systemctl list-timers | grep -E "dream|phase|spica"

# Data volumes
du -sh ~/.kloros /home/kloros/artifacts/dream /home/kloros/logs
```

### Monitor D-REAM Evolution (when enabled)
```bash
# Watch runner logs
journalctl -u dream.service -f

# Check artifacts
ls -lht /home/kloros/artifacts/dream/ | head

# View latest telemetry
find /home/kloros/artifacts/dream -name "*.jsonl" -exec tail -5 {} \;
```

### Monitor PHASE Testing
```bash
# Check timer schedule
systemctl list-timers | grep spica-phase-test

# View last run
journalctl -u spica-phase-test.service -n 100

# Check report
cat /home/kloros/src/phase/phase_report.jsonl | tail -1 | jq
```

### Verify SPICA Instances
```bash
# List instances
ls -1 /home/kloros/experiments/spica/instances/

# Check instance count
ls /home/kloros/experiments/spica/instances/ | wc -l  # Should be 10

# Inspect instance
ls -la /home/kloros/experiments/spica/instances/spica-*/
```

### Check Voice Loop
```bash
# Service status
systemctl status kloros.service

# Recent logs
journalctl -u kloros.service -n 50

# Check memory DB (may not exist)
ls -lh ~/.kloros/kloros_memory.db 2>/dev/null || echo "DB not present"

# Check vector store
du -sh ~/.kloros/chroma_data/
```

---

## Key Metrics & Thresholds

### D-REAM Parameters (Verified)
```yaml
population_size: 24
elite_k: 6
tournament_size: 3
mutation_rate: 0.15
crossover_rate: 0.7
novelty_k: 15

# Hard Constraints
max_drawdown: 0.6    # Infeasible if exceeded
max_risk: 0.8        # Infeasible if exceeded
min_stability: 0.3
```

### PHASE Schedule
```
Window: 3:00 AM - 7:00 AM
Duration: 4 hours
Frequency: Nightly
Domains: 11 SPICA derivatives
KPIs: ~100 total (8-12 per domain)
```

### Voice Performance (Typical)
```
STT latency:    50-200ms (Vosk fast path)
                + 100-500ms (Whisper verification, parallel)
LLM latency:    500-2000ms
TTS latency:    100-300ms
Total turn:     1-3 seconds (Vosk path)
```

### System Resources
```
Source code:     264M
Runtime state:   453M
Epoch logs:      4,466 files
SPICA instances: 10 snapshots
```

---

## Troubleshooting Guide

### 1. D-REAM Not Starting
**Symptoms:** `dream.service` fails to start
**Checks:**
1. Verify service enabled: `systemctl is-enabled dream.service`
2. Check logs: `journalctl -u dream.service -n 100`
3. Verify config: `cat /home/kloros/src/dream/config/dream.yaml`
4. Check PHASE window: If 3-7 AM, D-REAM sleeps
5. Verify adaptive timer implemented: `grep adaptive_sleep /home/kloros/src/dream/runner/__main__.py`

### 2. PHASE Tests Not Running
**Symptoms:** No PHASE reports generated
**Checks:**
1. Verify timer: `systemctl list-timers | grep spica-phase-test`
2. Check timer status: `systemctl status spica-phase-test.timer`
3. View last run: `journalctl -u spica-phase-test.service -n 50`
4. Verify domains: `ls /home/kloros/src/phase/domains/spica_*.py | wc -l` (should be 11)
5. Check D-REAM status: PHASE waits for D-REAM to be active

### 3. Voice Loop Issues
**Symptoms:** Voice not responding
**Checks:**
1. Service status: `systemctl status kloros.service`
2. Check logs: `journalctl -u kloros.service -n 50`
3. Verify Vosk: `ls ~/kloros_models/vosk/model`
4. Verify Whisper: Check GPU availability and model loading
5. Verify Piper: `which piper` or check `KLR_PIPER_EXE`
6. Verify Ollama: `curl http://localhost:11434/api/tags`

### 4. Missing SPICA Instances
**Symptoms:** Instance count < 10
**Checks:**
1. Count instances: `ls /home/kloros/experiments/spica/instances/ | wc -l`
2. Check retention policy: `grep -A5 spica_retention /home/kloros/src/dream/config/dream.yaml`
3. Check prune logs: `journalctl | grep spica | grep prune`
4. Verify PHASE created instances: `ls -lt /home/kloros/experiments/spica/instances/`

### 5. High Disk Usage
**Symptoms:** Disk space warnings
**Checks:**
1. Check logs: `du -sh /home/kloros/logs` (4,466 epoch logs)
2. Check artifacts: `du -sh /home/kloros/artifacts/dream`
3. Check runtime: `du -sh ~/.kloros` (should be ~453M)
4. Check SPICA: `du -sh /home/kloros/experiments/spica/instances`
5. TTL cleanup: Verify Monday 00:00 cleanup runs

---

## Environment Variables

### Voice Configuration
```bash
KLR_INPUT_IDX=3              # Force audio device
KLR_WAKE_PHRASES="kloros"    # Wake word
KLR_WAKE_CONF_MIN=0.65       # Vosk confidence
KLR_WAKE_RMS_MIN=350         # RMS energy gate
KLR_INPUT_GAIN=1.0           # Software gain
KLR_PIPER_EXE=/path/to/piper # Piper override
```

### D-REAM Configuration
```bash
# Set via systemd service or config files
# See: /home/kloros/src/dream/config/dream.yaml
```

---

## References

### Comprehensive Documentation
- **Full Audit:** `/home/kloros/KLOROS_SYSTEM_AUDIT_COMPREHENSIVE.md` (795 lines)
- **Executive Summary:** `/home/kloros/AUDIT_SUMMARY.md` (358 lines)
- **This Quick Index:** `/home/kloros/AUDIT_QUICK_INDEX.md`

### Verification & Corrections
- **Verification Report:** `/home/kloros/AUDIT_VERIFICATION_REPORT.md`
  - Documents all fabrications found in v1.0
  - Lists all corrections made in v2.0
  - Provides verification commands

### Architecture Documentation
- **ASTRAEA Thesis:** `/home/kloros/docs/ASTRAEA_SYSTEM_THESIS.md`
- **SPICA Architecture:** `/home/kloros/SPICA_ARCHITECTURE.md`
- **D-REAM Guide:** `/home/kloros/D-REAM_TRUE_SYSTEM_GUIDE.md`

### Status & Migration
- **SPICA Migration:** `/home/kloros/SPICA_MIGRATION_COMPLETE.md`
- **Phase 6 Completion:** `/home/kloros/PHASE6_COMPLETION_SUMMARY.md`

---

## Contact Points (Code Locations)

| Component | Primary File | Lines | Location |
|-----------|-------------|-------|----------|
| Voice Loop | kloros_voice.py | 3,907 | `/home/kloros/src/` |
| D-REAM | runner/__main__.py | 575 | `/home/kloros/src/dream/` |
| PHASE | run_all_domains.py | 156 | `/home/kloros/src/phase/` |
| SPICA Base | base.py | 309 | `/home/kloros/src/spica/` |
| RAG | simple_rag.py | ~600 | `/home/kloros/src/` |
| ToolGen | - | 7,153 | `/home/kloros/src/tool_synthesis/` |
| RepairLab | - | - | `/home/kloros/repairlab/` |

---

## Quick Verification Commands

```bash
# Module count
find /home/kloros/src -name "*.py" | wc -l              # 529

# Line count
find /home/kloros/src -name "*.py" -exec wc -l {} + | tail -1  # 122,841

# Source size
du -sh /home/kloros/src                                  # 264M

# Runtime state
du -sh ~/.kloros                                         # 453M

# SPICA domains
find /home/kloros/src/phase/domains -name "spica_*.py" | wc -l  # 11

# SPICA instances
ls /home/kloros/experiments/spica/instances/ | wc -l     # 10

# Epoch logs
find /home/kloros/logs -name "epoch_*.log" | wc -l       # 4,466

# Service status
systemctl list-unit-files | grep -E "dream|phase|spica" | grep -v systemd-pcrphase
```

---

**Quick Index Version:** 2.0 (Verified)
**Last Updated:** October 28, 2025
**Bookmark this page for daily operations**
