"""Async event bus for heal events."""

import threading
import queue
from typing import Callable, List
from .events import HealEvent


class HealBus:
    """Non-blocking pub/sub bus for heal events."""

    def __init__(self):
        self._subscribers: List[Callable[[HealEvent], None]] = []
        self._queue = queue.Queue(maxsize=100)
        self._running = True
        self._worker = threading.Thread(target=self._process_events, daemon=True)
        self._worker.start()

    def subscribe(self, handler: Callable[[HealEvent], None]):
        """Subscribe a handler to receive all events.

        Args:
            handler: Callable that takes a HealEvent
        """
        self._subscribers.append(handler)

    def emit(self, event: HealEvent):
        """Emit an event (non-blocking).

        Args:
            event: HealEvent to emit
        """
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            print(f"[heal_bus] Queue full, dropping event {event.id}")

    def _process_events(self):
        """Worker thread that processes events."""
        while self._running:
            try:
                event = self._queue.get(timeout=1.0)
                for handler in self._subscribers:
                    try:
                        handler(event)
                    except Exception as e:
                        print(f"[heal_bus] Handler error: {e}")
            except queue.Empty:
                continue

    def shutdown(self):
        """Shutdown the event bus."""
        self._running = False
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)
