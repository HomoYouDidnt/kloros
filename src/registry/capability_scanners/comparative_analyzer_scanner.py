"""
ComparativeAnalyzerScanner - Compares strategy and variant performance.

Analyzes fitness ledger to identify which brainmods, zooid variants,
and strategies consistently outperform alternatives.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean
from collections import defaultdict
from datetime import datetime

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata
from kloros.orchestration.chem_bus_v2 import ChemPub
from registry.scanner_deduplication import ScannerDeduplicator

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
            kloros_home = Path(os.getenv('KLOROS_HOME', '/home/kloros'))
            self.fitness_ledger_path = kloros_home / ".kloros/lineage/fitness_ledger.jsonl"

        self.chem_pub = None

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
        """
        Compare brainmod performance across variants.

        Analyzes which variants of each brainmod perform best and emits
        findings when sufficient data exists.
        """
        gaps = []

        observations = []
        for entry in fitness_data:
            if entry.get('brainmod') and entry.get('variant') is not None:
                observations.append(entry)

        if not observations:
            logger.debug("[comparative_analyzer] No observations with brainmod/variant data")
            return gaps

        brainmod_performance = defaultdict(lambda: {
            "ok": 0,
            "fail": 0,
            "variants": defaultdict(lambda: {"ok": 0, "fail": 0})
        })

        for obs in observations:
            brainmod = obs["brainmod"]
            variant = obs["variant"]
            outcome = "ok" if obs.get("ok", True) else "fail"

            if outcome == "ok":
                brainmod_performance[brainmod]["ok"] += 1
                brainmod_performance[brainmod]["variants"][variant]["ok"] += 1
            else:
                brainmod_performance[brainmod]["fail"] += 1
                brainmod_performance[brainmod]["variants"][variant]["fail"] += 1

        dedup = ScannerDeduplicator("comparative_analyzer")

        if self.chem_pub is None:
            try:
                self.chem_pub = ChemPub()
            except Exception as e:
                logger.warning(f"[comparative_analyzer] Failed to initialize ChemPub: {e}")

        for brainmod, stats in brainmod_performance.items():
            total = stats["ok"] + stats["fail"]
            if total < self.MIN_SAMPLES_PER_STRATEGY:
                continue

            ok_rate = stats["ok"] / total

            best_variant = None
            best_rate = 0

            for variant, vstats in stats["variants"].items():
                vtotal = vstats["ok"] + vstats["fail"]
                if vtotal < 5:
                    continue

                vrate = vstats["ok"] / vtotal
                if vrate > best_rate:
                    best_rate = vrate
                    best_variant = variant

            if best_variant is None:
                continue

            finding = {
                "type": "brainmod_performance",
                "brainmod": brainmod,
                "overall_ok_rate": ok_rate,
                "best_variant": best_variant,
                "best_variant_ok_rate": best_rate,
                "sample_size": total,
                "recommendation": f"Brainmod {brainmod}: variant {best_variant} performing best at {best_rate:.1%}"
            }

            gap = CapabilityGap(
                type='brainmod_performance',
                name=f"brainmod_{brainmod}_best_variant",
                category='performance_optimization',
                reason=finding['recommendation'],
                alignment_score=0.80,
                install_cost=0.2,
                metadata=finding
            )
            gaps.append(gap)

            if dedup.should_report(finding):
                if self.chem_pub is not None:
                    try:
                        self.chem_pub.emit(
                            signal="CAPABILITY_GAP_FOUND",
                            ecosystem="introspection",
                            intensity=1.5,
                            facts={
                                "scanner": "comparative_analyzer",
                                "finding": finding
                            }
                        )
                        logger.info(f"[comparative_analyzer] Emitted CAPABILITY_GAP_FOUND for {brainmod}")
                    except Exception as e:
                        logger.warning(f"[comparative_analyzer] Failed to emit signal: {e}")

                kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
                findings_dir = Path(kloros_home) / ".kloros/scanner_findings"
                findings_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
                findings_file = findings_dir / f"comparative_{timestamp}.json"
                findings_file.write_text(json.dumps(finding, indent=2))

        logger.info(f"[comparative_analyzer] Found {len(gaps)} brainmod performance insights")

        return gaps

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
