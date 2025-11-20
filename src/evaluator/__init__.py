"""Evaluation metrics and dashboards."""

from .metrics import (
    p95, p99, mean, median, stddev,
    success_rate, error_rate, latency_stats,
    compute_delta, format_metric,
    compute_episode_metrics, compare_metrics
)

__all__ = [
    "p95", "p99", "mean", "median", "stddev",
    "success_rate", "error_rate", "latency_stats",
    "compute_delta", "format_metric",
    "compute_episode_metrics", "compare_metrics"
]
