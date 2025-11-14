"""
ComparativeAnalyzerScanner - Compares strategy and variant performance.

Analyzes fitness ledger to identify which brainmods, zooid variants,
and strategies consistently outperform alternatives.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class ComparativeAnalyzerScanner(CapabilityScanner):
    """Detects superior strategies via comparative fitness analysis."""

    MIN_SAMPLES_PER_STRATEGY = 10
    SIGNIFICANT_PERFORMANCE_GAP = 0.15
    SIGNIFICANT_SUCCESS_GAP = 0.20

    def __init__(
        self,
        fitness_ledger_path: Path = None,
        cache: 'ObservationCache' = None
    ):
        """
        Initialize scanner with either file path (legacy) or cache (streaming).

        Args:
            fitness_ledger_path: Path to fitness ledger JSONL (legacy)
            cache: ObservationCache instance (streaming mode)
        """
        if cache is not None:
            self.cache = cache
            self.fitness_ledger_path = None
        elif fitness_ledger_path is not None:
            self.cache = None
            self.fitness_ledger_path = fitness_ledger_path
        else:
            self.cache = None
            self.fitness_ledger_path = Path("/home/kloros/.kloros/lineage/fitness_ledger.jsonl")

    def scan(self) -> List[CapabilityGap]:
        """Scan fitness data for superior strategies."""
        gaps = []

        try:
            if self.cache is not None:
                fitness_data = self._load_from_cache()
            else:
                fitness_data = self._load_fitness_data()

            if not fitness_data:
                logger.debug("[comparative_analyzer] No fitness data available")
                return gaps

            brainmod_gaps = self._compare_brainmod_strategies(fitness_data)
            gaps.extend(brainmod_gaps)

            variant_gaps = self._compare_zooid_variants(fitness_data)
            gaps.extend(variant_gaps)

            logger.info(f"[comparative_analyzer] Found {len(gaps)} strategy improvements")

        except Exception as e:
            logger.warning(f"[comparative_analyzer] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='ComparativeAnalyzerScanner',
            domain='introspection',
            alignment_baseline=0.75,
            scan_cost=0.15,
            schedule_weight=0.5
        )

    def _load_fitness_data(self) -> List[Dict[str, Any]]:
        """Load fitness ledger data (7-day window)."""
        if not self.fitness_ledger_path.exists():
            return []

        data = []
        cutoff = time.time() - (7 * 86400)

        try:
            with open(self.fitness_ledger_path, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('ts', 0) >= cutoff:
                            data.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[comparative_analyzer] Failed to load fitness data: {e}")

        return data

    def _load_from_cache(self) -> List[Dict[str, Any]]:
        """
        Load fitness data from observation cache.

        Returns:
            List of fitness records (OBSERVATION facts)
        """
        observations = self.cache.get_recent(seconds=7 * 86400)

        fitness_data = []
        for obs in observations:
            fitness_data.append({
                'ts': obs.get('ts'),
                'zooid_name': obs.get('zooid_name'),
                'ok': obs.get('ok', True),
                'ttr_ms': obs.get('ttr_ms'),
                'incident_id': obs.get('incident_id'),
                'niche': obs.get('niche')
            })

        return fitness_data

    def _compare_brainmod_strategies(
        self,
        fitness_data: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Compare brainmod performance for each zooid type.

        TODO: Currently disabled - fitness ledger does not contain 'brainmod' field.
        Once fitness ledger is extended to track brainmod strategy per zooid,
        implement comparison logic here.
        """
        return []

    def _compare_zooid_variants(
        self,
        fitness_data: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Compare zooid variant performance (e.g., batched vs standard).

        TODO: Currently disabled - fitness ledger does not contain 'variant' field.
        Once fitness ledger is extended to track variant type per zooid,
        implement comparison logic here.
        """
        return []
