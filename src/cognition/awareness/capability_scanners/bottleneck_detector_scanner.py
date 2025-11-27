"""
BottleneckDetectorScanner - Monitors queue depths and slow operations.

Detects growing queues, lock contention, slow operations, and
processing delays that indicate system bottlenecks.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Any
from statistics import mean
from datetime import datetime

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger = logging.getLogger(__name__)
    logger.warning("NumPy not available, falling back to statistics.mean for bottleneck detection")

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata
from src.orchestration.core.umn_bus import UMNPub
from src.cognition.mind.cognition.scanner_deduplication import ScannerDeduplicator

logger = logging.getLogger(__name__)


class BottleneckDetectorScanner(CapabilityScanner):
    """Detects system bottlenecks via queue and operation monitoring."""

    QUEUE_GROWTH_THRESHOLD = 2.0
    QUEUE_SUSTAINED_THRESHOLD = 100
    SLOW_OPERATION_MS = 200
    MIN_SAMPLES = 3

    def __init__(self):
        """Initialize scanner."""
        self.chem_pub = None

    def scan(self) -> List[CapabilityGap]:
        """Scan for bottlenecks using UMN history."""
        gaps = []

        try:
            bottlenecks = self._scan_umn_history()
            dedup = ScannerDeduplicator("bottleneck_detector")

            if self.chem_pub is None:
                try:
                    self.chem_pub = UMNPub()
                except Exception as e:
                    logger.warning(f"[bottleneck_detector] Failed to initialize UMNPub: {e}")

            for bottleneck in bottlenecks:
                gap = CapabilityGap(
                    type='bottleneck',
                    name=f"{bottleneck['type']}_{bottleneck.get('daemon', 'system')}",
                    category='bottleneck',
                    reason=bottleneck.get('recommendation', 'Bottleneck detected'),
                    alignment_score=0.7 if bottleneck['severity'] in ['high', 'critical'] else 0.8,
                    install_cost=0.3,
                    metadata=bottleneck
                )
                gaps.append(gap)

                if dedup.should_report(bottleneck):
                    intensity = 2.0 if bottleneck["severity"] == "critical" else 1.5

                    if self.chem_pub is not None:
                        try:
                            self.chem_pub.emit(
                                signal="CAPABILITY_GAP_FOUND",
                                ecosystem="introspection",
                                intensity=intensity,
                                facts={
                                    "scanner": "bottleneck_detector",
                                    "finding": bottleneck
                                }
                            )
                            logger.info(f"[bottleneck_detector] Emitted CAPABILITY_GAP_FOUND for {bottleneck['type']}")
                        except Exception as e:
                            logger.warning(f"[bottleneck_detector] Failed to emit signal: {e}")

                    kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
                    findings_dir = Path(kloros_home) / ".kloros/scanner_findings"
                    findings_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
                    findings_file = findings_dir / f"bottleneck_{timestamp}.json"
                    findings_file.write_text(json.dumps(bottleneck, indent=2))

            logger.info(f"[bottleneck_detector] Found {len(gaps)} bottlenecks")

        except Exception as e:
            logger.warning(f"[bottleneck_detector] Scan failed: {e}")

        return gaps

    def _scan_umn_history(self) -> List[Dict[str, Any]]:
        """Scan for bottlenecks using UMN history."""
        kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
        history_file = Path(kloros_home) / ".kloros/umn_history.jsonl"

        if not history_file.exists():
            logger.warning(f"umn_history.jsonl not found at {history_file}")
            return []

        cutoff_ts = time.time() - 3600
        metrics_summaries = []
        queue_events = []

        with open(history_file, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)

                    if msg.get("ts", 0) < cutoff_ts:
                        continue

                    if msg.get("signal") == "METRICS_SUMMARY" and \
                       msg.get("facts", {}).get("daemon") == "investigation_consumer":
                        metrics_summaries.append(msg)

                    if msg.get("signal") in ["BOTTLENECK_DETECTED", "Q_INVESTIGATION_COMPLETE"]:
                        queue_events.append(msg)

                except json.JSONDecodeError:
                    continue

        bottlenecks = []

        queue_depths = [m["facts"]["queue_depth_current"]
                       for m in metrics_summaries
                       if "queue_depth_current" in m.get("facts", {})]

        if queue_depths:
            avg_depth = float(np.mean(queue_depths)) if HAS_NUMPY else mean(queue_depths)
            if avg_depth > 30:
                bottlenecks.append({
                    "type": "queue_buildup",
                    "daemon": "investigation_consumer",
                    "severity": "high" if avg_depth > 50 else "medium",
                    "issue": f"Queue depth avg {avg_depth:.1f}",
                    "avg_queue_depth": avg_depth,
                    "max_queue_depth": int(max(queue_depths)),
                    "recommendation": "Investigation consumer may need more workers or faster model"
                })

        completed = sum(m["facts"].get("investigations_completed", 0)
                       for m in metrics_summaries)
        failed = sum(m["facts"].get("investigations_failed", 0)
                    for m in metrics_summaries)

        total = completed + failed
        if total > 0 and (failed / total) > 0.2:
            bottlenecks.append({
                "type": "high_failure_rate",
                "daemon": "investigation_consumer",
                "severity": "critical",
                "issue": f"Failure rate {(failed/total)*100:.1f}%",
                "failure_rate": float(failed / total),
                "completed": completed,
                "failed": failed,
                "recommendation": "Investigate investigation failures - may indicate LLM issues or bad questions"
            })

        return bottlenecks

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='BottleneckDetectorScanner',
            domain='introspection',
            alignment_baseline=0.8,
            scan_cost=0.20,
            schedule_weight=0.7
        )
