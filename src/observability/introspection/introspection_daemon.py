#!/usr/bin/env python3
"""
IntrospectionDaemon - Real-time streaming introspection scanner orchestrator.

Subscribes to OBSERVATION events on ChemBus, maintains shared rolling window cache,
runs 11 introspection scanners in thread pool with timeout protection, emits
CapabilityGap objects immediately to CuriosityCore.
"""

import sys
import time
import threading
import logging
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import List, Dict, Any
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parents[3]))

from src.orchestration.core.umn_bus import UMNSub as ChemSub, UMNPub as ChemPub
from src.orchestration.maintenance_mode import wait_for_normal_mode
from src.introspection.observation_cache import ObservationCache

sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

from registry.capability_scanners import (
    InferencePerformanceScanner,
    ContextUtilizationScanner,
    ResourceProfilerScanner,
    BottleneckDetectorScanner,
    ComparativeAnalyzerScanner
)
from src.introspection.scanners.service_health_correlator import ServiceHealthCorrelator
from src.introspection.scanners.code_quality_scanner import CodeQualityScanner
from src.introspection.scanners.test_coverage_scanner import TestCoverageScanner
from src.introspection.scanners.performance_profiler_scanner import PerformanceProfilerScanner
from src.introspection.scanners.cross_system_pattern_scanner import CrossSystemPatternScanner
from src.introspection.scanners.documentation_completeness_scanner import DocumentationCompletenessScanner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntrospectionDaemon:
    """
    Streaming introspection daemon with executor pattern for scanner isolation.

    Features:
    - Single ChemBus subscription to OBSERVATION topic
    - Shared ObservationCache (5min rolling window)
    - Thread pool executor for scanner isolation
    - Timeout protection (30s per scanner)
    - Micro-batch analysis (every 5 seconds)
    - Immediate CapabilityGap emission
    """

    def __init__(
        self,
        cache_window_seconds: int = 300,
        scan_interval: float = 5.0,
        scanner_timeout: float = 30.0
    ):
        """
        Initialize introspection daemon.

        Args:
            cache_window_seconds: Rolling window size (default: 5 minutes)
            scan_interval: Seconds between scan cycles (default: 5 seconds)
            scanner_timeout: Timeout per scanner in seconds (default: 30 seconds)
        """
        self.running = True
        self.scan_interval = scan_interval
        self.scanner_timeout = scanner_timeout
        self.scan_count = 0
        self.gap_count = 0
        self.last_scan_ts = 0.0

        self.cache = ObservationCache(window_seconds=cache_window_seconds)

        self.scanners = [
            InferencePerformanceScanner(),
            ContextUtilizationScanner(),
            ResourceProfilerScanner(),
            BottleneckDetectorScanner(),
            ComparativeAnalyzerScanner(),
            ServiceHealthCorrelator(),
            CodeQualityScanner(),
            TestCoverageScanner(),
            PerformanceProfilerScanner(),
            CrossSystemPatternScanner(),
            DocumentationCompletenessScanner()
        ]

        self.executor = ThreadPoolExecutor(
            max_workers=11,
            thread_name_prefix="introspection_scanner_"
        )

        self.sub = ChemSub(
            topic="OBSERVATION",
            on_json=self._on_observation,
            zooid_name="introspection_daemon",
            niche="introspection"
        )

        self.pub = ChemPub()

        logger.info(f"IntrospectionDaemon initialized")
        logger.info(f"  Cache window: {cache_window_seconds}s")
        logger.info(f"  Scan interval: {scan_interval}s")
        logger.info(f"  Scanner timeout: {scanner_timeout}s")
        logger.info(f"  Scanners: {len(self.scanners)}")

    def _on_observation(self, msg: Dict[str, Any]) -> None:
        """
        Callback invoked for each OBSERVATION message from ChemBus.

        Args:
            msg: OBSERVATION message dict with 'facts' containing observation data
        """
        if not self.running:
            return

        try:
            facts = msg.get("facts", {})

            observation = {
                "ts": msg.get("ts", time.time()),
                "zooid_name": facts.get("zooid", facts.get("zooid_name")),
                "niche": facts.get("niche"),
                "ok": facts.get("ok", True),
                "ttr_ms": facts.get("ttr_ms"),
                "incident_id": facts.get("incident_id"),
                "facts": facts
            }

            self.cache.append(observation)

            now = time.time()
            if now - self.last_scan_ts >= self.scan_interval:
                threading.Thread(
                    target=self._run_scan_cycle,
                    daemon=True
                ).start()
                self.last_scan_ts = now

        except Exception as e:
            logger.error(f"Error processing observation: {e}", exc_info=True)

    def _run_scan_cycle(self) -> None:
        """
        Run all scanners over cached observations with timeout protection.

        Each scanner runs in thread pool with timeout. Scanner failures are
        isolated and logged. All detected gaps are emitted immediately.

        After scanning, triggers capability scanners via intents and consolidates
        old ChemBus history to episodic memory.
        """
        try:
            logger.debug(f"Starting scan cycle #{self.scan_count + 1}")

            futures = {}
            for scanner in self.scanners:
                future = self.executor.submit(self._safe_scan, scanner)
                futures[future] = scanner

            all_gaps = []
            for future in futures:
                scanner = futures[future]
                scanner_name = scanner.get_metadata().name

                try:
                    gaps = future.result(timeout=self.scanner_timeout)
                    all_gaps.extend(gaps)
                    logger.debug(f"  {scanner_name}: {len(gaps)} gaps")

                except FutureTimeoutError:
                    logger.error(f"  {scanner_name}: TIMEOUT after {self.scanner_timeout}s")

                except Exception as e:
                    logger.error(f"  {scanner_name}: ERROR - {e}")

            for gap in all_gaps:
                self._emit_capability_gap(gap)

            self.scan_count += 1
            logger.info(f"Scan cycle #{self.scan_count} complete: {len(all_gaps)} gaps emitted")

            self.trigger_scanners_via_intents()
            self.consolidate_chembus_history()

        except Exception as e:
            logger.error(f"Scan cycle failed: {e}", exc_info=True)

    def _safe_scan(self, scanner) -> List:
        """
        Safely execute scanner.scan() with exception handling.

        Args:
            scanner: Scanner instance

        Returns:
            List of CapabilityGap objects (empty list on error)
        """
        try:
            return scanner.scan()
        except Exception as e:
            scanner_name = scanner.get_metadata().name
            logger.error(f"Scanner {scanner_name} failed: {e}", exc_info=True)
            return []

    def _emit_capability_gap(self, gap) -> None:
        """
        Emit CapabilityGap to CuriosityCore via ChemBus.

        Args:
            gap: CapabilityGap object
        """
        try:
            self.pub.emit(
                signal="CAPABILITY_GAP",
                ecosystem="introspection",
                facts={
                    "gap_type": gap.type,
                    "gap_name": gap.name,
                    "gap_category": gap.category,
                    "gap_reason": gap.reason,
                    "alignment_score": gap.alignment_score,
                    "install_cost": gap.install_cost,
                    "metadata": gap.metadata
                }
            )

            self.gap_count += 1
            logger.info(f"  Emitted gap: {gap.category}/{gap.name}")

        except Exception as e:
            logger.error(f"Failed to emit gap: {e}", exc_info=True)

    def trigger_scanners_via_intents(self) -> None:
        """
        Trigger all scanners via intent files for intent_router to process.

        Creates intent files for each scanner that will be picked up by intent_router
        and executed as separate processes.
        """
        scanners = [
            "bottleneck_detector",
            "inference_performance",
            "context_utilization",
            "resource_profiler",
            "comparative_analyzer"
        ]

        for scanner_name in scanners:
            self.pub.emit(
                signal="Q_RUN_SCANNER",
                ecosystem="introspection",
                intensity=1.0,
                facts={
                    "scanner": scanner_name,
                    "triggered_by": "introspection_cycle",
                    "timestamp": time.time()
                }
            )
            logger.info(f"[introspection] Emitted Q_RUN_SCANNER signal for: {scanner_name}")

    def consolidate_chembus_history(self) -> None:
        """
        Consolidate old ChemBus history to episodic memory and prune.

        Moves messages older than 6h to episodic memory with aggregated statistics
        and preserves anomaly signals. Rewrites history file with only recent messages.

        MEMORY OPTIMIZATION: Only consolidates if file > 100MB to avoid loading
        entire file into memory every 5 seconds.
        """
        history_file = Path.home() / ".kloros/chembus_history.jsonl"

        if not history_file.exists():
            logger.debug("[introspection] No chembus_history.jsonl to consolidate")
            return

        # MEMORY FIX: Check file size before loading
        file_size_mb = history_file.stat().st_size / (1024 * 1024)
        if file_size_mb < 100:
            logger.debug(f"[introspection] chembus_history.jsonl only {file_size_mb:.1f}MB, skipping consolidation")
            return

        logger.info(f"[introspection] chembus_history.jsonl is {file_size_mb:.1f}MB, consolidating...")

        cutoff_ts = time.time() - 21600

        old_messages = []
        recent_messages = []

        with open(history_file, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)

                    if msg.get("ts", 0) < cutoff_ts:
                        old_messages.append(msg)
                    else:
                        recent_messages.append(msg)

                except json.JSONDecodeError:
                    continue

        if not old_messages:
            logger.info("[introspection] No old messages to consolidate")
            return

        consolidated = {
            "consolidation_timestamp": time.time(),
            "window_start": min(m.get("ts", 0) for m in old_messages),
            "window_end": cutoff_ts,
            "total_messages": len(old_messages),
            "signals_by_type": defaultdict(int),
            "daemons_active": set(),
            "anomalies": []
        }

        for msg in old_messages:
            signal = msg.get("signal")
            consolidated["signals_by_type"][signal] += 1

            daemon = msg.get("facts", {}).get("daemon")
            if daemon:
                consolidated["daemons_active"].add(daemon)

            if signal in ["BOTTLENECK_DETECTED", "PERFORMANCE_DEGRADED", "CAPABILITY_GAP_FOUND"]:
                consolidated["anomalies"].append({
                    "signal": signal,
                    "ts": msg.get("ts"),
                    "facts": msg.get("facts")
                })

        consolidated["daemons_active"] = list(consolidated["daemons_active"])
        consolidated["signals_by_type"] = dict(consolidated["signals_by_type"])

        episodic_memory_file = Path.home() / ".kloros/episodic_memory/chembus_consolidated.jsonl"
        episodic_memory_file.parent.mkdir(parents=True, exist_ok=True)

        with open(episodic_memory_file, "a") as f:
            f.write(json.dumps(consolidated) + "\n")

        logger.info(f"[introspection] Consolidated {len(old_messages)} old messages to episodic memory")

        with open(history_file, "w") as f:
            for msg in recent_messages:
                f.write(json.dumps(msg, separators=(",", ":")) + "\n")

        logger.info(f"[introspection] Pruned history file, kept {len(recent_messages)} recent messages")

    def run(self) -> None:
        """
        Main daemon loop - proactive introspection with timer-based scanning.

        Runs scans on scan_interval timer (default 5s) AND when observations arrive.
        This makes KLoROS truly autonomous - actively examining the system rather
        than waiting for incidents.
        """
        logger.info("Starting proactive introspection daemon...")
        logger.info(f"Scan interval: {self.scan_interval}s")

        try:
            while self.running:
                wait_for_normal_mode()

                # Proactive scan on timer
                now = time.time()
                if now - self.last_scan_ts >= self.scan_interval:
                    logger.debug(f"Proactive scan triggered (interval={self.scan_interval}s)")
                    threading.Thread(
                        target=self._run_scan_cycle,
                        daemon=True
                    ).start()
                    self.last_scan_ts = now

                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")

        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down introspection daemon...")

        self.running = False

        self.sub.close()
        self.pub.close()

        self.executor.shutdown(wait=True)

        logger.info(f"Introspection daemon stopped")
        logger.info(f"  Total scans: {self.scan_count}")
        logger.info(f"  Total gaps emitted: {self.gap_count}")


def main():
    """Main entry point."""
    daemon = IntrospectionDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
