#!/usr/bin/env python3
"""
D-REAM Phase 2: Composite Scoring
Computes multi-objective scores with latency and power penalties.
"""

from typing import Dict, List
import statistics as st


def composite_score(overall_perf: float, overall_p95_ms: float, overall_watts: float) -> float:
    """
    Composite score with explicit penalties for latency and power.
    
    Args:
        overall_perf: Performance metric (higher is better)
        overall_p95_ms: 95th percentile latency in milliseconds (lower is better)
        overall_watts: Power consumption in watts (lower is better)
    
    Returns:
        Composite score (higher is better)
    
    Formula:
        score = perf - 0.2*p95_ms - 0.1*watts
        
    Rationale:
        - Prioritize performance
        - Penalize latency at 20% weight (user-facing responsiveness)
        - Penalize power at 10% weight (efficiency)
    """
    return float(overall_perf - 0.2 * overall_p95_ms - 0.1 * overall_watts)


def compute_regime_means(regimes: List[Dict]) -> Dict[str, Dict[str, float]]:
    """
    Compute per-regime means for each metric.
    
    Args:
        regimes: List of RegimeResult dicts with kpis
    
    Returns:
        Dict mapping metric_name -> {regime_name: mean_value}
    """
    result = {}
    
    # Collect all metrics from all regimes
    all_metrics = set()
    for regime in regimes:
        all_metrics.update(regime.get('kpis', {}).keys())
    
    # Compute means per metric per regime
    for metric in all_metrics:
        result[metric] = {}
        for regime in regimes:
            kpi_values = regime.get('kpis', {}).get(metric, [])
            if kpi_values:
                result[metric][regime['regime']] = st.mean(kpi_values)
            else:
                result[metric][regime['regime']] = 0.0
    
    return result


def compute_overall_means(regime_means: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    Compute overall means across all regimes (equal weighting).
    
    Args:
        regime_means: Dict from compute_regime_means()
    
    Returns:
        Dict mapping metric_name -> overall_mean
    """
    result = {}
    
    for metric, regime_values in regime_means.items():
        if regime_values:
            result[metric] = st.mean(regime_values.values())
        else:
            result[metric] = 0.0
    
    return result


def check_improvement_vs_baseline(regimes: List[Dict], tolerance: Dict[str, float] = None) -> bool:
    """
    Check if candidate improves over baseline across all regimes.
    
    Args:
        regimes: List of RegimeResult dicts with delta arrays
        tolerance: Dict with perf_improvement_pct, latency_regression_pct, power_regression_pct
    
    Returns:
        True if candidate improves (or stays within tolerance) vs baseline in all regimes
    
    Policy:
        - All regimes must have mean(delta_perf) > tolerance
        - All regimes must have mean(delta_p95_ms) <= tolerance
        - All regimes must have mean(delta_watts) <= tolerance
    """
    if tolerance is None:
        tolerance = {
            'perf_improvement_pct': 0.5,
            'latency_regression_pct': 5.0,
            'power_regression_pct': 3.0
        }
    
    for regime in regimes:
        if 'delta' not in regime or not regime['delta']:
            # No baseline comparison available
            continue
        
        delta = regime['delta']
        baseline = regime.get('baseline', {})
        
        # Check performance improvement
        if 'perf' in delta and delta['perf']:
            mean_delta_perf = st.mean(delta['perf'])
            baseline_perf = baseline.get('perf', 1.0)
            
            if baseline_perf > 0:
                pct_improvement = (mean_delta_perf / baseline_perf) * 100
                if pct_improvement < tolerance['perf_improvement_pct']:
                    return False
        
        # Check latency regression
        if 'p95_ms' in delta and delta['p95_ms']:
            mean_delta_p95 = st.mean(delta['p95_ms'])
            baseline_p95 = baseline.get('p95_ms', 1.0)
            
            if baseline_p95 > 0:
                pct_regression = (mean_delta_p95 / baseline_p95) * 100
                if pct_regression > tolerance['latency_regression_pct']:
                    return False
        
        # Check power regression
        if 'watts' in delta and delta['watts']:
            mean_delta_watts = st.mean(delta['watts'])
            baseline_watts = baseline.get('watts', 1.0)
            
            if baseline_watts > 0:
                pct_regression = (mean_delta_watts / baseline_watts) * 100
                if pct_regression > tolerance['power_regression_pct']:
                    return False
    
    return True


def compute_aggregate_score(regimes: List[Dict], tolerance: Dict[str, float] = None) -> Dict:
    """
    Compute aggregate metrics and composite score from regime results.
    
    Args:
        regimes: List of RegimeResult dicts
        tolerance: Tolerance dict for improvement checks
    
    Returns:
        Dict with means, score_v2, and improves_over_baseline
    """
    # Compute per-regime means
    regime_means = compute_regime_means(regimes)
    
    # Compute overall means
    overall_means = compute_overall_means(regime_means)
    
    # Add "overall" to regime_means for each metric
    means_with_overall = {}
    for metric, regime_vals in regime_means.items():
        means_with_overall[metric] = {**regime_vals, 'overall': overall_means[metric]}
    
    # Compute composite score
    overall_perf = overall_means.get('perf', 0.0)
    overall_p95 = overall_means.get('p95_ms', 0.0)
    overall_watts = overall_means.get('watts', 0.0)
    
    score = composite_score(overall_perf, overall_p95, overall_watts)
    
    # Check improvement vs baseline
    improves = check_improvement_vs_baseline(regimes, tolerance)
    
    return {
        'means': means_with_overall,
        'score_v2': score,
        'improves_over_baseline': improves
    }


if __name__ == '__main__':
    # Test with sample data
    sample_regimes = [
        {
            'regime': 'idle',
            'kpis': {
                'perf': [1.0, 1.02, 0.98, 1.01, 1.0, 0.99, 1.01, 1.0, 1.02, 0.99],
                'p95_ms': [10, 11, 10, 10, 11, 10, 10, 11, 10, 10],
                'watts': [50, 51, 50, 50, 51, 50, 50, 51, 50, 50]
            },
            'delta': {
                'perf': [0.0, 0.02, -0.02, 0.01, 0.0, -0.01, 0.01, 0.0, 0.02, -0.01],
                'p95_ms': [0, 1, 0, 0, 1, 0, 0, 1, 0, 0],
                'watts': [0, 1, 0, 0, 1, 0, 0, 1, 0, 0]
            },
            'baseline': {'perf': 1.0, 'p95_ms': 10, 'watts': 50}
        }
    ]
    
    aggregate = compute_aggregate_score(sample_regimes)
    print("Sample aggregate:")
    print(f"  Score v2: {aggregate['score_v2']:.4f}")
    print(f"  Improves: {aggregate['improves_over_baseline']}")
    print(f"  Means: {aggregate['means']}")
