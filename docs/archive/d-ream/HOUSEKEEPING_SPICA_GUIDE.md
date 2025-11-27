# SPICA Housekeeping Optimization - Implementation Guide

**Date**: 2025-10-28
**Version**: 1.0
**Status**: ✅ IMPLEMENTED & TESTED

---

## Executive Summary

Created a SPICA derivative for optimizing KLoROS housekeeping parameters. This enables D-REAM to autonomously discover optimal configurations for system maintenance, balancing performance, disk efficiency, data retention, and system health.

**Key Features**:
- ✅ 7 configurable parameters (retention, vacuum frequency, backup policy, etc.)
- ✅ Multi-objective fitness function (performance + disk + health + retention)
- ✅ Safe TEST MODE (simulates without deletions) and LIVE MODE
- ✅ Production-aware parameter validation
- ✅ Comprehensive KPI tracking (13 metrics)

---

## What Is Housekeeping?

KLoROS has an automated maintenance system that performs 14 different tasks:

### Memory System Maintenance
1. **Event Cleanup**: Delete old events beyond retention period
2. **Episode Condensation**: Summarize old conversations
3. **Database Vacuum**: Optimize SQLite database performance
4. **Integrity Validation**: Check for data consistency issues

### File System Maintenance
5. **Python Cache Cleanup**: Remove .pyc files and __pycache__ directories
6. **Backup File Management**: Rotate old backup files
7. **TTS Output Cleanup**: Remove old generated speech files
8. **Reflection Log Rotation**: Manage reflection logs

### Analysis & Optimization
9. **TTS Quality Analysis**: Analyze speech synthesis quality
10. **Memory Export to KB**: Export summaries to knowledge base
11. **RAG Database Rebuild**: Refresh retrieval database
12. **Obsolete Script Cleanup**: Archive deprecated code
13. **File Obsolescence Sweep**: Mark stale files
14. **Health Reporting**: Generate system health scores

---

## The Optimization Problem

### Parameters to Optimize

| Parameter | Description | Default | Range | Impact |
|-----------|-------------|---------|-------|--------|
| `retention_days` | How long to keep events | 30 | 14-60 | Memory usage vs. history |
| `vacuum_days` | Database optimization freq | 7 | 3-14 | Performance vs. overhead |
| `reflection_retention_days` | Reflection log retention | 60 | 30-90 | Disk space vs. history |
| `reflection_log_max_mb` | Max reflection log size | 50 | 25-100 | Log rotation frequency |
| `max_uncondensed_episodes` | Episodes before condensation | 100 | 50-200 | Query speed vs. compression |
| `backup_retention_days` | How long to keep backups | 30 | 14-60 | Disk space vs. safety |
| `max_backups_per_file` | Backup file versions to keep | 3 | 2-5 | Disk space vs. rollback |

### Optimization Objectives

**Minimize**:
- Cleanup time (faster is better)
- Database size (smaller is better)
- Disk space used (more freed is better)

**Maximize**:
- System health score (higher is better)
- Data retention (preserve useful history)

**Balance**:
- Too aggressive retention = data loss
- Too conservative = bloat and slow queries

---

## Implementation: SpicaHousekeeping

### Architecture

```
SpicaHousekeeping (SPICA derivative)
├── HousekeepingTestConfig: Parameter bounds and fitness weights
├── HousekeepingTestResult: Test metrics and results
└── Core Methods:
    ├── run_test(): Execute housekeeping with candidate parameters
    ├── compute_fitness(): Multi-objective scoring
    └── evaluate(): Full evaluation pipeline
```

###File: `/home/kloros/src/phase/domains/spica_housekeeping.py`

### Key Components

#### 1. Test Configuration

```python
@dataclass
class HousekeepingTestConfig:
    # Parameter bounds
    retention_days_min: int = 14
    retention_days_max: int = 60

    vacuum_days_min: int = 3
    vacuum_days_max: int = 14

    # ... more parameters ...

    # Target KPIs
    target_cleanup_time_sec: float = 30.0
    target_db_size_mb: float = 100.0
    target_health_score: float = 95.0

    # Fitness weights (sum to 1.0)
    fitness_weight_performance: float = 0.30
    fitness_weight_disk_efficiency: float = 0.25
    fitness_weight_health: float = 0.25
    fitness_weight_retention: float = 0.20
```

#### 2. Test Results

```python
@dataclass
class HousekeepingTestResult:
    # Configuration tested
    retention_days: int
    vacuum_days: int
    # ... 5 more parameters ...

    # Performance metrics
    cleanup_time_sec: float
    tasks_completed: int
    errors: int

    # Disk metrics
    db_size_mb: float
    disk_space_freed_mb: float
    python_cache_freed_mb: float
    backup_files_deleted: int
    tts_files_deleted: int

    # Health metrics
    health_score: float
    integrity_issues: int

    # Cleanup results
    events_deleted: int
    episodes_condensed: int
    vacuum_performed: bool
```

#### 3. Fitness Computation

```python
def compute_fitness(self, result: HousekeepingTestResult) -> float:
    # Performance: faster cleanup is better
    perf_norm = 1.0 - min(cleanup_time / target_time, 1.0)

    # Disk efficiency: more freed + smaller DB
    disk_freed_norm = min(disk_freed_mb / 50.0, 1.0)
    db_size_norm = 1.0 - min(db_size_mb / target_db_size, 1.0)
    disk_efficiency = (disk_freed_norm + db_size_norm) / 2.0

    # Health: higher score is better
    health_norm = health_score / 100.0

    # Retention balance: optimal ~30 days
    retention_deviation = abs(retention_days - 30.0)
    retention_norm = 1.0 - min(retention_deviation / 30.0, 1.0)

    # Weighted sum
    fitness = (
        perf_norm * 0.30 +
        disk_efficiency * 0.25 +
        health_norm * 0.25 +
        retention_norm * 0.20
    )

    # Penalties
    if errors > 0:
        fitness *= 0.5
    if integrity_issues > 0:
        fitness *= 0.8

    return fitness
```

---

## Safety Features

### 1. TEST MODE (Default)

By default, housekeeping tests run in **TEST MODE**:

```bash
# TEST MODE is the default
python3 -m src.phase.domains.spica_housekeeping
```

**What it does**:
- ✅ Simulates cleanup metrics
- ✅ No actual file deletions
- ✅ No database modifications
- ✅ Safe for experimentation

**Simulation logic**:
- Cleanup time scales with retention days
- Disk freed scales inversely with retention (aggressive = more freed)
- All metrics derived from configuration parameters

### 2. LIVE MODE (Use with Caution!)

For actual testing with real deletions:

```bash
# LIVE MODE: ACTUALLY DELETES FILES
KLR_HOUSEKEEPING_TEST_MODE=0 python3 -m src.phase.domains.spica_housekeeping
```

**What it does**:
- ⚠️ Actually runs housekeeping operations
- ⚠️ Deletes old events, files, backups
- ⚠️ Modifies database (vacuum, condensation)
- ⚠️ **USE ONLY ON TEST SYSTEMS OR WITH BACKUPS**

### 3. Parameter Validation

All parameters are validated against bounds before execution:

```python
def _validate_parameters(self, candidate: Dict[str, Any]) -> bool:
    checks = [
        (14 <= retention_days <= 60),
        (3 <= vacuum_days <= 14),
        (30 <= reflection_retention <= 90),
        (25 <= reflection_log_max_mb <= 100),
        (50 <= max_uncondensed_episodes <= 200),
        (14 <= backup_retention_days <= 60),
        (2 <= max_backups_per_file <= 5)
    ]
    return all(checks)
```

Invalid configurations return status="invalid" with zero fitness.

---

## Usage Examples

### Example 1: Test Default Configuration

```python
from src.phase.domains.spica_housekeeping import SpicaHousekeeping

evaluator = SpicaHousekeeping()

# Default config (current production settings)
candidate = {
    "retention_days": 30,
    "vacuum_days": 7,
    "reflection_retention_days": 60,
    "reflection_log_max_mb": 50,
    "max_uncondensed_episodes": 100,
    "backup_retention_days": 30,
    "max_backups_per_file": 3
}

metrics = evaluator.evaluate(candidate)
print(f"Fitness: {metrics['fitness']:.3f}")
print(f"Cleanup time: {metrics['cleanup_time_sec']:.1f}s")
print(f"Disk freed: {metrics['disk_space_freed_mb']:.1f}MB")
print(f"Health score: {metrics['health_score']:.1f}")
```

**Expected Output**:
```
Fitness: 0.807
Cleanup time: 8.0s
Disk freed: 10.0MB
Health score: 95.0
```

### Example 2: Test Aggressive Retention

```python
# More aggressive retention (shorter history)
aggressive = {
    "retention_days": 14,  # Minimal retention
    "vacuum_days": 3,       # Frequent vacuum
    "reflection_retention_days": 30,
    "reflection_log_max_mb": 25,
    "max_uncondensed_episodes": 50,
    "backup_retention_days": 14,
    "max_backups_per_file": 2
}

metrics = evaluator.evaluate(aggressive)
# Will score lower on retention_norm but higher on disk_efficiency
```

### Example 3: Test Conservative Retention

```python
# More conservative retention (longer history)
conservative = {
    "retention_days": 60,  # Maximum retention
    "vacuum_days": 14,      # Infrequent vacuum
    "reflection_retention_days": 90,
    "reflection_log_max_mb": 100,
    "max_uncondensed_episodes": 200,
    "backup_retention_days": 60,
    "max_backups_per_file": 5
}

metrics = evaluator.evaluate(conservative)
# Will score higher on retention but lower on disk_efficiency and performance
```

---

## D-REAM Integration

### Add to D-REAM Config

Create experiment configuration in `/home/kloros/src/dream/config/`:

```yaml
# housekeeping_experiment.yaml
domain: housekeeping
evaluator: spica_housekeeping

parameters:
  retention_days:
    type: integer
    min: 14
    max: 60

  vacuum_days:
    type: integer
    min: 3
    max: 14

  reflection_retention_days:
    type: integer
    min: 30
    max: 90

  reflection_log_max_mb:
    type: integer
    min: 25
    max: 100

  max_uncondensed_episodes:
    type: integer
    min: 50
    max: 200

  backup_retention_days:
    type: integer
    min: 14
    max: 60

  max_backups_per_file:
    type: integer
    min: 2
    max: 5

evolution:
  algorithm: r_zero  # R-Zero tournament selection
  population_size: 10
  generations: 20
  mutation_rate: 0.2

fitness:
  objectives:
    - name: performance
      weight: 0.30
      direction: maximize

    - name: disk_efficiency
      weight: 0.25
      direction: maximize

    - name: health
      weight: 0.25
      direction: maximize

    - name: retention_balance
      weight: 0.20
      direction: maximize
```

### Run D-REAM Experiment

```bash
cd /home/kloros

# Test mode (safe simulation)
KLR_HOUSEKEEPING_TEST_MODE=1 \
/home/kloros/.venv/bin/python3 -m src.dream.runner \
  --config /home/kloros/src/dream/config/housekeeping_experiment.yaml \
  --logdir /home/kloros/logs/dream/housekeeping \
  --epochs-per-cycle 1
```

---

## Interpreting Results

### Fitness Score Breakdown

| Component | Weight | What It Measures | Optimal Value |
|-----------|--------|------------------|---------------|
| Performance | 30% | Cleanup speed | < 30s |
| Disk Efficiency | 25% | Space freed + DB size | > 50MB freed, < 100MB DB |
| Health | 25% | System health score | 95-100 |
| Retention Balance | 20% | Days from optimal (30) | Exactly 30 days |

### Example Score Analysis

**Configuration A**: retention_days=30, vacuum_days=7 (default)
```
Performance: 0.73 (8s cleanup vs 30s target)
Disk Efficiency: 0.60 (10MB freed, 0.3MB DB)
Health: 0.95 (95/100 score)
Retention: 1.00 (exactly 30 days = optimal)

Fitness = 0.73*0.30 + 0.60*0.25 + 0.95*0.25 + 1.00*0.20
        = 0.219 + 0.150 + 0.238 + 0.200
        = 0.807
```

**Configuration B**: retention_days=14, vacuum_days=3 (aggressive)
```
Performance: 0.87 (6.4s cleanup)
Disk Efficiency: 0.80 (21MB freed, smaller DB)
Health: 0.95 (95/100 score)
Retention: 0.47 (16 days from optimal)

Fitness = 0.87*0.30 + 0.80*0.25 + 0.95*0.25 + 0.47*0.20
        = 0.261 + 0.200 + 0.238 + 0.094
        = 0.793
```

**Winner**: Configuration A (default) wins despite slower cleanup due to better retention balance.

---

## Expected D-REAM Outcomes

### Phase 0-2: Exploration
- Test configurations across full parameter space
- Identify trade-offs between performance, disk usage, retention
- Discover sensitivity to each parameter

### Phase 3-4: Convergence
- R-Zero selection favors balanced configurations
- Likely convergence toward 25-35 day retention (near optimal)
- Vacuum frequency: 5-7 days (sweet spot)
- Moderate backup retention (21-30 days)

### Phase 5-6: Validation & Promotion
- Top performers undergo validation testing
- Winners promoted to production testing
- Gradual rollout with monitoring

---

## Monitoring & Metrics

### Pre-Deployment Checks

Before applying D-REAM winners:

1. **Health Score**: Ensure ≥ 90
2. **Integrity Issues**: Should be 0
3. **Cleanup Time**: Should be < 60s
4. **Data Retention**: Avoid < 20 days (data loss risk)

### Post-Deployment Monitoring

Track these metrics after applying new configuration:

```bash
# Check system health
PYTHONPATH=/home/kloros python3 << 'EOF'
from kloros_memory.housekeeping import MemoryHousekeeper
hk = MemoryHousekeeper()
health = hk.get_health_report()
print(f"Health Score: {health['health_score']}")
print(f"Status: {health['status']}")
print(f"Recommendations: {len(health['recommendations'])}")
EOF

# Monitor database size
ls -lh /home/kloros/.kloros/memory.db

# Check last maintenance
sudo journalctl -u kloros | grep -i housekeeping | tail -5
```

---

## Safety & Rollback

### Rollback Procedure

If new configuration causes issues:

```bash
# Restore default configuration
export KLR_RETENTION_DAYS=30
export KLR_AUTO_VACUUM_DAYS=7
export KLR_MAX_UNCONDENSED=100
export KLR_BACKUP_RETENTION_DAYS=30
export KLR_MAX_BACKUPS_PER_FILE=3
export KLR_REFLECTION_RETENTION_DAYS=60
export KLR_REFLECTION_LOG_MAX_MB=50

# Restart services
sudo systemctl restart kloros
```

### Backup Before Live Testing

```bash
# Backup memory database
sudo -u kloros cp /home/kloros/.kloros/memory.db \
  /home/kloros/.kloros/memory.db.backup-$(date +%Y%m%d)

# Verify backup
ls -lh /home/kloros/.kloros/memory.db*
```

---

## Limitations & Future Work

### Current Limitations

1. **Test Mode Simulation**: Metrics are estimated, not measured from actual operations
2. **No Concurrency Testing**: Doesn't test impact on concurrent operations
3. **Static Health Model**: Health score model doesn't adapt to system load
4. **Limited Failure Modes**: Doesn't test edge cases (full disk, corrupted DB, etc.)

### Future Enhancements

1. **Dynamic Retention**: Adjust retention based on disk space availability
2. **Load-Aware Scheduling**: Run housekeeping during low-activity periods
3. **Predictive Modeling**: Forecast disk usage growth, plan proactive cleanup
4. **Incremental Cleanup**: Spread cleanup across multiple runs to reduce spikes
5. **Adaptive Parameters**: Learn optimal parameters from production metrics

---

## Comparison with GPU SPICA

| Aspect | GPU Allocation SPICA | Housekeeping SPICA |
|--------|---------------------|-------------------|
| **Parameters** | 2 (VLLM util, Whisper size) | 7 (retention, vacuum, backups, etc.) |
| **KPIs** | 5 (latency, GPU util, OOM, capacity) | 13 (time, disk, health, deletions, etc.) |
| **Safety** | Production validation (checks model size) | TEST MODE by default (no deletions) |
| **Complexity** | Hardware constraints (GPU memory) | Policy constraints (data retention) |
| **Risk** | Medium (OOM crash possible) | Low (safe to experiment) |
| **Impact** | Performance (latency) | Disk usage + system health |

---

## Conclusion

**Status**: ✅ **READY FOR D-REAM EXPERIMENTS**

### What Was Delivered

1. ✅ Full SPICA derivative implementation (~650 lines)
2. ✅ 7 configurable parameters with validated bounds
3. ✅ Multi-objective fitness function (4 components)
4. ✅ Safe TEST MODE (default) and LIVE MODE
5. ✅ Comprehensive result tracking (13 metrics)
6. ✅ Integration-ready for D-REAM
7. ✅ Complete documentation

### Ready for Use

The housekeeping SPICA can now be used for:
- **Manual optimization**: Test specific configurations
- **D-REAM experiments**: Autonomous parameter discovery
- **Production tuning**: Find optimal maintenance settings
- **Trade-off analysis**: Understand performance vs. retention vs. disk usage

### Next Steps

1. **Create D-REAM experiment config** for housekeeping domain
2. **Run exploratory experiments** in TEST MODE (safe)
3. **Analyze results** to understand parameter sensitivity
4. **Select winners** for validation testing
5. **Deploy optimal configuration** with monitoring

**The framework is ready - let D-REAM find the optimal housekeeping configuration! 🧹**

---

**Document Version**: 1.0
**Last Updated**: 2025-10-28
**Author**: Claude (KLoROS Autonomous Agent)
**Status**: Production-ready, safe for experimentation
