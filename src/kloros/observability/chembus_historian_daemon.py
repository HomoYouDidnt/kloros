#!/usr/bin/env python3
"""
ChemBus Historian Daemon - Persists all chemical signals to history file.

Subscribes to all ChemBus topics and maintains a rolling window of recent messages.
Introspection daemon consolidates old segments and prunes the file.
"""
import sys
import time
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from kloros.orchestration.chem_bus_v2 import ChemSub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChemBusHistorian:
    """
    Daemon that subscribes to all ChemBus signals and persists them to history file.

    Features:
    - Subscribes to ALL topics (empty string matches everything)
    - Appends all messages to chembus_history.jsonl
    - Adds reception timestamp to each message
    - Emergency rotation at 500MB limit
    - Introspection daemon consolidates and prunes old data
    """

    def __init__(self):
        self.running = True
        self.history_file = Path.home() / ".kloros/chembus_history.jsonl"
        self.max_size_bytes = 500 * 1024 * 1024
        self.message_count = 0
        self.last_stats_ts = time.time()

        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        self.sub = ChemSub(
            topic="",
            on_json=self._on_message,
            zooid_name="chembus_historian",
            niche="observability"
        )

        logger.info(f"ChemBus Historian Daemon initialized")
        logger.info(f"  History file: {self.history_file}")
        logger.info(f"  Max size: {self.max_size_bytes / 1024 / 1024:.0f} MB")

    def _on_message(self, msg: dict):
        """Callback invoked for each ChemBus message."""
        if not self.running:
            return

        try:
            msg["_historian_ts"] = time.time()

            with open(self.history_file, "a") as f:
                f.write(json.dumps(msg, separators=(",", ":")) + "\n")

            self.message_count += 1

            now = time.time()
            if now - self.last_stats_ts >= 60:
                logger.info(f"Captured {self.message_count} messages in last 60s")
                self.message_count = 0
                self.last_stats_ts = now

            if self.history_file.stat().st_size > self.max_size_bytes:
                self._emergency_rotate()

        except Exception as e:
            logger.error(f"Error capturing message: {e}", exc_info=True)

    def _emergency_rotate(self):
        """Emergency rotation if introspection hasn't pruned in time."""
        try:
            old_path = self.history_file.with_suffix(".jsonl.old")
            self.history_file.rename(old_path)
            logger.warning(f"Emergency rotation: {self.history_file} exceeded 500MB")
        except Exception as e:
            logger.error(f"Emergency rotation failed: {e}", exc_info=True)

    def run(self):
        """Main daemon loop - keeps running while subscriber processes events."""
        logger.info("Starting ChemBus historian daemon...")

        try:
            while self.running:
                wait_for_normal_mode()
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down ChemBus historian daemon...")
        self.running = False
        self.sub.close()
        logger.info("ChemBus historian daemon stopped")


def main():
    """Main entry point."""
    daemon = ChemBusHistorian()
    daemon.run()


if __name__ == "__main__":
    main()
