#!/usr/bin/env python3
"""
Memory decay daemon for KLoROS.

Runs as a background process to periodically update decay scores
and clean up heavily decayed memories.
"""

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

# Add src to path if running as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.kloros_memory.decay import DecayEngine, DecayConfig
from src.kloros_memory.storage import MemoryStore
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logger = logging.getLogger(__name__)


class DecayDaemon:
    """
    Daemon process for automatic memory decay management.

    Features:
    - Periodic decay score updates
    - Automatic cleanup of heavily decayed memories
    - Graceful shutdown handling
    - Configurable update intervals
    """

    def __init__(
        self,
        update_interval_minutes: int = 60,
        store: Optional[MemoryStore] = None,
        config: Optional[DecayConfig] = None
    ):
        """
        Initialize the decay daemon.

        Args:
            update_interval_minutes: How often to update decay scores
            store: Memory storage instance
            config: Decay configuration
        """
        self.update_interval = update_interval_minutes * 60  # Convert to seconds
        self.store = store or MemoryStore()
        self.config = config or DecayConfig.from_environment()
        self.engine = DecayEngine(store=self.store, config=self.config)

        self.running = False
        self.last_update = 0

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"[decay_daemon] Received signal {signum}, shutting down...")
        self.running = False

    def start(self):
        """Start the decay daemon."""
        logger.info("[decay_daemon] Starting memory decay daemon")
        logger.info(f"[decay_daemon] Update interval: {self.update_interval/60:.1f} minutes")
        logger.info(f"[decay_daemon] Deletion threshold: {self.config.deletion_threshold}")

        self.running = True
        iteration = 0

        while self.running:
            try:
                # Check maintenance mode before continuing
                wait_for_normal_mode()

                iteration += 1
                logger.info(f"[decay_daemon] Starting decay update iteration #{iteration}")

                # Update all decay scores
                start_time = time.time()
                stats = self.engine.update_all_decay_scores()
                elapsed = time.time() - start_time

                logger.info(
                    f"[decay_daemon] Iteration #{iteration} complete in {elapsed:.2f}s: "
                    f"{stats['updated']} updated, {stats['deleted']} deleted"
                )

                # Get decay statistics
                decay_stats = self.engine.get_decay_statistics()
                if 'overall' in decay_stats:
                    overall = decay_stats['overall']
                    logger.info(
                        f"[decay_daemon] Stats: {overall['total_events']} events, "
                        f"avg decay: {overall['avg_decay']:.3f}, "
                        f"near deletion: {decay_stats.get('near_deletion', 0)}"
                    )

                self.last_update = time.time()

                # Sleep until next update (check every minute for shutdown)
                sleep_remaining = self.update_interval
                while sleep_remaining > 0 and self.running:
                    sleep_chunk = min(60, sleep_remaining)
                    time.sleep(sleep_chunk)
                    sleep_remaining -= sleep_chunk

            except KeyboardInterrupt:
                logger.info("[decay_daemon] Keyboard interrupt received, shutting down...")
                break

            except Exception as e:
                logger.error(f"[decay_daemon] Error during decay update: {e}", exc_info=True)
                # Wait a bit before retrying
                time.sleep(60)

        logger.info("[decay_daemon] Daemon stopped")
        self.store.close()

    def run_once(self):
        """Run a single decay update cycle (useful for testing)."""
        logger.info("[decay_daemon] Running single decay update")

        start_time = time.time()
        stats = self.engine.update_all_decay_scores()
        elapsed = time.time() - start_time

        logger.info(
            f"[decay_daemon] Update complete in {elapsed:.2f}s: "
            f"{stats['updated']} updated, {stats['deleted']} deleted"
        )

        decay_stats = self.engine.get_decay_statistics()
        logger.info(f"[decay_daemon] Decay statistics: {decay_stats}")

        return stats


def main():
    """Main entry point for decay daemon."""
    parser = argparse.ArgumentParser(description="KLoROS Memory Decay Daemon")

    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.getenv("KLR_DECAY_UPDATE_INTERVAL", "60")),
        help="Update interval in minutes (default: 60)"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (useful for testing)"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Log file path (default: stdout)"
    )

    args = parser.parse_args()

    # Configure logging
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    if args.log_file:
        logging.basicConfig(
            level=getattr(logging, args.log_level),
            format=log_format,
            handlers=[
                logging.FileHandler(args.log_file),
                logging.StreamHandler()
            ]
        )
    else:
        logging.basicConfig(
            level=getattr(logging, args.log_level),
            format=log_format
        )

    # Create and run daemon
    daemon = DecayDaemon(update_interval_minutes=args.interval)

    if args.once:
        stats = daemon.run_once()
        print(f"\nDecay update complete:")
        print(f"  Updated: {stats['updated']}")
        print(f"  Deleted: {stats['deleted']}")
        print(f"  Remaining: {stats['remaining']}")
    else:
        daemon.start()


if __name__ == "__main__":
    main()
