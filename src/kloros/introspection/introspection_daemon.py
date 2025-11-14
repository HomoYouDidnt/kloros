#!/usr/bin/env python3
"""
IntrospectionDaemon - Real-time streaming introspection scanner orchestrator.

Subscribes to OBSERVATION events on ChemBus, maintains shared rolling window cache,
runs 5 introspection scanners in thread pool with timeout protection, emits
CapabilityGap objects immediately to CuriosityCore.
"""

import sys
import time
import threading
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parents[3]))

from kloros.orchestration.chem_bus_v2 import ChemSub, ChemPub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode
from kloros.introspection.observation_cache import ObservationCache

sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

from registry.capability_scanners import (
    InferencePerformanceScanner,
    ContextUtilizationScanner,
    ResourceProfilerScanner,
    BottleneckDetectorScanner,
    ComparativeAnalyzerScanner
)

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
            InferencePerformanceScanner(cache=self.cache),
            ContextUtilizationScanner(cache=self.cache),
            ResourceProfilerScanner(cache=self.cache),
            BottleneckDetectorScanner(cache=self.cache),
            ComparativeAnalyzerScanner(cache=self.cache)
        ]

        self.executor = ThreadPoolExecutor(
            max_workers=5,
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

    def run(self) -> None:
        """Main daemon loop - keeps running while subscriber processes events."""
        logger.info("Starting introspection daemon...")

        try:
            while self.running:
                wait_for_normal_mode()
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
