#!/usr/bin/env python3
"""
Maintenance Mode Support - Coordinated system-wide suspension.

Provides utilities for subsystems to check and respond to maintenance mode.
All consumers should check is_maintenance_mode() in their work loops and pause.
"""

import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAINTENANCE_MARKER = Path("/home/kloros/.kloros/maintenance_mode")


def is_maintenance_mode() -> bool:
    """
    Check if system is in maintenance mode.

    Returns:
        True if maintenance marker file exists, False otherwise
    """
    return MAINTENANCE_MARKER.exists()


def wait_for_normal_mode(check_interval: float = 1.0, log_interval: int = 60) -> None:
    """
    Block until maintenance mode is cleared.

    Args:
        check_interval: How often to check marker file (seconds)
        log_interval: How often to log waiting message (seconds)
    """
    if not is_maintenance_mode():
        return

    logger.info("[maintenance] System in maintenance mode, suspending operations")
    last_log = time.time()

    while is_maintenance_mode():
        time.sleep(check_interval)

        # Log periodically to show we're alive
        if time.time() - last_log >= log_interval:
            logger.info("[maintenance] Still in maintenance mode, waiting...")
            last_log = time.time()

    logger.info("[maintenance] Maintenance mode cleared, resuming operations")


def maintenance_mode_wrapper(func):
    """
    Decorator to pause function execution during maintenance mode.

    Usage:
        @maintenance_mode_wrapper
        def process_batch():
            # This will pause if maintenance mode is active
            ...
    """
    def wrapper(*args, **kwargs):
        wait_for_normal_mode()
        return func(*args, **kwargs)
    return wrapper


class MaintenanceModeAware:
    """
    Mixin for consumer daemons that need to respect maintenance mode.

    Usage:
        class MyConsumer(MaintenanceModeAware):
            def run(self):
                while True:
                    self.wait_if_maintenance_mode()
                    # Do work...
    """

    def wait_if_maintenance_mode(self, check_interval: float = 1.0):
        """Check maintenance mode and pause if active."""
        wait_for_normal_mode(check_interval)

    def is_maintenance_mode(self) -> bool:
        """Check if in maintenance mode."""
        return is_maintenance_mode()


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(level=logging.INFO)

    print("=== Maintenance Mode Utilities Self-Test ===\n")

    if is_maintenance_mode():
        print("⚠️  System is currently in MAINTENANCE MODE")
        print(f"Marker file: {MAINTENANCE_MARKER}")
        print("\nWaiting for normal mode (press Ctrl+C to cancel)...")
        try:
            wait_for_normal_mode(check_interval=0.5, log_interval=5)
        except KeyboardInterrupt:
            print("\n\nTest interrupted")
    else:
        print("✅ System is in NORMAL MODE")
        print(f"Marker file does not exist: {MAINTENANCE_MARKER}")
        print("\nNo blocking needed, all systems operational")
