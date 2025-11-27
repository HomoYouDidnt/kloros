# signal_router.py — translate intents/events to chemical signals; broadcast
from __future__ import annotations
from typing import Dict, Any
from .umn_bus import UMNPub

# Simple mapping; can be extended to rules or learned models
INTENT_TO_SIGNAL = {
    "queue.latency_spike": ("Q_LATENCY_SPIKE", "queue_management"),
    "queue.stall": ("Q_STALL", "queue_management"),
    "queue.congestion_forecast": ("Q_CONGESTION_FORECAST", "queue_management"),
    "queue.orphaned": ("Q_ORPHANED_QUEUE", "queue_management"),
}

class SignalRouter:
    def __init__(self, chem_path: str = None):
        self._pub = UMNPub(chem_path) if chem_path else UMNPub()

    def route_intent(self, intent_type: str, *, intensity: float = 1.0, facts: Dict[str, Any] | None = None, incident_id: str | None = None, trace: str | None = None) -> bool:
        key = INTENT_TO_SIGNAL.get(intent_type)
        if not key:
            return False
        signal, ecosystem = key
        self._pub.emit(signal, ecosystem=ecosystem, intensity=intensity, facts=facts or {}, incident_id=incident_id, trace=trace)
        return True

    def close(self):
        self._pub.close()
