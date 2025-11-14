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
        fitness_ledger_path: Path = Path("/home/kloros/.kloros/lineage/fitness_ledger.jsonl")
    ):
        """Initialize scanner with fitness ledger path."""
        self.fitness_ledger_path = fitness_ledger_path

    def scan(self) -> List[CapabilityGap]:
        """Scan fitness data for superior strategies."""
        gaps = []

        try:
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
                        if entry.get('timestamp', 0) >= cutoff:
                            data.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"[comparative_analyzer] Failed to load fitness data: {e}")

        return data

    def _compare_brainmod_strategies(
        self,
        fitness_data: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Compare brainmod performance for each zooid type."""
        gaps = []

        by_zooid = {}
        for entry in fitness_data:
            if 'brainmod' not in entry:
                continue

            zooid = entry.get('zooid', 'unknown')
            if zooid not in by_zooid:
                by_zooid[zooid] = {}

            brainmod = entry['brainmod']
            if brainmod not in by_zooid[zooid]:
                by_zooid[zooid][brainmod] = []

            by_zooid[zooid][brainmod].append(entry)

        for zooid, strategies in by_zooid.items():
            if len(strategies) < 2:
                continue

            strategy_stats = {}
            for brainmod, entries in strategies.items():
                if len(entries) < self.MIN_SAMPLES_PER_STRATEGY:
                    continue

                successes = [e for e in entries if e.get('success', False)]
                success_rate = len(successes) / len(entries)
                strategy_stats[brainmod] = {
                    'success_rate': success_rate,
                    'sample_count': len(entries)
                }

            if len(strategy_stats) < 2:
                continue

            best = max(strategy_stats.items(), key=lambda x: x[1]['success_rate'])
            worst = min(strategy_stats.items(), key=lambda x: x[1]['success_rate'])

            performance_gap = best[1]['success_rate'] - worst[1]['success_rate']

            if performance_gap >= self.SIGNIFICANT_SUCCESS_GAP:
                gaps.append(CapabilityGap(
                    type='strategy_optimization',
                    name=f'superior_brainmod_{zooid}_{best[0]}',
                    category='brainmod_strategy',
                    reason=f"Brainmod '{best[0]}' outperforms '{worst[0]}' by {performance_gap*100:.1f}% for '{zooid}' tasks ({best[1]['success_rate']*100:.1f}% vs {worst[1]['success_rate']*100:.1f}%)",
                    alignment_score=0.8,
                    install_cost=0.25,
                    metadata={
                        'zooid': zooid,
                        'superior_strategy': best[0],
                        'inferior_strategy': worst[0],
                        'performance_gap': performance_gap,
                        'superior_success_rate': best[1]['success_rate'],
                        'inferior_success_rate': worst[1]['success_rate'],
                        'sample_counts': {best[0]: best[1]['sample_count'], worst[0]: worst[1]['sample_count']}
                    }
                ))

        return gaps

    def _compare_zooid_variants(
        self,
        fitness_data: List[Dict[str, Any]]
    ) -> List[CapabilityGap]:
        """Compare zooid variant performance (e.g., batched vs standard)."""
        gaps = []

        by_zooid = {}
        for entry in fitness_data:
            if 'variant' not in entry or 'ttr_ms' not in entry:
                continue

            zooid = entry.get('zooid', 'unknown')
            if zooid not in by_zooid:
                by_zooid[zooid] = {}

            variant = entry['variant']
            if variant not in by_zooid[zooid]:
                by_zooid[zooid][variant] = []

            by_zooid[zooid][variant].append(entry)

        for zooid, variants in by_zooid.items():
            if len(variants) < 2:
                continue

            variant_stats = {}
            for variant, entries in variants.items():
                if len(entries) < self.MIN_SAMPLES_PER_STRATEGY:
                    continue

                ttrs = [e['ttr_ms'] for e in entries if 'ttr_ms' in e]
                if not ttrs:
                    continue

                avg_ttr = mean(ttrs)
                variant_stats[variant] = {
                    'avg_ttr_ms': avg_ttr,
                    'sample_count': len(ttrs)
                }

            if len(variant_stats) < 2:
                continue

            fastest = min(variant_stats.items(), key=lambda x: x[1]['avg_ttr_ms'])
            slowest = max(variant_stats.items(), key=lambda x: x[1]['avg_ttr_ms'])

            improvement = (slowest[1]['avg_ttr_ms'] - fastest[1]['avg_ttr_ms']) / slowest[1]['avg_ttr_ms']

            if improvement >= self.SIGNIFICANT_PERFORMANCE_GAP:
                gaps.append(CapabilityGap(
                    type='strategy_optimization',
                    name=f'superior_variant_{zooid}_{fastest[0]}',
                    category='zooid_variant',
                    reason=f"Variant '{fastest[0]}' outperforms '{slowest[0]}' by {improvement*100:.1f}% for '{zooid}' ({fastest[1]['avg_ttr_ms']:.0f}ms vs {slowest[1]['avg_ttr_ms']:.0f}ms TTR)",
                    alignment_score=0.75,
                    install_cost=0.3,
                    metadata={
                        'zooid': zooid,
                        'superior_variant': fastest[0],
                        'inferior_variant': slowest[0],
                        'improvement_pct': improvement,
                        'superior_ttr_ms': fastest[1]['avg_ttr_ms'],
                        'inferior_ttr_ms': slowest[1]['avg_ttr_ms'],
                        'sample_counts': {fastest[0]: fastest[1]['sample_count'], slowest[0]: slowest[1]['sample_count']}
                    }
                ))

        return gaps
