#!/usr/bin/env python3
"""
Autonomous decay daemon integration for KLoROS.

Runs memory decay updates in a background thread without blocking
the main voice interaction loop.
"""

import logging
import os
import threading
import time
from typing import Optional

from .decay import DecayEngine, DecayConfig
from .storage import MemoryStore

logger = logging.getLogger(__name__)


class AutonomousDecayManager:
    """
    Background decay manager that runs in a separate thread.

    Integrates seamlessly with KLoROS's main loop without blocking.
    """

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        config: Optional[DecayConfig] = None,
        update_interval_minutes: int = None
    ):
        """
        Initialize the autonomous decay manager.

        Args:
            store: Memory storage instance
            config: Decay configuration
            update_interval_minutes: How often to update (default: from env or 60)
        """
        self.store = store or MemoryStore()
        self.config = config or DecayConfig.from_environment()

        # Get update interval from environment or use provided value
        if update_interval_minutes is None:
            update_interval_minutes = int(os.getenv("KLR_DECAY_UPDATE_INTERVAL", "60"))

        self.update_interval = update_interval_minutes * 60  # Convert to seconds
        self.engine = DecayEngine(store=self.store, config=self.config)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self):
        """Start the autonomous decay manager in background thread."""
        if self._running:
            logger.warning("[autonomous_decay] Already running")
            return

        logger.info("[autonomous_decay] Starting background decay manager")
        logger.info(f"[autonomous_decay] Update interval: {self.update_interval/60:.1f} minutes")
        logger.info(f"[autonomous_decay] Deletion threshold: {self.config.deletion_threshold}")

        self._stop_event.clear()
        self._running = True

        # Start background thread
        self._thread = threading.Thread(
            target=self._background_loop,
            name="KLoROS-Decay-Manager",
            daemon=True  # Daemon thread won't prevent program exit
        )
        self._thread.start()

        logger.info("[autonomous_decay] Background decay manager started")

    def stop(self):
        """Stop the autonomous decay manager."""
        if not self._running:
            return

        logger.info("[autonomous_decay] Stopping background decay manager")
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        self._running = False
        logger.info("[autonomous_decay] Background decay manager stopped")

    def is_running(self) -> bool:
        """Check if decay manager is running."""
        return self._running and self._thread and self._thread.is_alive()

    def _background_loop(self):
        """Background loop that runs decay updates periodically."""
        iteration = 0

        while not self._stop_event.is_set():
            try:
                iteration += 1
                logger.info(f"[autonomous_decay] Starting decay update iteration #{iteration}")

                # Update all decay scores
                start_time = time.time()
                stats = self.engine.update_all_decay_scores()
                elapsed = time.time() - start_time

                logger.info(
                    f"[autonomous_decay] Iteration #{iteration} complete in {elapsed:.2f}s: "
                    f"{stats['updated']} updated, {stats['deleted']} deleted"
                )

                # Get decay statistics
                try:
                    decay_stats = self.engine.get_decay_statistics()
                    if 'overall' in decay_stats:
                        overall = decay_stats['overall']
                        logger.info(
                            f"[autonomous_decay] Stats: {overall['total_events']} events, "
                            f"avg decay: {overall['avg_decay']:.3f}, "
                            f"near deletion: {decay_stats.get('near_deletion', 0)}"
                        )
                except Exception as e:
                    logger.error(f"[autonomous_decay] Failed to get statistics: {e}")

                # Sleep until next update (check every minute for stop signal)
                sleep_remaining = self.update_interval
                while sleep_remaining > 0 and not self._stop_event.is_set():
                    sleep_chunk = min(60, sleep_remaining)
                    time.sleep(sleep_chunk)
                    sleep_remaining -= sleep_chunk

            except Exception as e:
                logger.error(f"[autonomous_decay] Error during decay update: {e}", exc_info=True)
                # Wait a bit before retrying on error
                if not self._stop_event.is_set():
                    time.sleep(60)

        logger.info("[autonomous_decay] Background loop exited")


# Global singleton instance
_decay_manager: Optional[AutonomousDecayManager] = None


def start_autonomous_decay(
    store: Optional[MemoryStore] = None,
    config: Optional[DecayConfig] = None,
    update_interval_minutes: int = None
) -> AutonomousDecayManager:
    """
    Start autonomous decay management in background.

    Args:
        store: Memory storage instance
        config: Decay configuration
        update_interval_minutes: Update interval (default: from env or 60)

    Returns:
        The decay manager instance
    """
    global _decay_manager

    if _decay_manager is not None and _decay_manager.is_running():
        logger.info("[autonomous_decay] Decay manager already running")
        return _decay_manager

    _decay_manager = AutonomousDecayManager(
        store=store,
        config=config,
        update_interval_minutes=update_interval_minutes
    )

    _decay_manager.start()
    return _decay_manager


def stop_autonomous_decay():
    """Stop autonomous decay management."""
    global _decay_manager

    if _decay_manager is not None:
        _decay_manager.stop()
        _decay_manager = None


def get_autonomous_decay_manager() -> Optional[AutonomousDecayManager]:
    """Get the current decay manager instance."""
    return _decay_manager
