"""
Performance metrics tracking for KLoROS memory system.

Tracks:
- Operation latencies
- Throughput
- Memory usage
- Query performance
"""

from __future__ import annotations

import functools
import logging
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Performance metrics collector."""

    def __init__(self):
        """Initialize metrics collector."""
        self.operation_times: Dict[str, List[float]] = defaultdict(list)
        self.operation_counts: Dict[str, int] = defaultdict(int)
        self.max_history = 1000  # Keep last 1000 measurements

    def record_operation(self, operation: str, duration: float):
        """Record an operation duration."""
        self.operation_counts[operation] += 1
        self.operation_times[operation].append(duration)

        # Trim history
        if len(self.operation_times[operation]) > self.max_history:
            self.operation_times[operation] = self.operation_times[operation][-self.max_history:]

    def get_stats(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """Get performance statistics."""
        if operation:
            times = self.operation_times.get(operation, [])
            if not times:
                return {}

            times_sorted = sorted(times)
            count = len(times)

            return {
                "operation": operation,
                "count": self.operation_counts[operation],
                "avg_ms": sum(times) / count * 1000,
                "p50_ms": times_sorted[count // 2] * 1000,
                "p95_ms": times_sorted[int(count * 0.95)] * 1000 if count > 20 else times_sorted[-1] * 1000,
                "p99_ms": times_sorted[int(count * 0.99)] * 1000 if count > 100 else times_sorted[-1] * 1000,
                "min_ms": min(times) * 1000,
                "max_ms": max(times) * 1000,
            }

        # Return stats for all operations
        all_stats = {}
        for op in self.operation_times.keys():
            all_stats[op] = self.get_stats(op)

        return all_stats


# Global metrics instance
_metrics = PerformanceMetrics()


def get_metrics() -> PerformanceMetrics:
    """Get global metrics instance."""
    return _metrics


def track_performance(operation_name: str) -> Callable:
    """Decorator to track function performance."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                _metrics.record_operation(operation_name, duration)
        return wrapper
    return decorator
