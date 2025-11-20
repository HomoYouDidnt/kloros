#!/usr/bin/env python3
# latency_tracker_v1.py — hardened latency monitoring zooid
from __future__ import annotations
import sys
import time
import statistics
import logging
from pathlib import Path

# Add source to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from kloros.orchestration.colony_util import ZooidRuntime
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LatencyTracker(ZooidRuntime):
    """
    Latency monitoring zooid with aggregation.

    Features:
    - Aggregates multiple readings per incident (median)
    - Emits observations for fitness ledger
    - Replay defense (inherited from ZooidRuntime)
    - Kill switch support
    - Heartbeat emission

    Responds to:
    - Q_LATENCY_SPIKE: Monitors and aggregates latency measurements
    """

    def __init__(self):
        super().__init__(
            name="LatencyTracker_v1",
            niche="latency_monitoring",
            topics=["Q_LATENCY_SPIKE"]
        )

        # Aggregation: collect multiple readings per incident
        self.p95_readings: dict[str, list[float]] = {}
        self._aggregation_threshold = 3  # Emit observation after N readings

        logger.info(f"LatencyTracker_v1 initialized")

    def _on(self, msg: dict):
        """
        Handle Q_LATENCY_SPIKE signal.

        Collects readings and emits aggregated observation once
        threshold is reached.
        """
        if self.kill:
            return

        # Extract incident ID
        inc = msg.get("incident_id") or f"inc-{int(time.time())}"

        # Replay defense
        if self.already_handled(inc):
            logger.debug(f"Skipping duplicate incident: {inc}")
            return

        # Extract p95 from facts
        facts = msg.get("facts", {})
        p95_ms = facts.get("p95_ms")

        if p95_ms is None:
            logger.warning(f"No p95_ms in facts for {inc}")
            return

        logger.info(f"Observed spike for {inc}: p95={p95_ms}ms")

        # Aggregate readings
        self.p95_readings.setdefault(inc, []).append(p95_ms)

        # Check if we have enough readings to emit observation
        if len(self.p95_readings[inc]) >= self._aggregation_threshold:
            readings = self.p95_readings[inc]

            # Compute statistics
            median_p95 = statistics.median(readings)
            mean_p95 = statistics.mean(readings)
            max_p95 = max(readings)

            logger.info(
                f"Aggregated {len(readings)} readings for {inc}: "
                f"median={median_p95:.1f}ms, mean={mean_p95:.1f}ms, max={max_p95:.1f}ms"
            )

            # Emit observation for fitness ledger / PHASE adapters
            try:
                self.pub.emit(
                    "OBSERVATION",
                    ecosystem="queue_management",
                    facts={
                        "incident_id": inc,
                        "zooid": self.name,
                        "niche": self.niche,
                        "p95_ms_median": median_p95,
                        "p95_ms_mean": mean_p95,
                        "p95_ms_max": max_p95,
                        "sample_count": len(readings),
                        "ts": time.time()
                    }
                )
                logger.info(f"✅ Emitted observation for {inc}")

            except Exception as e:
                logger.error(f"Error emitting observation for {inc}: {e}", exc_info=True)

            # Clear readings for this incident (prevent memory leak)
            del self.p95_readings[inc]

        # Prune old incidents (keep last 100)
        if len(self.p95_readings) > 100:
            oldest_incidents = sorted(
                self.p95_readings.keys(),
                key=lambda k: min(len(self.p95_readings[k]), 1)  # Prioritize incomplete ones
            )[:50]
            for inc_id in oldest_incidents:
                del self.p95_readings[inc_id]
            logger.debug(f"Pruned {len(oldest_incidents)} old incidents from memory")


def main():
    """Main entry point."""
    logger.info("Starting LatencyTracker_v1...")

    tracker = LatencyTracker()

    try:
        # Run until killed
        while not tracker.kill:
            # Check maintenance mode before continuing
            wait_for_normal_mode()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        logger.info("Shutting down LatencyTracker_v1")
        tracker.close()


if __name__ == "__main__":
    main()
