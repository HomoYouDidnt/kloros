#!/usr/bin/env python3
"""
Baseline tracking for D-REAM domain evaluations.
Stores first successful run per (domain, regime) for future comparisons.
Phase 2: Added baseline_id, refresh flag, and schema versioning.
"""

from dataclasses import dataclass, asdict
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Baseline:
    """Baseline measurement for a domain in a specific regime."""
    domain: str
    regime: str
    genome: dict
    kpis: dict  # {"perf": float, "p95_ms": float, "watts": float, ...}
    code_hash: str
    timestamp: str
    baseline_id: str = ""  # e.g., "cpu_idle_2025-10-08T10-40-00"
    
    def __post_init__(self):
        """Generate baseline_id if not provided."""
        if not self.baseline_id:
            timestamp_short = self.timestamp.replace(":", "-").split(".")[0]
            self.baseline_id = f"{self.domain}_{self.regime}_{timestamp_short}"


class Baselines:
    """Manages baseline storage and retrieval."""
    
    def __init__(self, path: str = "/home/kloros/src/dream/artifacts/baselines.json", refresh: bool = False):
        """
        Initialize baselines manager.
        
        Args:
            path: Path to baselines.json file
            refresh: If True, clear all existing baselines (use with --refresh-baseline flag)
        """
        self.p = Path(path)
        self.p.parent.mkdir(parents=True, exist_ok=True)
        
        if refresh:
            # Clear existing baselines
            self.data = {"schema": "baselines.v2"}
            self.p.write_text(json.dumps(self.data, indent=2))
        else:
            # Load existing or create new
            if self.p.exists():
                loaded = json.loads(self.p.read_text())
                # Migrate old schema if needed
                if "schema" not in loaded:
                    loaded = {"schema": "baselines.v2", **loaded}
                self.data = loaded
            else:
                self.data = {"schema": "baselines.v2"}
    
    def get(self, domain: str, regime: str) -> Optional[Dict]:
        """Get baseline for domain/regime, or None if not set."""
        return self.data.get(domain, {}).get(regime)
    
    def set(self, b: Baseline, force: bool = False):
        """
        Set baseline for domain/regime.
        
        Args:
            b: Baseline object to set
            force: If True, overwrite existing baseline
        
        Returns:
            True if baseline was set, False if baseline already exists and force=False
        """
        if not force and self.exists(b.domain, b.regime):
            return False
        
        self.data.setdefault(b.domain, {})[b.regime] = asdict(b)
        self._save()
        return True
    
    def exists(self, domain: str, regime: str) -> bool:
        """Check if baseline exists for domain/regime."""
        return self.get(domain, regime) is not None
    
    def list_domains(self) -> List[str]:
        """List all domains with baselines."""
        return [k for k in self.data.keys() if k != "schema"]
    
    def list_regimes(self, domain: str) -> List[str]:
        """List all regimes for a domain."""
        return list(self.data.get(domain, {}).keys())
    
    def delete(self, domain: str, regime: str = None):
        """
        Delete baseline(s).
        
        Args:
            domain: Domain name
            regime: If provided, delete specific regime; otherwise delete all regimes for domain
        """
        if regime:
            if domain in self.data and regime in self.data[domain]:
                del self.data[domain][regime]
        else:
            if domain in self.data:
                del self.data[domain]
        self._save()
    
    def get_stats(self) -> Dict:
        """Get statistics about baselines."""
        domains = self.list_domains()
        total_regimes = sum(len(self.list_regimes(d)) for d in domains)
        
        return {
            "schema": self.data.get("schema", "unknown"),
            "total_domains": len(domains),
            "total_regimes": total_regimes,
            "domains": {d: len(self.list_regimes(d)) for d in domains}
        }
    
    def _save(self):
        """Save baselines to disk."""
        self.p.write_text(json.dumps(self.data, indent=2))


def hash_code(files: List[str]) -> str:
    """
    Hash key source files for traceability.
    
    Args:
        files: List of file paths to hash
    
    Returns:
        SHA256 hash with prefix
    """
    h = hashlib.sha256()
    for f in files:
        try:
            h.update(Path(f).read_bytes())
        except FileNotFoundError:
            # File might not exist, skip
            pass
    return "sha256:" + h.hexdigest()[:16]  # Truncate for readability


def create_baseline_from_trials(domain: str, regime: str, kpis: dict, genome: dict, 
                                code_hash: str, timestamp: str = None) -> Baseline:
    """
    Create a Baseline from trial KPIs (averaging arrays).
    
    Args:
        domain: Domain name
        regime: Regime name
        kpis: Dict mapping metric_name -> [values]
        genome: Genome dict
        code_hash: Code hash from manifest
        timestamp: ISO timestamp (generated if not provided)
    
    Returns:
        Baseline object with mean KPIs
    """
    import statistics as st
    
    if timestamp is None:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # Compute means for all KPIs
    mean_kpis = {}
    for metric, values in kpis.items():
        if values:
            mean_kpis[metric] = float(st.mean(values))
        else:
            mean_kpis[metric] = 0.0
    
    return Baseline(
        domain=domain,
        regime=regime,
        genome=genome,
        kpis=mean_kpis,
        code_hash=code_hash,
        timestamp=timestamp
    )


if __name__ == '__main__':
    # Test baseline management
    import statistics as st
    
    # Create test baseline
    kpis_arrays = {
        'perf': [1.0, 1.02, 0.98, 1.01, 1.0, 0.99, 1.01, 1.0, 1.02, 0.99],
        'p95_ms': [10, 11, 10, 10, 11, 10, 10, 11, 10, 10],
        'watts': [50, 51, 50, 50, 51, 50, 50, 51, 50, 50]
    }
    
    baseline = create_baseline_from_trials(
        domain="cpu",
        regime="idle",
        kpis=kpis_arrays,
        genome={"governor": "powersave"},
        code_hash="sha256:test123"
    )
    
    print(f"Created baseline: {baseline.baseline_id}")
    print(f"Mean KPIs: {baseline.kpis}")
    
    # Test baseline storage
    baselines = Baselines(path="/tmp/test_baselines.json")
    if baselines.set(baseline):
        print("✓ Baseline set successfully")
    
    retrieved = baselines.get("cpu", "idle")
    print(f"Retrieved baseline: {retrieved}")
    
    stats = baselines.get_stats()
    print(f"Stats: {stats}")
