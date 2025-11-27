"""Mock UMN implementation for unit testing voice zooids."""
import time
import threading
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass, field


@dataclass
class MockUMNMessage:
    """Mock UMN message for testing."""
    signal: str
    ecosystem: str
    intensity: float = 1.0
    facts: Dict[str, Any] = field(default_factory=dict)
    incident_id: Optional[str] = None
    trace: Optional[str] = None
    ts: float = field(default_factory=lambda: time.time())
    schema_version: int = 1


class MockUMNPub:
    """Mock UMN publisher for unit testing."""

    def __init__(self, ipc_path: str = None):
        self.messages: List[MockUMNMessage] = []
        self.signals_emitted: Dict[str, int] = {}
        self.closed = False

    def emit(self, signal: str, *, ecosystem: str, intensity: float = 1.0,
             facts: Optional[Dict[str, Any]] = None, incident_id: Optional[str] = None,
             trace: Optional[str] = None):
        """Emit a signal (mock - just records it)."""
        msg = MockUMNMessage(
            signal=signal,
            ecosystem=ecosystem,
            intensity=intensity,
            facts=facts or {},
            incident_id=incident_id,
            trace=trace
        )
        self.messages.append(msg)
        self.signals_emitted[signal] = self.signals_emitted.get(signal, 0) + 1

    def get_signal_count(self, signal: str) -> int:
        """Get count of times a signal was emitted."""
        return self.signals_emitted.get(signal, 0)

    def get_last_message(self, signal: str = None) -> Optional[MockUMNMessage]:
        """Get the last message emitted, optionally filtered by signal."""
        if not self.messages:
            return None

        if signal is None:
            return self.messages[-1]

        for msg in reversed(self.messages):
            if msg.signal == signal:
                return msg
        return None

    def clear(self):
        """Clear recorded messages."""
        self.messages.clear()
        self.signals_emitted.clear()

    def close(self):
        """Close the publisher."""
        self.closed = True


class MockUMNSub:
    """Mock UMN subscriber for unit testing."""

    def __init__(self, topic: str, on_json: Callable[[Dict[str, Any]], None],
                 zooid_name: str = None, niche: str = None, ipc_path: str = None):
        self.topic = topic
        self.on_json = on_json
        self.zooid_name = zooid_name
        self.niche = niche
        self.closed = False
        self.messages_received: List[Dict[str, Any]] = []

    def inject_message(self, signal: str, ecosystem: str = "voice",
                      intensity: float = 1.0, facts: Optional[Dict[str, Any]] = None,
                      incident_id: Optional[str] = None):
        """Inject a message into the subscriber (simulates receiving a signal)."""
        msg = {
            "signal": signal,
            "ecosystem": ecosystem,
            "intensity": intensity,
            "facts": facts or {},
            "incident_id": incident_id,
            "ts": time.time(),
            "schema_version": 1
        }
        self.messages_received.append(msg)
        if self.on_json:
            self.on_json(msg)

    def close(self):
        """Close the subscriber."""
        self.closed = True


class MockUMNContext:
    """Context manager for mocking UMN in tests."""

    def __init__(self):
        self.publishers: List[MockUMNPub] = []
        self.subscribers: List[MockUMNSub] = []
        self.original_classes = {}

    def __enter__(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        try:
            from src.orchestration import umn_bus_v2

            self.original_classes['UMNPub'] = umn_bus_v2.UMNPub
            self.original_classes['UMNSub'] = umn_bus_v2.UMNSub

            umn_bus_v2.UMNPub = MockUMNPub
            umn_bus_v2.UMNSub = MockUMNSub
        except Exception as e:
            print(f"Warning: Could not mock UMN: {e}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            from src.orchestration import umn_bus_v2

            if 'UMNPub' in self.original_classes:
                umn_bus_v2.UMNPub = self.original_classes['UMNPub']
            if 'UMNSub' in self.original_classes:
                umn_bus_v2.UMNSub = self.original_classes['UMNSub']
        except Exception:
            pass
