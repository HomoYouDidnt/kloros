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
import os
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
        self.max_size_bytes = 50 * 1024 * 1024  # Increased to 50MB to accommodate 100k line retention (~29MB)
        self.message_count = 0
        self.last_stats_ts = time.time()
        self.max_retries = 10
        self.max_backoff_s = 60

        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.history_file.exists():
            self.history_file.touch()
        os.chmod(self.history_file, 0o640)

        self.sub = self._connect_with_retry()

        logger.info(f"ChemBus Historian Daemon initialized")
        logger.info(f"  History file: {self.history_file}")
        logger.info(f"  Max size: {self.max_size_bytes / 1024 / 1024:.0f} MB")

    def _connect_with_retry(self):
        """Connect to ChemBus with exponential backoff retry logic."""
        for attempt in range(self.max_retries):
            try:
                sub = ChemSub(
                    topic="",
                    on_json=self._on_message,
                    zooid_name="chembus_historian",
                    niche="observability"
                )
                logger.info(f"ChemBus connection established on attempt {attempt + 1}")
                return sub
            except Exception as e:
                backoff_s = min(2 ** attempt, self.max_backoff_s)
                logger.warning(
                    f"ChemBus connection attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                    f"Retrying in {backoff_s}s..."
                )
                if attempt < self.max_retries - 1:
                    time.sleep(backoff_s)
                else:
                    logger.error(f"Failed to connect to ChemBus after {self.max_retries} attempts")
                    raise

    def _on_message(self, msg: dict):
        """Callback invoked for each ChemBus message."""
        if not self.running:
            return

        try:
            msg["_historian_ts"] = time.time()

            file_existed = self.history_file.exists()
            with open(self.history_file, "a") as f:
                f.write(json.dumps(msg, separators=(",", ":")) + "\n")

            if not file_existed:
                os.chmod(self.history_file, 0o640)

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
            file_size_mb = self.history_file.stat().st_size / 1024 / 1024
            logger.warning(f"Emergency rotation triggered: {self.history_file} is {file_size_mb:.2f} MB")

            # Keep only the most recent lines (approximately last 24 hours of data)
            # This prevents scanner timeouts caused by reading huge files
            import subprocess
            keep_lines = 100000  # Approximately last 24 hours at current message rate

            temp_file = self.history_file.with_suffix(".jsonl.tmp")
            try:
                # Use tail to keep only recent lines
                subprocess.run(
                    ["tail", f"-{keep_lines}", str(self.history_file)],
                    stdout=open(temp_file, 'w'),
                    check=True
                )

                # Archive old file before replacing
                old_path = self.history_file.with_suffix(".jsonl.old")
                if old_path.exists():
                    old_path.unlink()
                self.history_file.rename(old_path)

                # Move temp file to history file
                temp_file.rename(self.history_file)
                os.chmod(self.history_file, 0o640)

                new_size_mb = self.history_file.stat().st_size / 1024 / 1024
                logger.info(f"Emergency rotation complete: kept last {keep_lines} lines, reduced from {file_size_mb:.2f}MB to {new_size_mb:.2f}MB")
            finally:
                if temp_file.exists():
                    temp_file.unlink()

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
