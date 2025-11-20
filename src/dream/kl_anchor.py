"""
KL Divergence Anchor Model Drift Detection

Measures how much candidate metrics have drifted from baseline/anchor metrics.
Uses metric distribution comparison to detect model degradation or unexpected changes.
"""
import json
import os
from typing import Dict, Any, List
import numpy as np


def load_baseline_metrics(baseline_path: str = None) -> Dict[str, float]:
    """Load baseline/anchor metrics from file."""
    if baseline_path is None:
        baseline_path = "/home/kloros/src/dream/artifacts/baseline_metrics.json"

    if not os.path.exists(baseline_path):
        # No baseline - return empty dict (will skip KL check)
        return {}

    try:
        with open(baseline_path, "r") as f:
            return json.load(f)
    except:
        return {}


def calculate_metric_drift(candidate_metrics: Dict[str, Any], baseline_metrics: Dict[str, float]) -> float:
    """
    Calculate drift score between candidate and baseline metrics.

    Returns a drift score (0.0-1.0+) where:
    - 0.0 = no drift (identical to baseline)
    - 0.1-0.3 = minor drift (acceptable)
    - 0.3-0.5 = moderate drift (borderline)
    - 0.5+ = significant drift (reject)

    This is a practical approximation of KL divergence for scalar metrics.
    """
    if not baseline_metrics:
        # No baseline to compare against
        return 0.0

    # Key metrics to compare
    metrics_to_compare = ["wer", "latency_ms", "vad_boundary_ms", "score"]

    drifts = []

    for metric_name in metrics_to_compare:
        baseline_val = baseline_metrics.get(metric_name)
        candidate_val = candidate_metrics.get(metric_name)

        if baseline_val is None or candidate_val is None:
            continue

        # Avoid division by zero
        if abs(baseline_val) < 1e-6:
            baseline_val = 1e-6

        # Calculate relative drift (normalized)
        relative_drift = abs(candidate_val - baseline_val) / abs(baseline_val)

        drifts.append(relative_drift)

    if not drifts:
        return 0.0

    # Aggregate: mean drift across all metrics
    mean_drift = np.mean(drifts)

    return float(mean_drift)


def passes_kl_anchor_check(candidate_metrics: Dict[str, Any], kl_tau: float) -> bool:
    """
    Check if candidate passes KL anchor drift threshold.

    Args:
        candidate_metrics: Candidate's metrics dictionary
        kl_tau: Maximum allowed drift (0.0-1.0)

    Returns:
        True if drift is within threshold, False if too much drift
    """
    baseline = load_baseline_metrics()

    if not baseline:
        # No baseline - pass by default (can't check drift)
        return True

    drift = calculate_metric_drift(candidate_metrics, baseline)

    return drift <= kl_tau


if __name__ == "__main__":
    # Test KL anchor check
    baseline = {
        "wer": 0.25,
        "latency_ms": 180,
        "vad_boundary_ms": 16,
        "score": 0.85
    }

    # Save test baseline
    with open("/tmp/test_baseline.json", "w") as f:
        json.dump(baseline, f)

    # Test candidate with minor drift
    candidate_ok = {
        "wer": 0.27,  # +8% drift
        "latency_ms": 185,  # +2.8% drift
        "vad_boundary_ms": 17,  # +6.3% drift
        "score": 0.84  # -1.2% drift
    }

    # Test candidate with significant drift
    candidate_bad = {
        "wer": 0.40,  # +60% drift!
        "latency_ms": 300,  # +66.7% drift!
        "vad_boundary_ms": 50,  # +212% drift!
        "score": 0.60  # -29% drift
    }

    drift_ok = calculate_metric_drift(candidate_ok, baseline)
    drift_bad = calculate_metric_drift(candidate_bad, baseline)

    print(f"Minor drift candidate: {drift_ok:.3f} (should be < 0.3)")
    print(f"Significant drift candidate: {drift_bad:.3f} (should be > 0.5)")

    # Test with kl_tau = 0.3
    print(f"\nWith kl_tau=0.3:")
    print(f"  Minor drift passes: {drift_ok <= 0.3}")
    print(f"  Significant drift passes: {drift_bad <= 0.3}")
