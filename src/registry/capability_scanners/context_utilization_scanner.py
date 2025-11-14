"""
ContextUtilizationScanner - Monitors context window usage patterns.

Tracks which portions of context get referenced, detects unused context,
recency bias, and context windowing optimization opportunities.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class ContextUtilizationScanner(CapabilityScanner):
    """Detects context utilization optimization opportunities."""

    UNUSED_TAIL_THRESHOLD = 0.7
    RECENCY_BIAS_THRESHOLD = 0.2
    MIN_SAMPLES = 3

    def __init__(
        self,
        metrics_path: Path = None,
        cache: 'ObservationCache' = None
    ):
        """
        Initialize scanner with either file path (legacy) or cache (streaming).

        Args:
            metrics_path: Path to context utilization JSONL (legacy mode)
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
            self.metrics_path = Path("/home/kloros/.kloros/metrics/context_utilization.jsonl")

    def scan(self) -> List[CapabilityGap]:
        """Scan context utilization for optimization opportunities."""
        gaps = []

        try:
            if self.cache is not None:
                logs = self._load_from_cache()
            else:
                logs = self._load_context_logs()

            if len(logs) < self.MIN_SAMPLES:
                logger.debug("[context_util] Insufficient samples")
                return gaps

            unused_tail_gap = self._detect_unused_tail(logs)
            if unused_tail_gap:
                gaps.append(unused_tail_gap)

            recency_bias_gap = self._detect_recency_bias(logs)
            if recency_bias_gap:
                gaps.append(recency_bias_gap)

            logger.info(f"[context_util] Found {len(gaps)} context optimization gaps")

        except Exception as e:
            logger.warning(f"[context_util] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='ContextUtilizationScanner',
            domain='introspection',
            alignment_baseline=0.7,
            scan_cost=0.25,
            schedule_weight=0.5
        )

    def _load_context_logs(self) -> List[Dict[str, Any]]:
        """Load context utilization logs (7-day window)."""
        if not self.metrics_path.exists():
            return []

        logs = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.metrics_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('timestamp', 0) >= cutoff:
                            logs.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[context_util] Failed to load logs: {e}")

        return logs

    def _detect_unused_tail(self, logs: List[Dict[str, Any]]) -> Optional[CapabilityGap]:
        """Detect if last portion of context is consistently unused."""
        max_reference_ratios = []

        for log in logs:
            context_len = log.get('context_length', 0)
            references = log.get('references', [])

            if not context_len or not references:
                continue

            max_ref = max(references)
            ratio = max_ref / context_len
            max_reference_ratios.append(ratio)

        if not max_reference_ratios:
            return None

        avg_max_ref_ratio = mean(max_reference_ratios)

        if avg_max_ref_ratio < self.UNUSED_TAIL_THRESHOLD:
            unused_pct = (1.0 - avg_max_ref_ratio) * 100
            return CapabilityGap(
                type='context_optimization',
                name='unused_context_tail',
                category='context_utilization',
                reason=f"Last {unused_pct:.0f}% of context unused (max ref at {avg_max_ref_ratio*100:.0f}%)",
                alignment_score=0.75,
                install_cost=0.3,
                metadata={
                    'avg_max_reference_ratio': avg_max_ref_ratio,
                    'unused_percentage': unused_pct,
                    'sample_count': len(max_reference_ratios)
                }
            )

        return None

    def _detect_recency_bias(self, logs: List[Dict[str, Any]]) -> Optional[CapabilityGap]:
        """Detect if only recent context is being used."""
        recency_ratios = []

        for log in logs:
            context_len = log.get('context_length', 0)
            references = log.get('references', [])

            if not context_len or not references:
                continue

            cutoff = context_len * 0.8
            recent_refs = [r for r in references if r >= cutoff]
            ratio = len(recent_refs) / len(references) if references else 0
            recency_ratios.append(ratio)

        if not recency_ratios:
            return None

        avg_recency = mean(recency_ratios)

        if avg_recency > 0.8:
            return CapabilityGap(
                type='context_optimization',
                name='recency_bias',
                category='context_utilization',
                reason=f"Recency bias detected: {avg_recency*100:.0f}% of references in last 20% of context",
                alignment_score=0.65,
                install_cost=0.35,
                metadata={
                    'avg_recency_ratio': avg_recency,
                    'sample_count': len(recency_ratios)
                }
            )

        return None

    def _load_from_cache(self) -> List[Dict[str, Any]]:
        """
        Load context utilization logs from observation cache.

        Returns:
            List of context utilization log dicts
        """
        observations = self.cache.get_recent(seconds=7 * 86400)

        logs = []
        for obs in observations:
            facts = obs.get('facts', {})

            if 'context_length' in facts and 'references' in facts:
                logs.append({
                    'timestamp': facts.get('timestamp', obs.get('ts')),
                    'context_length': facts['context_length'],
                    'references': facts['references'],
                    'zooid_name': obs.get('zooid_name')
                })

        return logs
