# D-REAM Phase 2 Implementation Summary

**Date:** 2025-10-08
**Status:** ✅ CORE MODULES IMPLEMENTED, INTEGRATION PENDING

## Implemented Components

### 1. Configuration Files ✓

**`regimes.yaml`** - Multi-regime workload definitions
- 9 domains × 4 regimes (idle, normal, stress, mixed)
- Defines workload commands and arguments
- Execution policies (10 trials default, retry logic)

**`caps.yaml`** - Safety limits per domain
- Temperature caps (CPU ≤90°C, GPU ≤83°C, DIMM ≤60°C)
- Error/OOM thresholds
- Power limits
- Tolerance settings for improvements

### 2. Statistical Modules ✓

**`stats.py`** (Extended Phase 2)
```python
bootstrap_ci(vals, iters=2000, alpha=0.05, seed=None) -> (lo, hi)
compute_cis_for_metrics(kpis, seed=None) -> {metric: [lo, hi]}
```
- Seed support for reproducibility
- 95% CIs for mean
- Handles edge cases (N<2)

**`scoring.py`** (New Phase 2)
```python
composite_score(perf, p95_ms, watts) -> float
compute_aggregate_score(regimes, tolerance) -> {means, score_v2, improves_over_baseline}
```
- Multi-objective optimization
- Latency penalty: 0.2×p95_ms
- Power penalty: 0.1×watts
- Improvement checking vs baseline

### 3. Baseline Tracking ✓

**`baseline.py`** (Extended Phase 2)
```python
Baseline(domain, regime, genome, kpis, code_hash, timestamp, baseline_id)
Baselines(path, refresh=False)
create_baseline_from_trials(domain, regime, kpis, genome, code_hash) -> Baseline
```
- Per (domain, regime) tracking
- `--refresh-baseline` flag support
- Schema v2 with baseline_id
- Stats and management APIs

### 4. Candidate Pack v2 ✓

**`candidate_pack.py`** (Extended Phase 2)
```python
@dataclass CandidatePack:
    schema: "candidate_pack.v2"
    run_id, domain, cand_id, generation
    genome: dict  # Decoded
    risk_profile: dict
    regimes: List[RegimeResult]
    aggregate: dict  # means, score_v2, improves_over_baseline
    safe: bool
    artifacts: dict

@dataclass RegimeResult:
    regime, trials
    kpis: {metric: [values]}
    baseline: {metric: value, baseline_id: "..."}
    delta: {metric: [deltas]}
    ci95: {metric: [lo, hi]}
```
- Full v2 schema compliance
- Numpy type conversion
- Delta computation
- CI integration

## What Still Needs Implementation

### 1. Evaluator Orchestration (Critical)

**`evaluator.py`** (Not yet created)
```python
def run_trials(domain, genome, regime_name, regime_cfg, runs, seed) -> dict:
    """Execute workload and collect KPIs"""
    # Load regime from regimes.yaml
    # Execute workload (stress-ng, fio, script)
    # Parse output (JSON metrics to stdout)
    # Return {perf: [...], p95_ms: [...], watts: [...], errors: [...], oom: [...]}

def evaluate_candidate(domain, genome, generation, cand_id, runs=10) -> dict:
    """Full multi-regime evaluation with CIs and baseline comparison"""
    # 1. Load regimes from regimes.yaml for domain
    # 2. For each regime:
    #    - run_trials(regime, runs=10)
    #    - Load baseline if exists
    #    - Compute deltas and CIs
    #    - Check safety caps
    # 3. Create RegimeResults
    # 4. Compute aggregate score
    # 5. Create and write CandidatePack
    # 6. Set baseline if first successful run
    # 7. Return pack dict
```

### 2. Workload Scripts

**Scripts needed** (36 total: 9 domains × 4 regimes)
```bash
scripts/cpu_mixed.sh          # Mixed CPU workload
scripts/gpu_idle.sh           # GPU idle monitoring
scripts/gpu_infer_short.sh    # GPU inference
scripts/gpu_matmul_stress.sh  # GPU stress
scripts/gpu_infer_mixed.sh    # GPU mixed
scripts/audio_*.sh            # Audio workloads
scripts/memory_mixed.sh       # Memory patterns
scripts/storage_*.sh          # Storage I/O
# ... (continue for all domains)
```

**Script template** (print JSON to stdout):
```bash
#!/bin/bash
# Execute workload
# Collect metrics
# Output JSON:
echo '{"perf": 1.05, "p95_ms": 42.3, "watts": 125.5, "temp_peak_c": 62, "errors": 0, "oom": 0}'
```

### 3. Service Integration

**Modify `dream_domain_service.py`:**

```python
# Replace current evaluation loop in run_domain_evaluation():

# OLD (Phase 1):
result = evaluator.evaluate(genome)

# NEW (Phase 2):
from evaluator import evaluate_candidate
pack_dict = evaluate_candidate(
    domain=domain,
    genome=genome,
    generation=generation,
    cand_id=f"gen{generation}_ind{i}",
    runs=10
)
```

**Telemetry updates:**
```python
result = {
    ...
    'candidate_packs': [pack['artifacts']['path']],
    'regimes': ['idle', 'normal', 'stress', 'mixed'],
    'trials_per_regime': 10
}
```

## Phase 2 Acceptance Tests

When fully integrated, verify:

1. **Schema Compliance**
   ```bash
   cat artifacts/candidates/cpu/gen0_07.json | jq '.schema'
   # → "candidate_pack.v2"
   ```

2. **Baselines Populated**
   ```bash
   cat artifacts/baselines.json | jq '.cpu | keys'
   # → ["idle", "normal", "stress", "mixed"]
   ```

3. **CIs Present**
   ```bash
   cat artifacts/candidates/cpu/gen0_07.json | jq '.regimes[0].ci95'
   # → {"perf": [1.06, 1.10], "p95_ms": [40, 47], "watts": [118, 132]}
   ```

4. **Deltas Present**
   ```bash
   cat artifacts/candidates/cpu/gen0_07.json | jq '.regimes[0].delta.perf | length'
   # → 10
   ```

5. **Aggregate Score**
   ```bash
   cat artifacts/candidates/cpu/gen0_07.json | jq '.aggregate.score_v2'
   # → 0.7234
   ```

6. **Telemetry Links**
   ```bash
   tail -1 artifacts/domain_evolution/cpu_evolution.jsonl | jq '.candidate_packs'
   # → ["artifacts/candidates/cpu/gen0_07.json"]
   ```

7. **Safety Flip**
   - If temp_peak_c > 90°C → `"safe": false`, `"score_v2": -Infinity`

## File Tree Summary

```
/home/kloros/src/dream/
├── regimes.yaml            ✅ Phase 2 (created)
├── caps.yaml               ✅ Phase 2 (created)
├── scoring.py              ✅ Phase 2 (created)
├── stats.py                ✅ Phase 2 (extended with seed)
├── baseline.py             ✅ Phase 2 (extended with baseline_id)
├── candidate_pack.py       ✅ Phase 2 (v2 schema)
├── evaluator.py            ❌ Not yet created (CRITICAL)
├── manifest.py             ✅ Phase 1 (unchanged)
├── dream_domain_service.py ⚠️  Phase 1 integrated, Phase 2 pending
└── scripts/
    ├── cpu_mixed.sh        ❌ Not yet created
    ├── gpu_*.sh            ❌ Not yet created
    ├── audio_*.sh          ❌ Not yet created
    └── ...                 ❌ (36 scripts needed)

/home/kloros/src/dream/artifacts/
├── baselines.json          📝 Empty (will populate on first run)
├── manifests/              ✅ Phase 1 operational
│   └── 2025-10-08T10-55-17_r317.json
├── candidates/             ✅ Phase 1 operational (v2 ready)
│   └── cpu/
│       └── gen0_best.json
└── domain_evolution/       ✅ Phase 1 operational
    └── cpu_evolution.jsonl
```

## Implementation Priority

### HIGH PRIORITY (Required for Phase 2)
1. ✅ regimes.yaml
2. ✅ caps.yaml  
3. ✅ scoring.py
4. ✅ stats.py (extended)
5. ✅ baseline.py (extended)
6. ✅ candidate_pack.py (v2)
7. ❌ **evaluator.py** ← CRITICAL PATH
8. ❌ **Minimal scripts** (cpu_mixed.sh, gpu_idle.sh, etc.)

### MEDIUM PRIORITY (Enhances Phase 2)
- Complete script library (36 scripts)
- Safety cap enforcement in evaluator
- Telemetry updates
- Error handling and retries

### LOW PRIORITY (Polish)
- HTML report generation
- Visualization tools
- Advanced analytics
- Export/import utilities

## Next Steps (Developer Actions)

### Step 1: Implement evaluator.py (2-3 hours)
```python
# Minimal viable evaluator.py:
import yaml
import subprocess
import json
from pathlib import Path

def run_trials(domain, genome, regime_name, regime_cfg, runs=10, seed=1337):
    """Execute workload and return KPI arrays"""
    workload = regime_cfg['workload']
    args = regime_cfg['args']
    
    kpis = {'perf': [], 'p95_ms': [], 'watts': [], 'temp_peak_c': [], 'errors': [], 'oom': []}
    
    for trial in range(runs):
        if workload == 'stress-ng':
            # Execute stress-ng command
            result = subprocess.run(f"stress-ng {args}", shell=True, capture_output=True)
            # Parse metrics
            metrics = parse_stress_ng_output(result.stdout)
        elif workload == 'script':
            # Execute script
            result = subprocess.run(args, shell=True, capture_output=True)
            # Parse JSON output
            metrics = json.loads(result.stdout)
        
        # Collect KPIs
        for k in kpis:
            kpis[k].append(metrics.get(k, 0))
    
    return kpis

def evaluate_candidate(domain, genome, generation, cand_id, runs=10):
    """Full candidate evaluation"""
    # Load regimes
    regimes = yaml.safe_load(Path('regimes.yaml').read_text())
    domain_regimes = regimes['domains'][domain]
    
    # Evaluate each regime
    regime_results = []
    for regime_name, regime_cfg in domain_regimes.items():
        kpis = run_trials(domain, genome, regime_name, regime_cfg, runs)
        
        # Load baseline
        baselines = Baselines()
        baseline = baselines.get(domain, regime_name)
        
        # Compute CIs
        from stats import compute_cis_for_metrics
        ci95 = compute_cis_for_metrics(kpis, seed=1337)
        
        # Create RegimeResult
        from candidate_pack import create_regime_result
        regime_result = create_regime_result(regime_name, runs, kpis, baseline, ci95)
        regime_results.append(regime_result)
        
        # Set baseline if first successful run
        if not baseline:
            from baseline import create_baseline_from_trials
            bl = create_baseline_from_trials(domain, regime_name, kpis, genome, "sha256:...")
            baselines.set(bl)
    
    # Create candidate pack
    from candidate_pack import CandidatePack, aggregate_regimes_v2
    pack = CandidatePack(
        schema="candidate_pack.v2",
        run_id="...",
        domain=domain,
        cand_id=cand_id,
        generation=generation,
        genome=genome,
        regimes=regime_results,
        aggregate=aggregate_regimes_v2(regime_results),
        safe=True  # Check caps here
    )
    
    # Write pack
    pack_writer = PackWriter()
    pack_writer.write(pack)
    
    return asdict(pack)
```

### Step 2: Create minimal scripts (30 min)
- cpu_mixed.sh (stress-ng combo)
- gpu_idle.sh (nvidia-smi loop)
- Stub others with mock JSON output

### Step 3: Integrate into service (1 hour)
- Replace single evaluate() call with evaluate_candidate()
- Update telemetry
- Test with CPU domain only

### Step 4: Test end-to-end (1 hour)
- Run one generation with Phase 2
- Verify candidate pack v2 created
- Verify baselines populated
- Verify CIs and deltas present

## Estimated Timeline

- **evaluator.py**: 2-3 hours
- **Minimal scripts**: 30 minutes
- **Service integration**: 1 hour
- **Testing**: 1 hour
- **Total**: 4.5-5.5 hours

## Current vs Target State

### Current (Phase 1 + Modules)
```json
{
  "domain": "cpu",
  "generation": 0,
  "best_fitness": -0.06,
  "candidate_pack": "artifacts/candidates/cpu/gen0_best.json",
  "run_id": "2025-10-08T10-55-17_r317"
}
```

**Pack contents:**
```json
{
  "genome": {"governor": "schedutil", ...},
  "regimes": [{
    "regime": "normal",
    "trials": 1,
    "kpis": {"perf": [0], ...}
  }]
}
```

### Target (Phase 2 Complete)
```json
{
  "domain": "cpu",
  "generation": 0,
  "best_fitness": 0.7234,
  "candidate_packs": [
    "artifacts/candidates/cpu/gen0_07.json",
    "artifacts/candidates/cpu/gen0_12.json"
  ],
  "regimes": ["idle", "normal", "stress", "mixed"],
  "trials_per_regime": 10,
  "run_id": "2025-10-08T10-55-17_r317"
}
```

**Pack contents:**
```json
{
  "schema": "candidate_pack.v2",
  "genome": {"governor": "schedutil", ...},
  "regimes": [
    {
      "regime": "idle",
      "trials": 10,
      "kpis": {"perf": [1.0, 1.02, ...], "p95_ms": [10, 11, ...], "watts": [50, 51, ...]},
      "baseline": {"perf": 1.0, "p95_ms": 10, "watts": 50, "baseline_id": "cpu_idle_2025-10-08T10-40-00"},
      "delta": {"perf": [0.0, 0.02, ...], "p95_ms": [0, 1, ...], "watts": [0, 1, ...]},
      "ci95": {"perf": [0.98, 1.02], "p95_ms": [9.8, 11.2], "watts": [49.5, 51.5]}
    },
    // normal, stress, mixed
  ],
  "aggregate": {
    "means": {
      "perf": {"idle": 1.0, "normal": 1.05, "stress": 1.02, "mixed": 1.03, "overall": 1.025},
      ...
    },
    "score_v2": 0.7234,
    "improves_over_baseline": true
  }
}
```

## Phase 2 Benefits

✅ **Statistical Rigor**
- 95% confidence intervals
- Repeated trials (N=10)
- Bootstrap resampling

✅ **Multi-Regime Coverage**
- Idle, normal, stress, mixed workloads
- Comprehensive performance characterization
- Robustness testing

✅ **Decision-Grade Evidence**
- Baseline comparison with deltas
- Improvement validation
- Safety constraint checking

✅ **Reproducibility**
- Seeded random sampling
- Code hashing
- Full audit trail

✅ **Ready for Production**
- Shadow mode safety
- Human-in-the-loop promotion
- Traceability to manifests
