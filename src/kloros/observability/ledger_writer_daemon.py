#!/usr/bin/env python3
"""
Ledger Writer Daemon - Consumes OBSERVATION events and writes to fitness ledger.

Subscribes to OBSERVATION topic on ChemBus and atomically appends events
to the fitness ledger with HMAC signatures.
"""
import sys
import time
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from kloros.orchestration.chem_bus_v2 import ChemSub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode
from kloros.observability.ledger_writer import (
    append_observation_atomic,
    update_registry_rolling_metrics
)
from kloros.registry.lifecycle_registry import LifecycleRegistry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

LEDGER_PATH = Path.home() / ".kloros/lineage/fitness_ledger.jsonl"
HMAC_KEY_PATH = Path.home() / ".kloros/keys/hmac.key"


def _load_policy():
    """Load lifecycle policy with defaults."""
    try:
        policy_path = Path.home() / ".kloros/config/lifecycle_policy.json"
        if policy_path.exists():
            return json.loads(policy_path.read_text())
        else:
            logger.info("Policy file not found, using defaults")
            return {"prod_ok_window_n": 20}
    except Exception as e:
        logger.warning(f"Failed to load policy, using defaults: {e}")
        return {"prod_ok_window_n": 20}


class LedgerWriterDaemon:
    """
    Daemon that consumes OBSERVATION events and writes to fitness ledger.

    Features:
    - Subscribes to OBSERVATION topic on ChemBus
    - Appends events to ledger with HMAC signatures
    - Updates registry rolling metrics (ok_rate, ttr_ms_mean, evidence)
    - Graceful shutdown
    """

    def __init__(self):
        self.running = True
        self.event_count = 0
        self.last_stats_ts = time.time()
        self.reg_mgr = LifecycleRegistry()
        self.policy = _load_policy()

        # Ensure paths exist
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Subscribe to OBSERVATION topic with callback
        self.sub = ChemSub(
            topic="OBSERVATION",
            on_json=self._on_observation,
            zooid_name="ledger_writer_daemon",
            niche="observability"
        )

        logger.info(f"Ledger Writer Daemon initialized")
        logger.info(f"  Ledger: {LEDGER_PATH}")
        logger.info(f"  HMAC Key: {HMAC_KEY_PATH}")
        logger.info(f"  Policy: ok_window_n={self.policy.get('prod_ok_window_n', 20)}")

    def _on_observation(self, msg: dict):
        """Callback invoked for each OBSERVATION message."""
        if not self.running:
            return

        try:
            self._process_observation(msg)
            self.event_count += 1

            # Log stats every 60 seconds
            now = time.time()
            if now - self.last_stats_ts >= 60:
                logger.info(f"Processed {self.event_count} OBSERVATION events in last 60s")
                self.event_count = 0
                self.last_stats_ts = now

        except Exception as e:
            logger.error(f"Error processing observation: {e}", exc_info=True)

    def run(self):
        """Main daemon loop - just keeps running while subscriber processes events."""
        logger.info("Starting ledger writer daemon...")

        try:
            while self.running:
                # Check maintenance mode before continuing
                wait_for_normal_mode()
                time.sleep(1)  # Subscriber processes events in background thread

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.shutdown()

    def _process_observation(self, msg: dict):
        """
        Process a single OBSERVATION event.

        Args:
            msg: OBSERVATION message from ChemBus
        """
        facts = msg.get("facts", {})

        # Extract required fields
        zooid_name = facts.get("zooid")
        if not zooid_name:
            logger.warning("OBSERVATION missing 'zooid' field, skipping")
            return

        # Look up brainmod and variant from registry
        brainmod = None
        variant = None

        if zooid_name:
            try:
                zooid_meta = self.reg_mgr.get_zooid_metadata(zooid_name)
                brainmod = zooid_meta.get("brainmod")
                variant = zooid_meta.get("variant")
            except Exception as e:
                logger.debug(f"Could not enrich zooid {zooid_name}: {e}")

        # Check if zooid exists in registry
        with self.reg_mgr.lock():
            reg = self.reg_mgr.load()

            if zooid_name not in reg["zooids"]:
                logger.debug(f"Zooid {zooid_name} not in registry, skipping observation")
                return

            # Prepare ledger row with enrichment
            now = time.time()
            row = {
                "ts": now,
                "zooid_name": zooid_name,
                "zooid": zooid_name,  # For update_registry_rolling_metrics()
                "niche": reg["zooids"][zooid_name].get("niche"),
                "ok": facts.get("ok", True),  # Assume OK unless explicitly failed
                "ttr_ms": facts.get("ttr_ms", 0),
                "incident_id": facts.get("incident_id", f"inc-{int(now)}"),
                "p95_ms_median": facts.get("p95_ms_median"),
                "p95_ms_mean": facts.get("p95_ms_mean"),
                "p95_ms_max": facts.get("p95_ms_max"),
                "sample_count": facts.get("sample_count"),
                "brainmod": brainmod,
                "variant": variant,
                "raw_facts": facts  # Preserve all facts for debugging
            }

            # Append to ledger atomically (with HMAC)
            try:
                append_observation_atomic(row, str(LEDGER_PATH))
                logger.debug(f"✅ Wrote observation for {zooid_name} (brainmod={brainmod}, variant={variant})")
            except Exception as e:
                logger.error(f"Failed to append observation to ledger: {e}", exc_info=True)
                return

            # Update registry rolling metrics
            try:
                update_registry_rolling_metrics(reg, row, now, self.policy)
                self.reg_mgr.snapshot_then_atomic_write(reg)
                logger.debug(f"Updated rolling metrics for {zooid_name}")
            except Exception as e:
                logger.error(f"Failed to update registry metrics: {e}", exc_info=True)

    def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down ledger writer daemon...")
        self.running = False
        self.sub.close()
        logger.info("Ledger writer daemon stopped")


def main():
    """Main entry point."""
    daemon = LedgerWriterDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
