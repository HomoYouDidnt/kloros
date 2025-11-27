"""
ContextUtilizationScanner - Monitors context window usage patterns.

Analyzes Q_INVESTIGATION_COMPLETE events from UMN to track token usage,
detect wasted context, and identify context window optimization opportunities.
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
    logger.warning("NumPy not available, falling back to statistics module for context analysis")

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata
from src.orchestration.core.umn_bus import UMNPub
from src.cognition.mind.cognition.scanner_deduplication import ScannerDeduplicator

logger = logging.getLogger(__name__)


class ContextUtilizationScanner(CapabilityScanner):
    """Detects context utilization optimization opportunities from investigation data."""

    HIGH_TOKEN_THRESHOLD = 50000
    CRITICAL_TOKEN_THRESHOLD = 100000
    LOW_EFFICIENCY_RATIO = 0.1
    MIN_SAMPLES = 3
    HISTORY_WINDOW_HOURS = 6

    def __init__(self):
        """Initialize scanner."""
        self.chem_pub = None

    def scan(self) -> List[CapabilityGap]:
        """Scan for high context usage using UMN investigation history."""
        gaps = []

        try:
            findings = self._scan_umn_history()
            dedup = ScannerDeduplicator("context_utilization")

            if self.chem_pub is None:
                try:
                    self.chem_pub = UMNPub()
                except Exception as e:
                    logger.warning(f"[context_util] Failed to initialize UMNPub: {e}")

            for finding in findings:
                gap = CapabilityGap(
                    type='high_context_usage',
                    name=f"context_inefficiency_{finding.get('pattern', 'unknown')}",
                    category='context_utilization',
                    reason=finding.get('recommendation', 'High context usage detected'),
                    alignment_score=0.65 if finding['severity'] in ['high', 'critical'] else 0.75,
                    install_cost=0.3,
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
                                    "scanner": "context_utilization",
                                    "finding": finding
                                }
                            )
                            logger.info(f"[context_util] Emitted CAPABILITY_GAP_FOUND for {finding['pattern']}")
                        except Exception as e:
                            logger.warning(f"[context_util] Failed to emit signal: {e}")

                    kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
                    findings_dir = Path(kloros_home) / ".kloros/scanner_findings"
                    findings_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
                    findings_file = findings_dir / f"context_{timestamp}.json"
                    findings_file.write_text(json.dumps(finding, indent=2))

            logger.info(f"[context_util] Found {len(gaps)} context inefficiency issues")

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

    def _scan_umn_history(self) -> List[Dict[str, Any]]:
        """Scan UMN history for high context usage patterns."""
        kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
        history_file = Path(kloros_home) / ".kloros/umn_history.jsonl"

        if not history_file.exists():
            logger.warning(f"umn_history.jsonl not found at {history_file}")
            return []

        cutoff_ts = time.time() - (self.HISTORY_WINDOW_HOURS * 3600)
        investigations = []

        with open(history_file, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)

                    if msg.get("ts", 0) < cutoff_ts:
                        continue

                    if msg.get("signal") == "Q_INVESTIGATION_COMPLETE":
                        facts = msg.get("facts", {})
                        if facts.get("status") == "completed":
                            investigations.append(facts)

                except json.JSONDecodeError:
                    continue

        findings = []
        token_usage = defaultdict(list)

        for inv in investigations:
            tokens_used = inv.get("tokens_used", 0)
            duration_ms = inv.get("duration_ms", 0)
            question_id = inv.get("question_id", "unknown")

            if tokens_used > 0:
                token_usage[question_id].append({
                    "tokens_used": tokens_used,
                    "duration_ms": duration_ms
                })

        for question_id, usage_list in token_usage.items():
            if len(usage_list) < self.MIN_SAMPLES:
                continue

            if HAS_NUMPY:
                avg_tokens = float(np.mean([u["tokens_used"] for u in usage_list]))
                max_tokens = float(np.max([u["tokens_used"] for u in usage_list]))
            else:
                tokens = [u["tokens_used"] for u in usage_list]
                avg_tokens = mean(tokens)
                max_tokens = max(tokens)

            if avg_tokens > self.HIGH_TOKEN_THRESHOLD or max_tokens > self.CRITICAL_TOKEN_THRESHOLD:
                severity = "critical" if max_tokens > self.CRITICAL_TOKEN_THRESHOLD else "high"

                if HAS_NUMPY:
                    avg_duration = float(np.mean([u["duration_ms"] for u in usage_list]))
                else:
                    avg_duration = mean([u["duration_ms"] for u in usage_list])

                efficiency_ratio = (avg_duration / 1000) / avg_tokens if avg_tokens > 0 else 0

                findings.append({
                    "type": "high_context_usage",
                    "pattern": question_id,
                    "avg_tokens_used": avg_tokens,
                    "max_tokens_used": max_tokens,
                    "avg_duration_ms": avg_duration,
                    "sample_size": len(usage_list),
                    "efficiency_ratio": efficiency_ratio,
                    "severity": severity,
                    "recommendation": f"Pattern '{question_id}' uses high context (avg: {avg_tokens:.0f} tokens, max: {max_tokens:.0f}). Consider optimizing prompt or splitting into smaller queries."
                })

        return findings
