"""
Shadow Mode Daemon - Real-World 24h Validation

Runs legacy and wrapper implementations in parallel with real-world timing,
logging wrapper output while applying legacy output. Streams metrics for
auto-promotion decision.

Architecture:
- Parallel execution: legacy (applied) + wrapper (logged)
- Real-time drift monitoring
- Metrics streaming to JSON
- Auto-promotion criteria checking
"""

import time
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from kloros.dream.shadow_mode import ShadowModeExecutor, ShadowModeMonitor
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logger = logging.getLogger(__name__)


@dataclass
class ShadowMetrics:
    """Real-time shadow mode metrics."""
    niche: str
    start_time: float
    elapsed_hours: float
    total_executions: int
    successful_executions: int
    failed_executions: int
    max_drift_percentage: float
    avg_drift_percentage: float
    current_drift_percentage: float
    legacy_error_count: int
    wrapper_error_count: int
    rollback_triggered: bool
    promotion_eligible: bool
    last_updated: float


class ShadowModeDaemon:
    """
    Daemon that runs shadow mode validation for 24 hours.

    Executes both legacy and wrapper implementations in parallel,
    streams metrics, and checks for auto-promotion eligibility.
    """

    def __init__(
        self,
        niche: str,
        legacy_factory: callable,
        wrapper_factory: callable,
        metrics_path: Path = None,
        duration_hours: float = 24.0,
    ):
        self.niche = niche
        self.legacy_factory = legacy_factory
        self.wrapper_factory = wrapper_factory
        self.duration_hours = duration_hours

        self.metrics_path = metrics_path or Path.home() / ".kloros" / "metrics" / f"shadow_{niche}.json"
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

        self.executor = ShadowModeExecutor()
        self.monitor = ShadowModeMonitor()

        self.running = True
        self.start_time = None
        self.legacy_instance = None
        self.wrapper_instance = None

        self.drift_threshold = 0.01
        self.rollback_threshold = 20.0
        self.error_rate_threshold = 0.05

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        logger.info(f"Received signal {signum}, shutting down shadow mode daemon...")
        self.running = False

    def run(self):
        """
        Main daemon loop - runs for 24 hours or until stopped.
        """
        logger.info(f"Starting shadow mode daemon for {self.niche}")
        logger.info(f"  Duration: {self.duration_hours}h")
        logger.info(f"  Metrics: {self.metrics_path}")
        logger.info(f"  Drift threshold: {self.drift_threshold}%")
        logger.info(f"  Rollback threshold: {self.rollback_threshold}%")

        self.start_time = time.time()
        end_time = self.start_time + (self.duration_hours * 3600)

        self.legacy_instance = self.legacy_factory()
        self.wrapper_instance = self.wrapper_factory()

        execution_count = 0
        drift_values = []
        error_counts = {"legacy": 0, "wrapper": 0}

        while self.running and time.time() < end_time:
            try:
                # Check maintenance mode before continuing
                wait_for_normal_mode()

                now = time.time()

                execution = self._execute_shadow_tick(now)

                execution_count += 1
                drift_values.append(execution.drift_percentage)

                if execution.legacy_error:
                    error_counts["legacy"] += 1
                if execution.wrapper_error:
                    error_counts["wrapper"] += 1

                max_drift = max(drift_values) if drift_values else 0.0
                avg_drift = sum(drift_values) / len(drift_values) if drift_values else 0.0

                rollback = max_drift >= self.rollback_threshold
                if rollback:
                    logger.error(f"🚨 ROLLBACK TRIGGERED: Max drift {max_drift:.2f}% exceeds threshold {self.rollback_threshold}%")
                    self._save_metrics(
                        execution_count=execution_count,
                        drift_values=drift_values,
                        error_counts=error_counts,
                        rollback_triggered=True,
                    )
                    return 1

                elapsed_hours = (now - self.start_time) / 3600
                promotion_eligible = (
                    elapsed_hours >= self.duration_hours
                    and avg_drift <= self.drift_threshold
                    and error_counts["wrapper"] / max(execution_count, 1) < self.error_rate_threshold
                )

                if execution_count % 10 == 0:
                    logger.info(
                        f"Shadow progress: {elapsed_hours:.2f}h / {self.duration_hours}h, "
                        f"{execution_count} executions, "
                        f"avg drift {avg_drift:.4f}%, "
                        f"max drift {max_drift:.4f}%"
                    )

                if execution_count % 60 == 0:
                    self._save_metrics(
                        execution_count=execution_count,
                        drift_values=drift_values,
                        error_counts=error_counts,
                        rollback_triggered=False,
                    )

                time.sleep(60)

            except Exception as e:
                logger.error(f"Error in shadow mode loop: {e}", exc_info=True)
                time.sleep(60)

        final_elapsed = (time.time() - self.start_time) / 3600
        logger.info(f"Shadow mode complete after {final_elapsed:.2f}h")

        self._save_metrics(
            execution_count=execution_count,
            drift_values=drift_values,
            error_counts=error_counts,
            rollback_triggered=False,
            final=True,
        )

        return 0

    def _execute_shadow_tick(self, now: float):
        """Execute one shadow tick through both implementations."""
        if self.niche == "maintenance_housekeeping":
            def wrapper_callable():
                tick_result = self.wrapper_instance.tick(now)
                return tick_result.get("result") if tick_result.get("status") == "success" else None

            return self.executor.execute_shadow(
                niche=self.niche,
                legacy_callable=lambda: self.legacy_instance.run_scheduled_maintenance(),
                wrapper_callable=wrapper_callable,
            )
        elif self.niche == "observability_logging":
            def wrapper_callable():
                tick_result = self.wrapper_instance.tick(now)
                return tick_result.get("result") if tick_result.get("status") == "success" else None

            return self.executor.execute_shadow(
                niche=self.niche,
                legacy_callable=lambda: {"daemon_running": self.legacy_instance.running, "event_count": self.legacy_instance.event_count},
                wrapper_callable=wrapper_callable,
            )
        else:
            raise ValueError(f"Unknown niche: {self.niche}")

    def _save_metrics(
        self,
        execution_count: int,
        drift_values: list,
        error_counts: dict,
        rollback_triggered: bool,
        final: bool = False,
    ):
        """Save current metrics to disk."""
        now = time.time()
        elapsed_hours = (now - self.start_time) / 3600

        max_drift = max(drift_values) if drift_values else 0.0
        avg_drift = sum(drift_values) / len(drift_values) if drift_values else 0.0
        current_drift = drift_values[-1] if drift_values else 0.0

        successful = execution_count - error_counts["legacy"] - error_counts["wrapper"]

        promotion_eligible = (
            elapsed_hours >= self.duration_hours
            and avg_drift <= self.drift_threshold
            and error_counts["wrapper"] / max(execution_count, 1) < self.error_rate_threshold
            and not rollback_triggered
        )

        metrics = ShadowMetrics(
            niche=self.niche,
            start_time=self.start_time,
            elapsed_hours=elapsed_hours,
            total_executions=execution_count,
            successful_executions=successful,
            failed_executions=error_counts["legacy"] + error_counts["wrapper"],
            max_drift_percentage=max_drift,
            avg_drift_percentage=avg_drift,
            current_drift_percentage=current_drift,
            legacy_error_count=error_counts["legacy"],
            wrapper_error_count=error_counts["wrapper"],
            rollback_triggered=rollback_triggered,
            promotion_eligible=promotion_eligible,
            last_updated=now,
        )

        with open(self.metrics_path, 'w') as f:
            json.dump(asdict(metrics), f, indent=2)

        if final:
            logger.info(f"{'✅' if promotion_eligible else '❌'} Final metrics: {promotion_eligible=}, avg_drift={avg_drift:.4f}%")


def main_maintenance_housekeeping():
    """Run shadow mode for maintenance_housekeeping."""
    from housekeeping_scheduler import HousekeepingScheduler
    from zooids.wrappers.maintenance_housekeeping_v0_wrapper import HousekeepingZooid

    class MockKLoROS:
        def __init__(self):
            self.memory_system = None

    def legacy_factory():
        return HousekeepingScheduler(kloros_instance=MockKLoROS())

    def wrapper_factory():
        return HousekeepingZooid()

    daemon = ShadowModeDaemon(
        niche="maintenance_housekeeping",
        legacy_factory=legacy_factory,
        wrapper_factory=wrapper_factory,
    )

    return daemon.run()


def main_observability_logging():
    """Run shadow mode for observability_logging."""
    from kloros.observability.ledger_writer_daemon import LedgerWriterDaemon
    from zooids.wrappers.observability_logging_v0_wrapper import LedgerWriterZooid

    def legacy_factory():
        return LedgerWriterDaemon()

    def wrapper_factory():
        return LedgerWriterZooid()

    daemon = ShadowModeDaemon(
        niche="observability_logging",
        legacy_factory=legacy_factory,
        wrapper_factory=wrapper_factory,
    )

    return daemon.run()
