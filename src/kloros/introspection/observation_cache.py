"""
ObservationCache - Thread-safe rolling window cache for OBSERVATION events.

Provides shared observation storage for streaming introspection scanners with
automatic pruning of stale data and concurrent read/write access.
"""

import time
import threading
import logging
from collections import deque
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ObservationCache:
    """
    Thread-safe rolling window cache for OBSERVATION events.

    Features:
    - Automatic pruning of observations older than window_seconds
    - Thread-safe append and read operations
    - Custom time windows for queries
    - Memory-bounded (deque with maxlen)
    """

    def __init__(self, window_seconds: int = 300, max_items: int = 10000):
        """
        Initialize observation cache.

        Args:
            window_seconds: Time window in seconds (default: 5 minutes)
            max_items: Maximum number of observations to store (default: 10000)
        """
        self.window_seconds = window_seconds
        self.max_items = max_items
        self.observations = deque(maxlen=max_items)
        self.lock = threading.Lock()

        logger.info(f"ObservationCache initialized: window={window_seconds}s, max_items={max_items}")

    def append(self, observation: Dict[str, Any]) -> None:
        """
        Append observation to cache and prune stale entries.

        Args:
            observation: OBSERVATION dict with 'ts' field
        """
        with self.lock:
            self.observations.append(observation)
            self._prune_stale()

    def get_recent(self, seconds: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get observations within time window (thread-safe).

        Args:
            seconds: Custom time window in seconds (default: use window_seconds)

        Returns:
            List of observation dicts
        """
        with self.lock:
            if seconds is None:
                return list(self.observations)

            cutoff = time.time() - seconds
            return [obs for obs in self.observations if obs.get('ts', 0) >= cutoff]

    def _prune_stale(self) -> None:
        """
        Remove observations older than window_seconds.

        Note: Must be called with lock held.
        """
        cutoff = time.time() - self.window_seconds

        while self.observations and self.observations[0].get('ts', 0) < cutoff:
            self.observations.popleft()

    def size(self) -> int:
        """Get current cache size (thread-safe)."""
        with self.lock:
            return len(self.observations)
