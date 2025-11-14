"""
InferencePerformanceScanner - Monitors token generation performance.

Tracks tokens/second, probability distributions, backtracking patterns
to identify inference optimization opportunities.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean, stdev

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class InferencePerformanceScanner(CapabilityScanner):
    """Detects inference performance optimization opportunities."""

    SLOW_TOKENS_PER_SEC = 10.0
    SIGNIFICANT_VARIANCE = 0.3
    MIN_SAMPLES = 3

    def __init__(
        self,
        metrics_path: Path = None,
        cache: 'ObservationCache' = None
    ):
        """
        Initialize scanner with either file path (legacy) or cache (streaming).

        Args:
            metrics_path: Path to inference metrics JSONL (legacy mode)
            cache: ObservationCache instance (streaming mode)
        """
        if cache is not None:
            self.cache = cache
            self.metrics_path = None
        elif metrics_path is not None:
            self.cache = None
            self.metrics_path = metrics_path
        else:
            self.cache = None
            self.metrics_path = Path("/home/kloros/.kloros/metrics/inference_metrics.jsonl")

    def scan(self) -> List[CapabilityGap]:
        """Scan inference metrics for performance optimization opportunities."""
        gaps = []

        try:
            if self.cache is not None:
                metrics = self._load_from_cache()
            else:
                metrics = self._load_inference_metrics()

            if not metrics:
                logger.debug("[inference_perf] No metrics available")
                return gaps

            by_task = self._group_by_task_type(metrics)

            for task_type, task_metrics in by_task.items():
                if len(task_metrics) < self.MIN_SAMPLES:
                    continue

                gap = self._analyze_task_performance(task_type, task_metrics)
                if gap:
                    gaps.append(gap)

            logger.info(f"[inference_perf] Found {len(gaps)} performance gaps")

        except Exception as e:
            logger.warning(f"[inference_perf] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='InferencePerformanceScanner',
            domain='introspection',
            alignment_baseline=0.7,
            scan_cost=0.15,
            schedule_weight=0.6
        )

    def _load_inference_metrics(self) -> List[Dict[str, Any]]:
        """Load inference metrics from disk (7-day window)."""
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
                        timestamp = entry.get('timestamp', 0)
                        if timestamp >= cutoff:
                            metrics.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[inference_perf] Failed to load metrics: {e}")

        return metrics

    def _load_from_cache(self) -> List[Dict[str, Any]]:
        """
        Load inference metrics from observation cache.

        Returns:
            List of inference metric dicts extracted from observation facts
        """
        observations = self.cache.get_recent(seconds=7 * 86400)

        metrics = []
        for obs in observations:
            facts = obs.get('facts', {})

            if 'task_type' in facts and 'tokens_per_sec' in facts:
                metrics.append({
                    'timestamp': facts.get('timestamp', obs.get('ts')),
                    'task_type': facts['task_type'],
                    'tokens_per_sec': facts['tokens_per_sec'],
                    'zooid_name': obs.get('zooid_name')
                })

        return metrics

    def _group_by_task_type(
        self,
        metrics: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group metrics by task type."""
        grouped = {}
        for entry in metrics:
            task_type = entry.get('task_type', 'unknown')
            if task_type not in grouped:
                grouped[task_type] = []
            grouped[task_type].append(entry)
        return grouped

    def _analyze_task_performance(
        self,
        task_type: str,
        metrics: List[Dict[str, Any]]
    ) -> Optional[CapabilityGap]:
        """Analyze performance for a specific task type."""
        tokens_per_sec = [m['tokens_per_sec'] for m in metrics if 'tokens_per_sec' in m]

        if not tokens_per_sec:
            return None

        avg_tps = mean(tokens_per_sec)

        if avg_tps < self.SLOW_TOKENS_PER_SEC:
            return CapabilityGap(
                type='performance_optimization',
                name=f'slow_inference_{task_type}',
                category='inference_performance',
                reason=f"Task type '{task_type}' averaging {avg_tps:.1f} tokens/sec (threshold: {self.SLOW_TOKENS_PER_SEC})",
                alignment_score=0.75,
                install_cost=0.4,
                metadata={
                    'task_type': task_type,
                    'avg_tokens_per_sec': avg_tps,
                    'sample_count': len(tokens_per_sec),
                    'threshold': self.SLOW_TOKENS_PER_SEC
                }
            )

        if len(tokens_per_sec) >= 3:
            variance = stdev(tokens_per_sec) / avg_tps
            if variance > self.SIGNIFICANT_VARIANCE:
                return CapabilityGap(
                    type='performance_optimization',
                    name=f'unstable_inference_{task_type}',
                    category='inference_performance',
                    reason=f"Task type '{task_type}' has {variance*100:.1f}% variance in performance",
                    alignment_score=0.65,
                    install_cost=0.35,
                    metadata={
                        'task_type': task_type,
                        'variance': variance,
                        'avg_tokens_per_sec': avg_tps,
                        'sample_count': len(tokens_per_sec)
                    }
                )

        return None
