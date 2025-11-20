# colony_util.py — hardened zooid runtime with replay defense, kill-switch, heartbeats
from __future__ import annotations
import hmac
import hashlib
import json
import os
import time
import collections
import threading
import logging
from typing import Callable, List, Dict, Any
from .chem_bus_v2 import ChemSub, ChemPub

logger = logging.getLogger(__name__)

# HMAC key for signed fragments
HMAC_KEY = os.getenv("KLR_COLONY_HMAC", "dev-key-override-me").encode()

def sign(obj: dict) -> str:
    """
    Sign a dictionary with HMAC-SHA256.

    Args:
        obj: Dictionary to sign

    Returns:
        Hex-encoded HMAC signature
    """
    msg = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(HMAC_KEY, msg, hashlib.sha256).hexdigest()

def verify(obj: dict, signature: str) -> bool:
    """
    Verify HMAC signature on a dictionary.

    Args:
        obj: Dictionary to verify (without 'sig' key)
        signature: Expected HMAC signature

    Returns:
        True if signature is valid
    """
    expected = sign(obj)
    return hmac.compare_digest(expected, signature)


class ZooidRuntime:
    """
    Hardened zooid runtime framework.

    Features:
    - Replay defense (60s LRU of incident_ids)
    - Kill switch (governance.kill subscription)
    - Heartbeat emission (every 10s)
    - Signed fragment proposals
    - Rate limiting helpers

    Usage:
        class MyZooid(ZooidRuntime):
            def __init__(self):
                super().__init__(
                    name="MyZooid_v1",
                    niche="my_niche",
                    topics=["Q_MY_SIGNAL"]
                )

            def _on(self, msg):
                if self.kill:
                    return

                inc = msg.get("incident_id") or f"inc-{int(time.time())}"
                if self.already_handled(inc):
                    return

                # Handle signal...
                self.propose("SYNTH_" + inc, {"plan": "..."})
    """

    def __init__(self, name: str, niche: str, topics: List[str], ipc_path: str = None):
        """
        Initialize hardened zooid runtime.

        Args:
            name: Zooid name (e.g., "LatencyTracker_v1")
            niche: Ecological niche (e.g., "latency_monitoring")
            topics: List of signals to subscribe to (e.g., ["Q_LATENCY_SPIKE"])
            ipc_path: Optional IPC path for ChemBus (default: uses ChemBus default)
        """
        self.name = name
        self.niche = niche
        self.kill = False

        # Replay defense: LRU of incident_ids
        self._seen: collections.OrderedDict[str, float] = collections.OrderedDict()
        self._replay_window_s = 60.0
        self._replay_max_entries = 200

        # Chemical bus
        self.pub = ChemPub(ipc_path) if ipc_path else ChemPub()

        # Subscribe to target signals
        self._subs = [
            ChemSub(topic, self._on_wrapper, ipc_path, zooid_name=name, niche=niche)
            for topic in topics
        ]

        # Subscribe to kill switch
        self._gov_sub = ChemSub(
            "governance.kill",
            self._on_kill,
            ipc_path,
            zooid_name=name,
            niche=niche
        )

        # Start heartbeat thread
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()

        logger.info(f"ZooidRuntime initialized: {name} niche={niche} topics={topics}")

    def _on_kill(self, msg: Dict[str, Any]):
        """Handle governance kill signal."""
        logger.warning(f"{self.name} received kill signal")
        self.kill = True

    def _on_wrapper(self, msg: Dict[str, Any]):
        """
        Wrapper for user's _on() handler.

        Adds kill check before calling user handler.
        """
        if self.kill:
            return

        try:
            self._on(msg)
        except Exception as e:
            logger.error(f"{self.name} error processing message: {e}", exc_info=True)

    def _on(self, msg: Dict[str, Any]):
        """
        Override this method in subclass to handle signals.

        Example:
            def _on(self, msg):
                if self.kill:
                    return

                inc = msg.get("incident_id") or f"inc-{int(time.time())}"
                if self.already_handled(inc):
                    return

                # Your signal handling logic here...
        """
        raise NotImplementedError("Subclass must implement _on()")

    def already_handled(self, incident_id: str) -> bool:
        """
        Check if incident was recently handled (replay defense).

        Args:
            incident_id: Incident identifier

        Returns:
            True if incident was handled in last 60s
        """
        now = time.time()

        # Prune old entries
        cutoff = now - self._replay_window_s
        while self._seen and next(iter(self._seen.values())) < cutoff:
            self._seen.popitem(last=False)

        # Trim to max size
        while len(self._seen) > self._replay_max_entries:
            self._seen.popitem(last=False)

        # Check for duplicate
        if incident_id in self._seen:
            logger.debug(f"{self.name} skipping duplicate incident: {incident_id}")
            return True

        # Mark as seen
        self._seen[incident_id] = now
        return False

    def _heartbeat_loop(self):
        """Emit heartbeat every 10s."""
        while True:
            if self.kill:
                logger.info(f"{self.name} heartbeat thread exiting (kill signal received)")
                return

            try:
                self.pub.emit(
                    "HEARTBEAT",
                    ecosystem="colony",
                    facts={
                        "zooid": self.name,
                        "niche": self.niche,
                        "ts": time.time(),
                        "schema": "chem:v1",
                        "incidents_handled": len(self._seen)
                    }
                )
                logger.debug(f"{self.name} heartbeat sent")
            except Exception as e:
                logger.error(f"{self.name} heartbeat error: {e}")

            time.sleep(10)

    def propose(self, room_topic: str, fragment: Dict[str, Any]):
        """
        Propose a plan fragment to synthesis room with HMAC signature.

        Args:
            room_topic: Synthesis room topic (e.g., "SYNTH_inc-123")
            fragment: Plan fragment to propose
        """
        # Sign fragment
        fragment["sig"] = sign(fragment)

        # Emit to synthesis room
        self.pub.emit(
            room_topic,
            ecosystem="synthesis",
            facts=fragment
        )

        logger.info(f"{self.name} proposed fragment to {room_topic}")

    def close(self):
        """Clean shutdown."""
        logger.info(f"{self.name} shutting down")
        self.kill = True

        for sub in self._subs:
            try:
                sub.close()
            except Exception as e:
                logger.error(f"Error closing subscriber: {e}")

        try:
            self._gov_sub.close()
        except Exception as e:
            logger.error(f"Error closing governance subscriber: {e}")

        try:
            self.pub.close()
        except Exception as e:
            logger.error(f"Error closing publisher: {e}")
