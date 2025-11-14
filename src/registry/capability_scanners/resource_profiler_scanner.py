"""
ResourceProfilerScanner - Monitors CPU/GPU/RAM usage per operation.

Tracks resource consumption patterns to identify allocation
optimization opportunities and bottlenecks.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)

try:
    import pynvml
    _GPU_AVAILABLE = True
except ImportError:
    _GPU_AVAILABLE = False
    logger.info("[resource_profiler] nvidia-ml-py not available, GPU monitoring disabled")


class ResourceProfilerScanner(CapabilityScanner):
    """Detects resource utilization optimization opportunities."""

    LOW_GPU_UTIL_THRESHOLD = 50.0
    HIGH_CPU_UTIL_THRESHOLD = 90.0
    MIN_SAMPLES = 3

    def __init__(
        self,
        metrics_path: Path = Path("/home/kloros/.kloros/resource_metrics.jsonl")
    ):
        """Initialize scanner with metrics path."""
        self.metrics_path = metrics_path
        self._gpu_handle = None

        if _GPU_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                logger.warning(f"[resource_profiler] Failed to init GPU monitoring: {e}")

    def scan(self) -> List[CapabilityGap]:
        """Scan resource usage for optimization opportunities."""
        gaps = []

        try:
            metrics = self._load_resource_metrics()

            if len(metrics) < self.MIN_SAMPLES:
                logger.debug("[resource_profiler] Insufficient samples")
                return gaps

            by_operation = self._group_by_operation(metrics)

            for operation, op_metrics in by_operation.items():
                if len(op_metrics) < self.MIN_SAMPLES:
                    continue

                gpu_gap = self._analyze_gpu_utilization(operation, op_metrics)
                if gpu_gap:
                    gaps.append(gpu_gap)

                cpu_gap = self._analyze_cpu_utilization(operation, op_metrics)
                if cpu_gap:
                    gaps.append(cpu_gap)

            logger.info(f"[resource_profiler] Found {len(gaps)} resource optimization gaps")

        except Exception as e:
            logger.warning(f"[resource_profiler] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='ResourceProfilerScanner',
            domain='introspection',
            alignment_baseline=0.75,
            scan_cost=0.25,
            schedule_weight=0.6
        )

    def _load_resource_metrics(self) -> List[Dict[str, Any]]:
        """Load resource metrics from disk (7-day window)."""
        if not self.metrics_path.exists():
            return []

        metrics = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.metrics_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('timestamp', 0) >= cutoff:
                            metrics.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[resource_profiler] Failed to load metrics: {e}")

        return metrics

    def _group_by_operation(
        self,
        metrics: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group metrics by operation type."""
        grouped = {}
        for entry in metrics:
            operation = entry.get('operation', 'unknown')
            if operation not in grouped:
                grouped[operation] = []
            grouped[operation].append(entry)
        return grouped

    def _analyze_gpu_utilization(
        self,
        operation: str,
        metrics: List[Dict[str, Any]]
    ) -> Optional[CapabilityGap]:
        """Analyze GPU utilization for an operation."""
        gpu_utils = [m['gpu_util'] for m in metrics if 'gpu_util' in m]

        if not gpu_utils:
            return None

        avg_gpu = mean(gpu_utils)

        if avg_gpu < self.LOW_GPU_UTIL_THRESHOLD:
            return CapabilityGap(
                type='resource_optimization',
                name=f'low_gpu_util_{operation}',
                category='resource_utilization',
                reason=f"Operation '{operation}' averaging {avg_gpu:.1f}% GPU utilization (threshold: {self.LOW_GPU_UTIL_THRESHOLD}%)",
                alignment_score=0.7,
                install_cost=0.4,
                metadata={
                    'operation': operation,
                    'avg_gpu_util': avg_gpu,
                    'sample_count': len(gpu_utils),
                    'threshold': self.LOW_GPU_UTIL_THRESHOLD
                }
            )

        return None

    def _analyze_cpu_utilization(
        self,
        operation: str,
        metrics: List[Dict[str, Any]]
    ) -> Optional[CapabilityGap]:
        """Analyze CPU utilization for potential bottlenecks."""
        cpu_utils = [m['cpu_util'] for m in metrics if 'cpu_util' in m]

        if not cpu_utils:
            return None

        avg_cpu = mean(cpu_utils)

        if avg_cpu > self.HIGH_CPU_UTIL_THRESHOLD:
            return CapabilityGap(
                type='resource_optimization',
                name=f'cpu_bottleneck_{operation}',
                category='resource_utilization',
                reason=f"Operation '{operation}' averaging {avg_cpu:.1f}% CPU utilization (bottleneck threshold: {self.HIGH_CPU_UTIL_THRESHOLD}%)",
                alignment_score=0.75,
                install_cost=0.35,
                metadata={
                    'operation': operation,
                    'avg_cpu_util': avg_cpu,
                    'sample_count': len(cpu_utils),
                    'threshold': self.HIGH_CPU_UTIL_THRESHOLD
                }
            )

        return None

    def __del__(self):
        """Cleanup GPU resources."""
        if _GPU_AVAILABLE and self._gpu_handle:
            try:
                pynvml.nvmlShutdown()
            except:
                pass
