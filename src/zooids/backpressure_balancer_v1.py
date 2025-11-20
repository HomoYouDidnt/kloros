#!/usr/bin/env python3
# backpressure_balancer_v1.py — hardened backpressure control zooid
from __future__ import annotations
import sys
import time
import logging
from pathlib import Path

# Add source to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from kloros.orchestration.colony_util import ZooidRuntime
from kloros.orchestration.synth_bus import SynthRoom
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackpressureBalancer(ZooidRuntime):
    """
    Backpressure control zooid with rate limiting.

    Features:
    - One proposal per incident (rate limited)
    - Signed plan fragments (HMAC)
    - Replay defense (inherited from ZooidRuntime)
    - Kill switch support
    - Heartbeat emission

    Responds to:
    - Q_LATENCY_SPIKE: Proposes throttling when latency exceeds threshold
    """

    def __init__(self):
        super().__init__(
            name="BackpressureBalancer_v1",
            niche="backpressure_control",
            topics=["Q_LATENCY_SPIKE"]
        )

        # Rate limiting: track proposals per incident
        self._last_proposed: dict[str, float] = {}
        self._proposal_cooldown_s = 5.0  # Don't re-propose for same incident within 5s

        logger.info(f"BackpressureBalancer_v1 initialized")

    def _on(self, msg: dict):
        """
        Handle Q_LATENCY_SPIKE signal.

        Proposes throttling plan fragment if:
        1. Not a duplicate incident (replay defense)
        2. Haven't proposed for this incident recently (rate limiting)
        3. Latency exceeds threshold
        """
        if self.kill:
            return

        # Extract incident ID
        inc = msg.get("incident_id") or f"inc-{int(time.time())}"

        # Replay defense
        if self.already_handled(inc):
            logger.debug(f"Skipping duplicate incident: {inc}")
            return

        # Rate limiting: one proposal per incident
        now = time.time()
        last_proposal = self._last_proposed.get(inc, 0)

        if now - last_proposal < self._proposal_cooldown_s:
            logger.debug(f"Skipping {inc}: proposal cooldown active ({now - last_proposal:.1f}s ago)")
            return

        # Extract latency from facts
        facts = msg.get("facts", {})
        p95_ms = facts.get("p95_ms", 0)

        # Threshold check
        if p95_ms < 300:  # Only propose if p95 > 300ms
            logger.debug(f"Skipping {inc}: p95={p95_ms}ms below threshold (300ms)")
            return

        # Calculate throttle percentage based on severity
        if p95_ms > 1000:
            throttle_percent = 25
        elif p95_ms > 600:
            throttle_percent = 15
        else:
            throttle_percent = 10

        logger.info(f"Responding to {inc}: p95={p95_ms}ms → proposing {throttle_percent}% throttle")

        # Mark as proposed
        self._last_proposed[inc] = now

        # Prune old proposals (keep last 100)
        if len(self._last_proposed) > 100:
            oldest_keys = sorted(self._last_proposed.keys(), key=lambda k: self._last_proposed[k])[:50]
            for key in oldest_keys:
                del self._last_proposed[key]

        # Open synthesis room
        try:
            room = SynthRoom(inc).join(lambda m: logger.debug(f"Synthesis message: {m}"))

            # Propose plan fragment
            plan = {
                "type": "plan_fragment",
                "actor": self.name,
                "action": "throttle",
                "percent": throttle_percent,
                "incident_id": inc,
                "rationale": f"p95 latency {p95_ms}ms exceeds threshold",
                "ts": time.time()
            }

            self.propose(room.topic, plan)
            logger.info(f"✅ Proposed throttle plan for {inc}")

        except Exception as e:
            logger.error(f"Error proposing plan for {inc}: {e}", exc_info=True)


def main():
    """Main entry point."""
    logger.info("Starting BackpressureBalancer_v1...")

    balancer = BackpressureBalancer()

    try:
        # Run until killed
        while not balancer.kill:
            # Check maintenance mode before continuing
            wait_for_normal_mode()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        logger.info("Shutting down BackpressureBalancer_v1")
        balancer.close()


if __name__ == "__main__":
    main()
