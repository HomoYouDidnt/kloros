"""
InferencePerformanceScanner - Monitors investigation inference performance.

Analyzes Q_INVESTIGATION_COMPLETE events from UMN to track per-model
performance, identify slow models, and detect performance degradation.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from statistics import mean, stdev
from collections import defaultdict
from datetime import datetime

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger = logging.getLogger(__name__)
    logger.warning("NumPy not available, falling back to statistics module for inference performance analysis")

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata
from src.orchestration.core.umn_bus import UMNPub
from src.cognition.mind.cognition.scanner_deduplication import ScannerDeduplicator

logger = logging.getLogger(__name__)


class InferencePerformanceScanner(CapabilityScanner):
    """Detects slow models and inference performance issues from investigation data."""

    SLOW_AVG_MS = 60000
    CRITICAL_AVG_MS = 120000
    SLOW_P95_MS = 120000
    MIN_SAMPLES = 3
    HISTORY_WINDOW_HOURS = 6

    def __init__(self):
        """Initialize scanner."""
        self.chem_pub = None

    def scan(self) -> List[CapabilityGap]:
        """Scan for slow models using UMN investigation history."""
        gaps = []

        try:
            findings = self._scan_umn_history()
            dedup = ScannerDeduplicator("inference_performance")

            if self.chem_pub is None:
                try:
                    self.chem_pub = UMNPub()
                except Exception as e:
                    logger.warning(f"[inference_perf] Failed to initialize UMNPub: {e}")

            for finding in findings:
                gap = CapabilityGap(
                    type='slow_inference',
                    name=f"slow_model_{finding.get('model', 'unknown')}",
                    category='inference_performance',
                    reason=finding.get('recommendation', 'Slow inference detected'),
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
                                    "scanner": "inference_performance",
                                    "finding": finding
                                }
                            )
                            logger.info(f"[inference_perf] Emitted CAPABILITY_GAP_FOUND for {finding['model']}")
                        except Exception as e:
                            logger.warning(f"[inference_perf] Failed to emit signal: {e}")

                    kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
                    findings_dir = Path(kloros_home) / ".kloros/scanner_findings"
                    findings_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
                    findings_file = findings_dir / f"inference_{timestamp}.json"
                    findings_file.write_text(json.dumps(finding, indent=2))

            logger.info(f"[inference_perf] Found {len(gaps)} slow model issues")

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

    def _scan_umn_history(self) -> List[Dict[str, Any]]:
        """Scan UMN history for slow inference models (optimized reverse read)."""
        kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
        history_file = Path(kloros_home) / ".kloros/umn_history.jsonl"

        if not history_file.exists():
            logger.warning(f"umn_history.jsonl not found at {history_file}")
            return []

        cutoff_ts = time.time() - (self.HISTORY_WINDOW_HOURS * 3600)
        investigations = []
        performance_degraded = []

        try:
            lines_read = 0
            old_lines_skipped = 0

            with open(history_file, "rb") as f:
                f.seek(0, 2)
                file_size = f.tell()
                buffer = bytearray()
                pointer = file_size

                while pointer > 0:
                    chunk_size = min(8192, pointer)
                    pointer -= chunk_size
                    f.seek(pointer)
                    chunk = f.read(chunk_size)

                    buffer = chunk + buffer

                    while b'\n' in buffer:
                        line_end = buffer.rfind(b'\n')
                        if line_end == len(buffer) - 1:
                            buffer = buffer[:line_end]
                            continue

                        line = buffer[line_end + 1:].decode('utf-8', errors='ignore')
                        buffer = buffer[:line_end]

                        if not line.strip():
                            continue

                        try:
                            msg = json.loads(line)
                            lines_read += 1

                            ts = msg.get("ts", 0)
                            if ts < cutoff_ts:
                                old_lines_skipped += 1
                                if old_lines_skipped > 1000:
                                    logger.debug(f"[inference_perf] Stopped reading after {old_lines_skipped} old lines")
                                    pointer = 0
                                    break
                                continue

                            if msg.get("signal") == "Q_INVESTIGATION_COMPLETE":
                                facts = msg.get("facts", {})
                                if facts.get("status") == "completed":
                                    investigations.append(facts)

                            if msg.get("signal") == "PERFORMANCE_DEGRADED":
                                performance_degraded.append(msg)

                        except json.JSONDecodeError:
                            continue

                if buffer:
                    try:
                        line = buffer.decode('utf-8', errors='ignore').strip()
                        if line:
                            msg = json.loads(line)
                            if msg.get("ts", 0) >= cutoff_ts:
                                if msg.get("signal") == "Q_INVESTIGATION_COMPLETE":
                                    facts = msg.get("facts", {})
                                    if facts.get("status") == "completed":
                                        investigations.append(facts)
                                if msg.get("signal") == "PERFORMANCE_DEGRADED":
                                    performance_degraded.append(msg)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass

            logger.debug(f"[inference_perf] Scanned {lines_read} lines, found {len(investigations)} investigations")

        except Exception as e:
            logger.warning(f"[inference_perf] Error reading history file: {e}")

        findings = []
        model_timings = defaultdict(list)

        for inv in investigations:
            model = inv.get("model_used")
            duration = inv.get("duration_ms")

            if model and duration and model != "unknown":
                model_timings[model].append(duration)

        for model, timings in model_timings.items():
            if len(timings) < self.MIN_SAMPLES:
                continue

            if HAS_NUMPY:
                avg_ms = float(np.mean(timings))
                p95_ms = float(np.percentile(timings, 95))
            else:
                avg_ms = mean(timings)
                sorted_timings = sorted(timings)
                p95_index = int(len(sorted_timings) * 0.95)
                p95_ms = sorted_timings[p95_index] if p95_index < len(sorted_timings) else sorted_timings[-1]

            if avg_ms > self.SLOW_AVG_MS or p95_ms > self.SLOW_P95_MS:
                severity = "critical" if avg_ms > self.CRITICAL_AVG_MS else "high"

                degraded_count = sum(
                    1 for msg in performance_degraded
                    if msg.get("facts", {}).get("model") == model
                )

                findings.append({
                    "type": "slow_inference",
                    "model": model,
                    "avg_duration_ms": avg_ms,
                    "p95_duration_ms": p95_ms,
                    "sample_size": len(timings),
                    "severity": severity,
                    "performance_degraded_count": degraded_count,
                    "recommendation": f"Model {model} is slow (avg: {avg_ms/1000:.1f}s, p95: {p95_ms/1000:.1f}s). Consider switching to faster model or increasing timeout."
                })

        return findings
