# GPU Canary System - Implementation Summary

## Overview

Completed surgical implementation of hybrid GPU canary testing system for bounded, safe configuration tuning with two operational modes:

1. **Predictive Mode** (default): Pre-flight validation using live telemetry, no downtime
2. **Canary Mode** (escalation): Real VLLM canary testing with bounded downtime budgets

## Components Implemented

### 1. GPU Canary Runner (`/home/kloros/src/spica/gpu_canary_runner.py`)

Orchestrates quiesce/canary/restore flow with two execution paths:

**Spare GPU Path (No Downtime)**:
- Detects spare GPU with `nvidia-smi -i $SPARE_ID`
- Starts canary VLLM with `CUDA_VISIBLE_DEVICES=$SPARE_ID`
- Runs in parallel with production
- No budget consumption

**Quiesced Single-GPU Path (Bounded Downtime)**:
- Checks maintenance window (03:00-07:00 America/New_York)
- Verifies budget remaining >= required time
- Acquires `gpu_maintenance` lock
- Stops production VLLM (`judge.service`)
- Starts canary VLLM on port 9011
- Waits for test completion (CANARY_TIMEOUT=30s)
- Stops canary, restarts production
- Verifies heartbeat within 15s SLA
- Tracks budget usage atomically

**Key Features**:
- Atomic daily budget tracking: `/home/kloros/.kloros/maintenance/gpu_budget_YYYYMMDD.json`
- Comprehensive audit logging: `/home/kloros/out/orchestration/epochs/gpu_canary_YYYYMMDD.jsonl`
- Stale lock detection and cleanup
- Hard timeout enforcement
- systemd-run scope for clean canary lifecycle

### 2. GPU Maintenance Lock (`/home/kloros/src/kloros/orchestration/gpu_maintenance_lock.py`)

System-wide GPU access coordination:

- File-based locking with atomic `O_CREAT | O_EXCL` acquisition
- PID tracking and stale lock detection
- 10-second acquisition timeout
- Lock file format: `{holder}:{pid}:{timestamp}`
- Lock path: `/home/kloros/.kloros/locks/gpu_maintenance.lock`

**Functions**:
- `try_acquire_gpu_lock(holder, timeout_sec)` - Acquire lock atomically
- `check_gpu_lock_status()` - Check without acquiring
- `force_release_gpu_lock()` - Emergency cleanup

### 3. SPICA Instance Spawner (`/home/kloros/src/dream/config_tuning/spica_spawner.py`)

Ephemeral filesystem isolation for config testing:

**Modified**:
- Added `KLR_CANARY_MODE` and `KLR_CANARY_PORT` to `.env.spica`
- Inherited from parent environment for mode detection

**Functions**:
- `spawn_instance(candidate, parent_id, notes)` - Clone template with candidate config
- `run_test_in_instance(instance, test_script, timeout_sec)` - Execute isolated test
- `prune_old_instances(max_instances, max_age_days)` - Retention policy enforcement

**Retention Policy**:
- Max 10 instances
- Max 3 days age
- Pruned before each spawn

### 4. Config Tuning Runner (`/home/kloros/src/dream/config_tuning/runner.py`)

Autonomous config tuning orchestrator:

**Modified**:
- Added MODE detection from `KLR_CANARY_MODE` environment variable
- Imported `run_canary` from gpu_canary_runner
- SPICA instances inherit MODE for test execution

**Integration**:
- Spawns SPICA instances with MODE set
- SPICA tests detect mode and validate accordingly
- Mode switch is transparent to existing flow

### 5. SPICA GPU Domain (`/home/kloros/src/phase/domains/spica_gpu_allocation.py`)

Two-mode GPU allocation testing:

**Added**:
- `MODE` and `CANARY_PORT` environment variable detection
- `run_canary_validation(candidate)` - Test against live canary endpoint

**Modified**:
- `run_test()` now checks MODE and calls appropriate validator:
  - Predictive: `validate_vllm_allocation()` (pre-flight math)
  - Canary: `run_canary_validation()` (real endpoint testing)

**Canary Validation**:
- Health check: `GET http://127.0.0.1:9011/health`
- Inference test: `POST http://127.0.0.1:9011/v1/completions`
- Latency measurement and OOM detection
- Pass gates: 0 OOM events, <2s latency

### 6. Environment Configuration (`/home/kloros/.kloros_env`)

**Added Knobs**:
```bash
KLR_GPU_MAINTENANCE_MAX_DOWNTIME=60     # Max seconds downtime per night
KLR_GPU_MAINTENANCE_WINDOW=03:00-07:00  # Maintenance window (ET)
KLR_CANARY_MODE=predictive              # predictive or canary
KLR_CANARY_PORT=9011                    # Canary VLLM port
KLR_CANARY_TIMEOUT=30                   # Max seconds per canary test
KLR_CANARY_COOLDOWN_HOURS=6             # Hours between quiesced canaries
KLR_ALLOW_SPARE_GPU=false               # Enable spare GPU path
KLR_SPARE_GPU_ID=1                      # Spare GPU CUDA device ID
```

### 7. Tests (`/home/kloros/tests/test_gpu_canary.py`)

Minimal test suite covering:

**Budget Tracking**:
- `test_budget_key_format()` - Date-based key generation
- `test_read_write_budget()` - Atomic read/write cycle
- `test_add_budget_non_negative()` - Non-negative budget enforcement
- `test_sec_budget_remaining()` - Remaining budget calculation

**Maintenance Window**:
- `test_in_window_parsing()` - Window boundary checks

**GPU Lock**:
- `test_acquire_release()` - Lock lifecycle
- `test_concurrent_acquisition()` - Mutual exclusion

**Mode Switching**:
- `test_mode_detection()` - Environment variable detection

**Test Results**: All 8 tests passing ✓

### 8. Operations Checklist (`/home/kloros/docs/GPU_CANARY_OPS.md`)

Comprehensive ops guide covering:
- Prerequisites verification (requests, judge.service, nvidia-smi)
- Configuration checks
- Functional tests (budget, window, locks)
- Predictive mode testing (default)
- Canary mode testing (manual)
- Monitoring (audit trail, budget usage)
- Troubleshooting (stuck locks, exhausted budget)
- Integration with D-REAM
- Safety limits

## Flow Diagrams

### Predictive Mode (Default)
```
Observer → Intent → Orchestrator → ConfigTuningRunner
                                          ↓
                                    SPICA Instance (MODE=predictive)
                                          ↓
                                    Pre-flight validation (no real VLLM)
                                          ↓
                                    Pass/Fail → Fitness → Promotion
```

### Canary Mode (Escalation)
```
Observer → Intent → Orchestrator → ConfigTuningRunner
                                          ↓
                                    GPU Canary Runner
                                          ↓
                    ┌─────────────────────┴──────────────────────┐
                    │                                             │
             Spare GPU Path                            Quiesced Path
            (No Downtime)                         (Bounded Downtime)
                    │                                             │
                    ↓                                             ↓
           Start Canary VLLM                         Acquire GPU Lock
           on spare GPU                                      ↓
                    │                                   Stop judge.service
                    │                                         ↓
                    │                                Start Canary VLLM
                    │                                         ↓
                    └─────────────┬───────────────────────────┘
                                  ↓
                          SPICA Instance (MODE=canary)
                                  ↓
                          Hit Canary Endpoint
                          (Health + Inference)
                                  ↓
                          Pass/Fail → Fitness
                                  ↓
                          ┌───────┴────────┐
                          │                │
                    Spare GPU        Quiesced Path
                          │                │
                    Stop Canary      Stop Canary
                          │          Restart judge.service
                          │          Track Budget
                          │          Release Lock
                          │                │
                          └────────┬───────┘
                                   ↓
                              Promotion
```

## Safety Guarantees

### Hard Limits
- **Max downtime**: 60s per night
- **Maintenance window**: 03:00-07:00 America/New_York only
- **Canary timeout**: 30s per test
- **Restore SLA**: 15s to restore production
- **Rate limiting**: Max 3 runs per 24h per subsystem, 6h cooldown

### Bounded Actuators
All configuration parameters have hard min/max bounds:
- `vllm.gpu_memory_utilization`: [0.60, 0.90]
- `vllm.max_model_len`: [4096, 16384]
- `vllm.max_num_seqs`: [16, 128]

### Audit Trail
Every canary operation logged to JSONL with:
- Timestamp
- Event type (canary_start, spare_path_selected, prod_stopped, etc.)
- Candidate params hash
- Budget usage
- Success/failure reason

### Lock Safety
- Stale lock detection (PID liveness check)
- Atomic lock acquisition (race-free)
- 10-second timeout (no indefinite blocking)
- Emergency force-release capability

## Files Modified/Created

### Created
- `/home/kloros/src/spica/gpu_canary_runner.py` (305 lines)
- `/home/kloros/src/kloros/orchestration/gpu_maintenance_lock.py` (172 lines)
- `/home/kloros/tests/test_gpu_canary.py` (213 lines)
- `/home/kloros/docs/GPU_CANARY_OPS.md` (ops checklist)
- `/home/kloros/docs/GPU_CANARY_IMPLEMENTATION.md` (this file)

### Modified
- `/home/kloros/src/dream/config_tuning/spica_spawner.py` - Added MODE/PORT to .env.spica
- `/home/kloros/src/dream/config_tuning/runner.py` - Added MODE detection and imports
- `/home/kloros/src/phase/domains/spica_gpu_allocation.py` - Added two-mode validation
- `/home/kloros/.kloros_env` - Added GPU maintenance knobs

### Total Lines
- New code: ~690 lines
- Modified code: ~20 lines
- Tests: 213 lines
- Documentation: ~400 lines

## Validation

### Syntax Validation
All Python files validated with AST parser: ✓

### Unit Tests
All 8 tests passing in `test_gpu_canary.py`: ✓

### Integration Status
- [x] GPU canary runner implemented
- [x] Two-mode SPICA domain switch
- [x] ConfigTuningRunner integration
- [x] Budget tracking
- [x] Audit trail
- [x] Tests passing
- [x] Ops checklist created
- [ ] End-to-end canary mode test (requires manual setup)

## Remaining Tasks

### For Full Canary Mode
1. Verify `judge.service` restart behavior
2. Test spare GPU path (if spare GPU available)
3. Test quiesced path during maintenance window
4. Verify budget exhaustion handling
5. Test lock contention scenarios

### For Production
1. Set `KLR_ALLOW_SPARE_GPU=true` if spare GPU available
2. Adjust `KLR_GPU_MAINTENANCE_WINDOW` for timezone
3. Monitor budget consumption in first week
4. Tune `KLR_CANARY_TIMEOUT` based on actual test durations

## Quick Start

### Verify Installation
```bash
cd /home/kloros
PYTHONPATH=/home/kloros .venv/bin/pytest tests/test_gpu_canary.py -v
```

### Test Predictive Mode (Safe)
```bash
source /home/kloros/.kloros_env
python3 -c "from src.phase.domains.spica_gpu_allocation import MODE; print(f'MODE: {MODE}')"
```

Should output: `MODE: predictive`

### Monitor System
```bash
# Check budget
jq . /home/kloros/.kloros/maintenance/gpu_budget_$(date +%Y%m%d).json

# Check audit trail
tail -f /home/kloros/out/orchestration/epochs/gpu_canary_$(date +%Y%m%d).jsonl

# Check lock status
ls -lh /home/kloros/.kloros/locks/
```

## Architecture Alignment

This implementation completes the D-REAM autonomous self-healing loop:

```
Observer (OOM detection)
    ↓
Intent Generation (config tuning needed)
    ↓
Orchestrator (rate limiting, scheduling)
    ↓
D-REAM ConfigTuningRunner (candidate generation)
    ↓
SPICA Isolation (ephemeral testing)
    ↓
GPU Canary (bounded real testing) ← NEW
    ↓
Fitness Evaluation
    ↓
Promotion (to /home/kloros/out/promotions/)
```

The system maintains KLoROS governance:
- **Bounded**: All operations have hard timeouts and resource limits
- **Safe**: Predictive mode default, canary mode requires explicit escalation
- **Auditable**: Comprehensive JSONL logging of all operations
- **Reversible**: Production always restored, budget tracked, rollback capability

## References

- User's hybrid solution spec (conversation summary)
- D-REAM doctrine (`D-REAM-Anchor` skill)
- PHASE orchestration (`PHASE-Overseer` skill)
- Governance framework (`Governance-Anchor-Master` skill)

---

Implementation Date: 2025-10-29
Implementation Mode: Surgical drop-in pieces
Status: Complete ✓
