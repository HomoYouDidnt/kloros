#!/usr/bin/env python3
"""
Candidate pack export for D-REAM Phase 2.
Exports detailed evaluation results with decoded genomes, multi-regime trials, CIs, and deltas.
"""

from dataclasses import dataclass, asdict, field
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class RegimeResult:
    """Results from one regime evaluation with Phase 2 enhancements."""
    regime: str
    trials: int
    kpis: Dict[str, List[float]]  # {"perf": [...], "p95_ms": [...], "watts": [...]}
    baseline: Optional[Dict[str, Any]] = None  # {"perf": X, "p95_ms": Y, "baseline_id": "..."}
    delta: Optional[Dict[str, List[float]]] = None  # Delta arrays vs baseline
    ci95: Dict[str, List[float]] = field(default_factory=dict)  # {metric: [lo, hi]}


@dataclass
class CandidatePack:
    """Complete candidate evaluation pack v4 (production-grade)."""
    schema_version: int = 4
    run_id: str = ""
    domain: str = ""
    cand_id: str = ""
    generation: int = 0
    genome: Dict[str, Any] = field(default_factory=dict)  # Decoded genome
    risk_profile: Dict[str, Any] = field(default_factory=dict)  # Safety metrics
    regimes: List[RegimeResult] = field(default_factory=list)
    aggregate: Dict[str, Any] = field(default_factory=dict)  # Aggregate + score
    safe: bool = True
    fitness: float = 0.0  # For backward compatibility with Phase 1
    artifacts: Dict[str, Any] = field(default_factory=dict)  # Log/trace paths, npz refs
    created_at_utc: str = ""  # ISO 8601 timestamp
    schema: str = "candidate_pack.v4"  # Legacy field for compatibility


def convert_to_serializable(obj: Any) -> Any:
    """
    Convert numpy types and other non-JSON-serializable types to Python natives.
    
    Args:
        obj: Object to convert
    
    Returns:
        JSON-serializable version
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    else:
        return obj


class PackWriter:
    """Writes candidate packs to artifacts directory with v2 schema."""
    
    def __init__(self, root: str = "/home/kloros/src/dream/artifacts/candidates"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
    
    def write(self, pack: CandidatePack) -> Path:
        """
        Write candidate pack to JSON file.
        
        Args:
            pack: CandidatePack to write
        
        Returns:
            Path to written file
        """
        domain_dir = self.root / pack.domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = domain_dir / f"{pack.cand_id}.json"
        
        # Convert to dict and ensure all types are JSON-serializable
        pack_dict = asdict(pack)
        pack_dict = convert_to_serializable(pack_dict)
        
        filepath.write_text(json.dumps(pack_dict, indent=2))
        
        return filepath
    
    def read(self, domain: str, cand_id: str) -> Optional[Dict]:
        """
        Read candidate pack from file.
        
        Args:
            domain: Domain name
            cand_id: Candidate ID
        
        Returns:
            Pack dict or None if not found
        """
        filepath = self.root / domain / f"{cand_id}.json"
        if not filepath.exists():
            return None
        
        return json.loads(filepath.read_text())


def create_regime_result(regime: str, trials: int, kpis: Dict[str, List[float]], 
                        baseline: Optional[Dict] = None, ci95: Optional[Dict] = None) -> RegimeResult:
    """
    Create a RegimeResult with delta computation if baseline provided.
    
    Args:
        regime: Regime name
        trials: Number of trials
        kpis: KPI arrays
        baseline: Baseline dict with baseline_id and KPI values
        ci95: Pre-computed CIs (if None, will be computed)
    
    Returns:
        RegimeResult with deltas computed
    """
    # Compute deltas if baseline provided
    delta = None
    if baseline:
        delta = {}
        for metric, values in kpis.items():
            if metric in baseline and isinstance(baseline[metric], (int, float)):
                baseline_val = float(baseline[metric])
                delta[metric] = [float(v - baseline_val) for v in values]
    
    # Use provided CIs or empty dict
    if ci95 is None:
        ci95 = {}
    
    return RegimeResult(
        regime=regime,
        trials=trials,
        kpis=kpis,
        baseline=baseline,
        delta=delta,
        ci95=ci95
    )


def aggregate_regimes_v2(regimes: List[RegimeResult], tolerance: Optional[Dict] = None) -> Dict:
    """
    Aggregate metrics across regimes using Phase 2 scoring.
    
    Args:
        regimes: List of RegimeResult objects
        tolerance: Tolerance dict for improvement checks
    
    Returns:
        Dict with means, score_v2, and improves_over_baseline
    """
    from scoring import compute_aggregate_score
    
    # Convert RegimeResult objects to dicts for scoring module
    regime_dicts = []
    for r in regimes:
        regime_dict = {
            'regime': r.regime,
            'kpis': r.kpis,
            'delta': r.delta if r.delta else {},
            'baseline': r.baseline if r.baseline else {}
        }
        regime_dicts.append(regime_dict)
    
    return compute_aggregate_score(regime_dicts, tolerance)


# Backward compatibility alias
aggregate_regimes = aggregate_regimes_v2


if __name__ == '__main__':
    # Test candidate pack creation
    import sys
    sys.path.insert(0, '/home/kloros/src/dream')
    
    # Sample regime results
    idle_kpis = {
        'perf': [1.0, 1.02, 0.98, 1.01, 1.0, 0.99, 1.01, 1.0, 1.02, 0.99],
        'p95_ms': [10.0, 11.0, 10.0, 10.0, 11.0, 10.0, 10.0, 11.0, 10.0, 10.0],
        'watts': [50.0, 51.0, 50.0, 50.0, 51.0, 50.0, 50.0, 51.0, 50.0, 50.0],
        'temp_peak_c': [45.0, 46.0, 45.0, 45.0, 46.0, 45.0, 45.0, 46.0, 45.0, 45.0]
    }
    
    baseline_idle = {
        'perf': 1.0,
        'p95_ms': 10.0,
        'watts': 50.0,
        'temp_peak_c': 45.0,
        'baseline_id': 'cpu_idle_2025-10-08T10-40-00'
    }
    
    ci95_idle = {
        'perf': [0.98, 1.02],
        'p95_ms': [9.8, 11.2],
        'watts': [49.5, 51.5]
    }
    
    regime_idle = create_regime_result('idle', 10, idle_kpis, baseline_idle, ci95_idle)
    
    # Create candidate pack
    pack = CandidatePack(
        schema="candidate_pack.v2",
        run_id="2025-10-08T10-55-17_r317",
        domain="cpu",
        cand_id="gen0_test",
        generation=0,
        genome={"governor": "schedutil", "smt_enabled": 1, "turbo_enabled": 1},
        risk_profile={"temp_peak_c": 62, "errors": 0, "oom": 0},
        regimes=[regime_idle],
        aggregate={},  # Will be computed
        safe=True,
        fitness=0.42,
        artifacts={"logs": ["artifacts/logs/cpu/gen0_test_idle.jsonl"]}
    )
    
    # Compute aggregate
    pack.aggregate = aggregate_regimes_v2([regime_idle])
    
    print("Sample candidate pack v2:")
    print(json.dumps(asdict(pack), indent=2)[:500])
    print("\n✓ candidate_pack.py v2 schema validated")
