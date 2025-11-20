#!/usr/bin/env python3
"""
Statistical utilities for D-REAM confidence interval computation.
Phase 2: Added seed support for reproducibility.
"""

import random
import statistics as st
from typing import List, Tuple, Optional


def bootstrap_ci(vals: List[float], iters: int = 2000, alpha: float = 0.05, seed: Optional[int] = None) -> Tuple[float, float]:
    """
    Compute bootstrap confidence interval for mean.
    
    Args:
        vals: Sample values
        iters: Number of bootstrap iterations
        alpha: Significance level (0.05 = 95% CI)
        seed: Random seed for reproducibility
    
    Returns:
        (lower_bound, upper_bound) tuple
    """
    if not vals or len(vals) < 2:
        # Not enough data for CI
        return (vals[0] if vals else 0.0, vals[0] if vals else 0.0)
    
    # Set seed for reproducibility if provided
    if seed is not None:
        random.seed(seed)
    
    n = len(vals)
    samples = [st.mean(random.choices(vals, k=n)) for _ in range(iters)]
    samples.sort()
    
    lo_idx = int((alpha / 2) * iters)
    hi_idx = int((1 - alpha / 2) * iters)
    
    return samples[lo_idx], samples[hi_idx]


def bootstrap_ci_median(vals: List[float], iters: int = 2000, alpha: float = 0.05, seed: Optional[int] = None) -> Tuple[float, float]:
    """
    Compute bootstrap confidence interval for median.
    
    Args:
        vals: Sample values
        iters: Number of bootstrap iterations  
        alpha: Significance level (0.05 = 95% CI)
        seed: Random seed for reproducibility
    
    Returns:
        (lower_bound, upper_bound) tuple
    """
    if not vals or len(vals) < 2:
        return (vals[0] if vals else 0.0, vals[0] if vals else 0.0)
    
    if seed is not None:
        random.seed(seed)
    
    n = len(vals)
    samples = [st.median(random.choices(vals, k=n)) for _ in range(iters)]
    samples.sort()
    
    lo_idx = int((alpha / 2) * iters)
    hi_idx = int((1 - alpha / 2) * iters)
    
    return samples[lo_idx], samples[hi_idx]


def compute_effect_size(treatment: List[float], baseline: float, seed: Optional[int] = None) -> dict:
    """
    Compute effect size metrics.
    
    Args:
        treatment: Treatment group measurements
        baseline: Baseline value
        seed: Random seed for CI computation
    
    Returns:
        Dict with mean, median, ci95, and delta metrics
    """
    if not treatment:
        return {
            "mean": 0.0,
            "median": 0.0,
            "ci95": [0.0, 0.0],
            "delta_mean": 0.0,
            "delta_pct": 0.0
        }
    
    mean_val = st.mean(treatment)
    median_val = st.median(treatment)
    ci_lo, ci_hi = bootstrap_ci(treatment, seed=seed)
    
    delta = mean_val - baseline
    delta_pct = (delta / baseline * 100) if baseline != 0 else 0.0
    
    return {
        "mean": mean_val,
        "median": median_val,
        "ci95": [ci_lo, ci_hi],
        "delta_mean": delta,
        "delta_pct": delta_pct
    }


def compute_cis_for_metrics(kpis: dict, seed: Optional[int] = None) -> dict:
    """
    Compute 95% CIs for all metrics in a KPI dictionary.
    
    Args:
        kpis: Dict mapping metric_name -> [values]
        seed: Random seed for reproducibility
    
    Returns:
        Dict mapping metric_name -> [ci_lo, ci_hi]
    """
    cis = {}
    for metric, values in kpis.items():
        if values and len(values) >= 2:
            ci_lo, ci_hi = bootstrap_ci(values, seed=seed)
            cis[metric] = [float(ci_lo), float(ci_hi)]
        elif values and len(values) == 1:
            # Single value - no CI
            cis[metric] = [float(values[0]), float(values[0])]
        else:
            cis[metric] = [0.0, 0.0]
    
    return cis


if __name__ == '__main__':
    # Test with sample data
    import numpy as np
    
    np.random.seed(1337)
    vals = list(np.random.normal(1.0, 0.1, 10))
    
    ci_lo, ci_hi = bootstrap_ci(vals, seed=1337)
    print(f"Sample CI: [{ci_lo:.4f}, {ci_hi:.4f}]")
    
    effect = compute_effect_size(vals, 1.0, seed=1337)
    print(f"Effect size: {effect}")
    
    kpis = {
        'perf': vals,
        'p95_ms': [10, 11, 10, 10, 11, 10, 10, 11, 10, 10],
        'watts': [50, 51, 50, 50, 51, 50, 50, 51, 50, 50]
    }
    cis = compute_cis_for_metrics(kpis, seed=1337)
    print(f"CIs for metrics: {cis}")
