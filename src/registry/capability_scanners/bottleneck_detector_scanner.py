"""
BottleneckDetectorScanner - Monitors queue depths and slow operations.

Detects growing queues, lock contention, slow operations, and
processing delays that indicate system bottlenecks.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class BottleneckDetectorScanner(CapabilityScanner):
    """Detects system bottlenecks via queue and operation monitoring."""

    QUEUE_GROWTH_THRESHOLD = 2.0
    QUEUE_SUSTAINED_THRESHOLD = 100
    SLOW_OPERATION_MS = 200
    MIN_SAMPLES = 3

    def __init__(
        self,
        queue_metrics_path: Path = Path("/home/kloros/.kloros/queue_metrics.jsonl"),
        operation_metrics_path: Path = Path("/home/kloros/.kloros/operation_metrics.jsonl")
    ):
        """Initialize scanner with metrics paths."""
        self.queue_metrics_path = queue_metrics_path
        self.operation_metrics_path = operation_metrics_path

    def scan(self) -> List[CapabilityGap]:
        """Scan for bottlenecks in queues and operations."""
        gaps = []

        try:
            queue_metrics = self._load_queue_metrics()
            if queue_metrics:
                queue_gaps = self._analyze_queue_buildup(queue_metrics)
                gaps.extend(queue_gaps)

            op_metrics = self._load_operation_metrics()
            if op_metrics:
                op_gaps = self._analyze_slow_operations(op_metrics)
                gaps.extend(op_gaps)

            logger.info(f"[bottleneck_detector] Found {len(gaps)} bottlenecks")

        except Exception as e:
            logger.warning(f"[bottleneck_detector] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='BottleneckDetectorScanner',
            domain='introspection',
            alignment_baseline=0.8,
            scan_cost=0.20,
            schedule_weight=0.7
        )

    def _load_queue_metrics(self) -> List[Dict[str, Any]]:
        """Load queue depth metrics (7-day window)."""
        if not self.queue_metrics_path.exists():
            return []

        metrics = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.queue_metrics_path, 'r') as f:
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
            logger.warning(f"[bottleneck_detector] Failed to load queue metrics: {e}")

        return metrics

    def _load_operation_metrics(self) -> List[Dict[str, Any]]:
        """Load operation timing metrics (7-day window)."""
        if not self.operation_metrics_path.exists():
            return []

        metrics = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.operation_metrics_path, 'r') as f:
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
            logger.warning(f"[bottleneck_detector] Failed to load operation metrics: {e}")

        return metrics

    def _analyze_queue_buildup(
        self,
        metrics: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Detect growing queue depths."""
        gaps = []

        by_queue = {}
        for entry in metrics:
            queue_name = entry.get('queue', 'unknown')
            if queue_name not in by_queue:
                by_queue[queue_name] = []
            by_queue[queue_name].append(entry)

        for queue_name, queue_data in by_queue.items():
            if len(queue_data) < self.MIN_SAMPLES:
                continue

            queue_data.sort(key=lambda x: x.get('timestamp', 0))

            depths = [q['depth'] for q in queue_data if 'depth' in q]
            if len(depths) < self.MIN_SAMPLES:
                continue

            recent_depths = depths[-5:]
            avg_recent = mean(recent_depths)

            if avg_recent > self.QUEUE_SUSTAINED_THRESHOLD:
                gaps.append(CapabilityGap(
                    type='bottleneck',
                    name=f'queue_buildup_{queue_name}',
                    category='queue_bottleneck',
                    reason=f"Queue '{queue_name}' sustained depth {avg_recent:.0f} (threshold: {self.QUEUE_SUSTAINED_THRESHOLD})",
                    alignment_score=0.8,
                    install_cost=0.4,
                    metadata={
                        'queue': queue_name,
                        'avg_depth': avg_recent,
                        'threshold': self.QUEUE_SUSTAINED_THRESHOLD,
                        'sample_count': len(depths)
                    }
                ))

            if len(depths) >= 4:
                first_half = mean(depths[:len(depths)//2])
                second_half = mean(depths[len(depths)//2:])

                if first_half > 0 and second_half / first_half >= self.QUEUE_GROWTH_THRESHOLD:
                    gaps.append(CapabilityGap(
                        type='bottleneck',
                        name=f'queue_growth_{queue_name}',
                        category='queue_bottleneck',
                        reason=f"Queue '{queue_name}' growing {second_half/first_half:.1f}x (from {first_half:.0f} to {second_half:.0f})",
                        alignment_score=0.75,
                        install_cost=0.35,
                        metadata={
                            'queue': queue_name,
                            'growth_factor': second_half / first_half,
                            'initial_depth': first_half,
                            'current_depth': second_half
                        }
                    ))

        return gaps

    def _analyze_slow_operations(
        self,
        metrics: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Detect consistently slow operations."""
        gaps = []

        by_operation = {}
        for entry in metrics:
            op_name = entry.get('operation', 'unknown')
            if op_name not in by_operation:
                by_operation[op_name] = []
            by_operation[op_name].append(entry)

        for op_name, op_data in by_operation.items():
            if len(op_data) < self.MIN_SAMPLES:
                continue

            durations = [o['duration_ms'] for o in op_data if 'duration_ms' in o]
            if len(durations) < self.MIN_SAMPLES:
                continue

            avg_duration = mean(durations)

            if avg_duration > self.SLOW_OPERATION_MS:
                gaps.append(CapabilityGap(
                    type='bottleneck',
                    name=f'slow_operation_{op_name}',
                    category='operation_bottleneck',
                    reason=f"Slow operation '{op_name}' averaging {avg_duration:.0f}ms (threshold: {self.SLOW_OPERATION_MS}ms)",
                    alignment_score=0.7,
                    install_cost=0.3,
                    metadata={
                        'operation': op_name,
                        'avg_duration_ms': avg_duration,
                        'threshold_ms': self.SLOW_OPERATION_MS,
                        'sample_count': len(durations)
                    }
                ))

        return gaps
