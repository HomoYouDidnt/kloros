#!/usr/bin/env python3
"""
Exception Monitor Daemon - Streams journalctl for exceptions in real-time.

Replaces ExceptionMonitor batch polling with streaming event-driven architecture.

Architecture:
- Subscribes to journalctl --follow stream (like tail -f)
- Parses JSON logs for exceptions
- Deduplicates using LRU cache
- Emits CAPABILITY_GAP signals to ChemBus immediately

Memory Profile: ~50MB (LRU cache + journal stream buffer)
CPU Profile: 5-10% (parsing JSON stream)
"""

import json
import logging
import subprocess
import hashlib
import sys
import time
import re
from pathlib import Path
from collections import OrderedDict
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parents[3]))

from kloros.orchestration.chem_bus_v2 import ChemPub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LRUCache:
    """Simple LRU cache for deduplication."""

    def __init__(self, maxsize: int = 1000):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def __contains__(self, key):
        if key in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return True
        return False

    def __setitem__(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)  # Remove oldest


class ExceptionMonitorDaemon:
    """
    Streaming exception monitor daemon.

    Features:
    - Real-time journalctl stream processing
    - LRU deduplication (1000 recent exceptions)
    - Immediate ChemBus signal emission
    - Low, constant memory usage
    """

    def __init__(self):
        """Initialize exception monitor daemon."""
        self.running = True
        self.pub = ChemPub()
        self.seen_exceptions = LRUCache(maxsize=1000)
        self.exception_count = 0
        self.signal_count = 0

    def run(self):
        """
        Main daemon loop - stream journalctl for exceptions.

        Streams all kloros-* units with --follow (real-time).
        Never polls, never batch processes - pure streaming.
        """
        logger.info("[exception_monitor] Starting exception monitor daemon (streaming mode)")
        logger.info("[exception_monitor] Watching journalctl -f --unit=kloros-*")

        try:
            # Stream journalctl with --follow (like tail -f)
            process = subprocess.Popen(
                [
                    'journalctl',
                    '-f',  # Follow (stream)
                    '--output=json',  # JSON format for parsing
                    '--unit=kloros-*',  # All kloros units
                    '--no-pager'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )

            logger.info("[exception_monitor] journalctl stream started")

            for line in iter(process.stdout.readline, ''):
                if not self.running:
                    break

                wait_for_normal_mode()

                try:
                    entry = json.loads(line.strip())
                    self._process_log_entry(entry)
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.error(f"[exception_monitor] Error processing log entry: {e}")
                    continue

        except KeyboardInterrupt:
            logger.info("[exception_monitor] Keyboard interrupt received")
        finally:
            self.shutdown()

    def _process_log_entry(self, entry: Dict[str, Any]):
        """
        Process one journald log entry.

        Args:
            entry: Parsed JSON log entry from journalctl
        """
        # Check if this is an exception
        if not self._is_exception(entry):
            return

        self.exception_count += 1

        # Generate exception ID for deduplication
        exception_id = self._hash_exception(entry)

        # Deduplicate - skip if seen recently
        if exception_id in self.seen_exceptions:
            logger.debug(f"[exception_monitor] Skipping duplicate exception: {exception_id[:8]}")
            return

        # Mark as seen
        self.seen_exceptions[exception_id] = True

        # Emit CAPABILITY_GAP signal
        self._emit_exception_gap(entry, exception_id)
        self.signal_count += 1

        logger.info(
            f"[exception_monitor] Exception detected: "
            f"{entry.get('_SYSTEMD_UNIT', 'unknown')} - "
            f"{entry.get('MESSAGE', 'no message')[:80]}"
        )

    def _is_exception(self, entry: Dict[str, Any]) -> bool:
        """
        Check if log entry contains an exception.

        Args:
            entry: Journald log entry

        Returns:
            True if entry contains exception/error
        """
        message = entry.get('MESSAGE', '').lower()
        priority = entry.get('PRIORITY', '6')  # 6 = info, 3 = error (string from journald)

        # Convert priority to int (journald returns as string)
        try:
            priority = int(priority)
        except (ValueError, TypeError):
            priority = 6  # Default to info

        # Option 1: Skip monitoring/logging metadata
        # If message starts with [tag], it's monitoring commentary, not an actual exception
        if message.startswith('[') and ']' in message[:30]:
            return False

        # Priority 3 or lower = error/critical
        if priority <= 3:
            return True

        # Option 2: Require actual exception signatures, not generic words
        # Look for real Python exception indicators
        exception_signatures = [
            'traceback (most recent call last)',
            'error: ',           # Actual error prefix (with colon+space)
            'failed with',
            'errno',
            'valueerror',        # Actual exception class names
            'keyerror',
            'typeerror',
            'attributeerror',
            'importerror',
            'modulenotfounderror',
            'filenotfounderror',
            'permissionerror',
            'runtimeerror',
            'indexerror',
            'zerodivisionerror'
        ]

        return any(signature in message for signature in exception_signatures)

    def _hash_exception(self, entry: Dict[str, Any]) -> str:
        """
        Generate unique hash for exception (for deduplication).

        Uses: unit name + message + priority
        Ignores timestamps to catch duplicate exceptions.

        Args:
            entry: Journald log entry

        Returns:
            Exception hash (hex string)
        """
        unit = entry.get('_SYSTEMD_UNIT', 'unknown')
        message = entry.get('MESSAGE', '')[:200]  # First 200 chars
        priority = entry.get('PRIORITY', '6')

        # Convert priority to int
        try:
            priority = int(priority)
        except (ValueError, TypeError):
            priority = 6

        hash_input = f"{unit}:{priority}:{message}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def _emit_exception_gap(self, entry: Dict[str, Any], exception_id: str):
        """
        Emit CAPABILITY_GAP signal for exception.

        Args:
            entry: Journald log entry
            exception_id: Exception hash
        """
        unit = entry.get('_SYSTEMD_UNIT', 'unknown')
        message = entry.get('MESSAGE', 'No message')
        priority = entry.get('PRIORITY', '6')

        # Convert priority to int
        try:
            priority = int(priority)
        except (ValueError, TypeError):
            priority = 6

        # Extract traceback if present
        traceback = None
        if 'TRACEBACK' in entry:
            traceback = entry['TRACEBACK']
        elif 'traceback' in message.lower():
            # Try to extract from message
            traceback = message

        self.pub.emit(
            signal="CAPABILITY_GAP",
            ecosystem="diagnostics",
            facts={
                "gap_type": "exception",
                "gap_name": f"exception_{unit}_{exception_id[:8]}",
                "gap_category": "error_handling",
                "unit": unit,
                "message": message,
                "priority": priority,
                "traceback": traceback,
                "exception_id": exception_id
            }
        )

    def shutdown(self):
        """Shutdown daemon gracefully."""
        logger.info("[exception_monitor] Shutting down exception monitor daemon")
        logger.info(f"[exception_monitor] Total exceptions detected: {self.exception_count}")
        logger.info(f"[exception_monitor] Total signals emitted: {self.signal_count}")
        self.running = False


def main():
    """Main entry point."""
    daemon = ExceptionMonitorDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
