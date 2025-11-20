"""Common evaluation metrics for cognitive systems."""
from typing import List, Dict, Any, Optional
import statistics


def p95(values: List[float]) -> float:
    """Compute 95th percentile.

    Args:
        values: List of values

    Returns:
        95th percentile value
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = max(0, int(0.95 * len(sorted_values)) - 1)
    return sorted_values[index]


def p99(values: List[float]) -> float:
    """Compute 99th percentile.

    Args:
        values: List of values

    Returns:
        99th percentile value
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = max(0, int(0.99 * len(sorted_values)) - 1)
    return sorted_values[index]


def mean(values: List[float]) -> float:
    """Compute mean.

    Args:
        values: List of values

    Returns:
        Mean value
    """
    if not values:
        return 0.0
    return statistics.mean(values)


def median(values: List[float]) -> float:
    """Compute median.

    Args:
        values: List of values

    Returns:
        Median value
    """
    if not values:
        return 0.0
    return statistics.median(values)


def stddev(values: List[float]) -> float:
    """Compute standard deviation.

    Args:
        values: List of values

    Returns:
        Standard deviation
    """
    if not values or len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def success_rate(results: List[Dict[str, Any]]) -> float:
    """Compute success rate from results.

    Args:
        results: List of result dicts with 'success' key

    Returns:
        Success rate [0,1]
    """
    if not results:
        return 0.0

    successes = sum(1 for r in results if r.get("success", False))
    return successes / len(results)


def error_rate(results: List[Dict[str, Any]]) -> float:
    """Compute error rate from results.

    Args:
        results: List of result dicts with 'success' key

    Returns:
        Error rate [0,1]
    """
    return 1.0 - success_rate(results)


def latency_stats(results: List[Dict[str, Any]], key: str = "latency_ms") -> Dict[str, float]:
    """Compute latency statistics.

    Args:
        results: List of result dicts
        key: Key for latency value

    Returns:
        Dict with mean, median, p95, p99, stddev
    """
    latencies = [r[key] for r in results if key in r]

    if not latencies:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "stddev": 0.0,
            "min": 0.0,
            "max": 0.0
        }

    return {
        "mean": mean(latencies),
        "median": median(latencies),
        "p95": p95(latencies),
        "p99": p99(latencies),
        "stddev": stddev(latencies),
        "min": min(latencies),
        "max": max(latencies)
    }


def compute_delta(baseline: float, candidate: float, as_percentage: bool = True) -> float:
    """Compute delta between baseline and candidate.

    Args:
        baseline: Baseline value
        candidate: Candidate value
        as_percentage: Return as percentage (default) or absolute

    Returns:
        Delta value
    """
    if baseline == 0:
        return 0.0

    delta = candidate - baseline

    if as_percentage:
        return (delta / baseline) * 100

    return delta


def format_metric(value: float, metric_type: str = "number") -> str:
    """Format metric for display.

    Args:
        value: Metric value
        metric_type: Type of metric (number, percentage, latency, rate)

    Returns:
        Formatted string
    """
    if metric_type == "percentage":
        return f"{value:.2f}%"
    elif metric_type == "latency":
        return f"{value:.1f}ms"
    elif metric_type == "rate":
        return f"{value:.3f}"
    else:
        return f"{value:.2f}"


def compute_episode_metrics(episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute comprehensive metrics from episodes.

    Args:
        episodes: List of episode records

    Returns:
        Metrics dict
    """
    if not episodes:
        return {
            "total_episodes": 0,
            "success_rate": 0.0,
            "error_rate": 0.0
        }

    # Extract results
    results = []
    latencies = []
    tokens = []
    tool_calls = []
    petri_blocks = 0

    for episode in episodes:
        success = episode.get("success", False)
        results.append({"success": success})

        if "latency_ms" in episode:
            latencies.append(episode["latency_ms"])

        if "tokens" in episode:
            tokens.append(episode["tokens"])

        if "tool_calls" in episode:
            tool_calls.append(episode["tool_calls"])

        if episode.get("petri_blocked", False):
            petri_blocks += 1

    metrics = {
        "total_episodes": len(episodes),
        "success_rate": success_rate(results),
        "error_rate": error_rate(results),
        "petri_blocks": petri_blocks
    }

    if latencies:
        metrics["latency"] = latency_stats([{"latency_ms": l} for l in latencies])

    if tokens:
        metrics["tokens"] = {
            "mean": mean(tokens),
            "median": median(tokens),
            "p95": p95(tokens),
            "stddev": stddev(tokens)
        }

    if tool_calls:
        metrics["tool_calls"] = {
            "mean": mean(tool_calls),
            "median": median(tool_calls),
            "p95": p95(tool_calls)
        }

    return metrics


def compare_metrics(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Compare metrics between baseline and candidate.

    Args:
        baseline: Baseline metrics
        candidate: Candidate metrics

    Returns:
        Comparison dict with deltas
    """
    comparison = {
        "baseline": baseline,
        "candidate": candidate,
        "deltas": {}
    }

    # Success rate delta (in percentage points)
    baseline_sr = baseline.get("success_rate", 0)
    candidate_sr = candidate.get("success_rate", 0)
    comparison["deltas"]["success_rate_pp"] = (candidate_sr - baseline_sr) * 100

    # Latency delta (as percentage)
    if "latency" in baseline and "latency" in candidate:
        baseline_lat = baseline["latency"].get("p95", 0)
        candidate_lat = candidate["latency"].get("p95", 0)
        comparison["deltas"]["p95_latency_pct"] = compute_delta(baseline_lat, candidate_lat)

    # Token delta (as percentage)
    if "tokens" in baseline and "tokens" in candidate:
        baseline_tok = baseline["tokens"].get("mean", 0)
        candidate_tok = candidate["tokens"].get("mean", 0)
        comparison["deltas"]["tokens_pct"] = compute_delta(baseline_tok, candidate_tok)

    # PETRI blocks delta (absolute)
    baseline_blocks = baseline.get("petri_blocks", 0)
    candidate_blocks = candidate.get("petri_blocks", 0)
    comparison["deltas"]["petri_blocks"] = candidate_blocks - baseline_blocks

    return comparison
