# synth_bus.py — peer synthesis channels for incident-scoped coordination
from __future__ import annotations
import json, time, uuid
from typing import Callable, Dict, Any
from .umn_bus import UMNPub, UMNSub

ROOM_PREFIX = "SYNTH_"  # topics look like: SYNTH_inc-2025-11-07T...

class SynthRoom:
    def __init__(self, incident_id: str):
        self.topic = f"{ROOM_PREFIX}{incident_id}"
        self.pub = UMNPub()
        self._sub = None

    def join(self, on_message: Callable[[Dict[str, Any]], None]):
        self._sub = UMNSub(self.topic, on_message)
        return self

    def propose(self, fragment: Dict[str, Any]):
        fragment.setdefault("ts", time.time())
        fragment.setdefault("id", str(uuid.uuid4()))
        self.pub.emit(self.topic, ecosystem="synthesis", facts=fragment)

    def close(self):
        if self._sub: self._sub.close()
        self.pub.close()
