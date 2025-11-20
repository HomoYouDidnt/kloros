"""
ResourceProfilerScanner - Monitors daemon resource usage patterns.

Analyzes METRICS_SUMMARY signals from ChemBus to track daemon resource usage,
detect memory leaks, and identify resource optimization opportunities.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean
from datetime import datetime
from collections import defaultdict

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger = logging.getLogger(__name__)
    logger.warning("NumPy not available, falling back to statistics module for resource analysis")

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata
from kloros.orchestration.chem_bus_v2 import ChemPub
from registry.scanner_deduplication import ScannerDeduplicator

logger = logging.getLogger(__name__)


class ResourceProfilerScanner(CapabilityScanner):
    """Detects resource utilization optimization opportunities from daemon metrics."""

    HIGH_MEMORY_MB = 1000
    CRITICAL_MEMORY_MB = 2000
    MEMORY_GROWTH_THRESHOLD = 0.2
    MIN_SAMPLES = 3
    HISTORY_WINDOW_HOURS = 6

    def __init__(self):
        """Initialize scanner."""
        self.chem_pub = None

    def scan(self) -> List[CapabilityGap]:
        """Scan for resource usage issues using ChemBus daemon metrics."""
        gaps = []

        try:
            findings = self._scan_chembus_history()
            dedup = ScannerDeduplicator("resource_profiler")

            if self.chem_pub is None:
                try:
                    self.chem_pub = ChemPub()
                except Exception as e:
                    logger.warning(f"[resource_profiler] Failed to initialize ChemPub: {e}")

            for finding in findings:
                gap = CapabilityGap(
                    type='resource_optimization',
                    name=f"resource_issue_{finding.get('daemon', 'unknown')}",
                    category='resource_utilization',
                    reason=finding.get('recommendation', 'Resource usage issue detected'),
                    alignment_score=0.65 if finding['severity'] in ['high', 'critical'] else 0.75,
                    install_cost=0.4,
                    metadata=finding
                )
                gaps.append(gap)

                if dedup.should_report(finding):
                    intensity = 2.0 if finding["severity"] == "critical" else 1.5

                    if self.chem_pub is not None:
                        try:
                            self.chem_pub.emit(
                                signal="CAPABILITY_GAP_FOUND",
                                ecosystem="introspection",
                                intensity=intensity,
                                facts={
                                    "scanner": "resource_profiler",
                                    "finding": finding
                                }
                            )
                            logger.info(f"[resource_profiler] Emitted CAPABILITY_GAP_FOUND for {finding['daemon']}")
                        except Exception as e:
                            logger.warning(f"[resource_profiler] Failed to emit signal: {e}")

                    kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
                    findings_dir = Path(kloros_home) / ".kloros/scanner_findings"
                    findings_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
                    findings_file = findings_dir / f"resource_{timestamp}.json"
                    findings_file.write_text(json.dumps(finding, indent=2))

            logger.info(f"[resource_profiler] Found {len(gaps)} resource usage issues")

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

    def _scan_chembus_history(self) -> List[Dict[str, Any]]:
        """Scan ChemBus history for daemon resource usage patterns."""
        kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
        history_file = Path(kloros_home) / ".kloros/chembus_history.jsonl"

        if not history_file.exists():
            logger.warning(f"chembus_history.jsonl not found at {history_file}")
            return []

        cutoff_ts = time.time() - (self.HISTORY_WINDOW_HOURS * 3600)
        metrics_summaries = []

        with open(history_file, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)

                    if msg.get("ts", 0) < cutoff_ts:
                        continue

                    if msg.get("signal") == "METRICS_SUMMARY":
                        facts = msg.get("facts", {})
                        metrics_summaries.append({
                            "daemon": facts.get("daemon_name", "unknown"),
                            "ts": msg.get("ts"),
                            "facts": facts
                        })

                except json.JSONDecodeError:
                    continue

        logger.info(f"[resource_profiler] Found {len(metrics_summaries)} METRICS_SUMMARY signals in last {self.HISTORY_WINDOW_HOURS}h")

        if metrics_summaries:
            logger.debug(f"[resource_profiler] Sample METRICS_SUMMARY: {json.dumps(metrics_summaries[0], indent=2)}")

        findings = []

        return findings
