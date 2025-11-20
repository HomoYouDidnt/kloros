# signal_router_v2.py — feature-flagged intent→signal router with observability
from __future__ import annotations
import os
import logging
from typing import Dict, Any, Optional
from .chem_bus_v2 import ChemPub

logger = logging.getLogger(__name__)

# Feature flag: KLR_CHEM_ENABLED=1 → broadcast mode, 0 → legacy RPC
CHEM_ENABLED = os.environ.get("KLR_CHEM_ENABLED", "1") == "1"

# Intent mapping
INTENT_TO_SIGNAL = {
    "queue.latency_spike": ("Q_LATENCY_SPIKE", "queue_management"),
    "queue.stall": ("Q_STALL", "queue_management"),
    "queue.congestion_forecast": ("Q_CONGESTION_FORECAST", "queue_management"),
    "queue.orphaned": ("Q_ORPHANED_QUEUE", "queue_management"),
    "integration_fix": ("Q_INTEGRATION_FIX", "queue_management"),
    "spica_spawn_request": ("Q_SPICA_SPAWN", "experimentation"),
    "curiosity_investigate": ("Q_CURIOSITY_INVESTIGATE", "introspection"),
    "curiosity_propose_fix": ("Q_CURIOSITY_PROPOSE_FIX", "introspection"),
    "investigation_complete": ("Q_INVESTIGATION_COMPLETE", "introspection"),
}

class SignalRouter:
    """
    Intent → Chemical Signal router with feature flag support.

    When KLR_CHEM_ENABLED=1: Broadcasts to colony via chem bus
    When KLR_CHEM_ENABLED=0: Returns False to trigger legacy RPC path
    """

    def __init__(self, chem_path: Optional[str] = None):
        self._pub = ChemPub(chem_path) if chem_path else ChemPub() if CHEM_ENABLED else None

        if CHEM_ENABLED:
            logger.info("SignalRouter: Chemical signal mode ENABLED")
        else:
            logger.warning("SignalRouter: Chemical signal mode DISABLED (legacy RPC mode)")

    def route_intent(
        self,
        intent_type: str,
        *,
        intensity: float = 1.0,
        facts: Optional[Dict[str, Any]] = None,
        incident_id: Optional[str] = None,
        trace: Optional[str] = None
    ) -> bool:
        """
        Route intent to chemical signal or legacy path.

        Returns:
            True if routed via chemical signal
            False if should fall back to legacy RPC (feature flag disabled or unmapped intent)
        """
        if not CHEM_ENABLED:
            logger.debug(f"SignalRouter: CHEM_DISABLED, falling back to legacy for {intent_type}")
            return False

        mapping = INTENT_TO_SIGNAL.get(intent_type)
        if not mapping:
            logger.warning(f"SignalRouter: No mapping for intent_type={intent_type}, falling back to legacy")
            return False

        signal, ecosystem = mapping

        try:
            self._pub.emit(
                signal,
                ecosystem=ecosystem,
                intensity=intensity,
                facts=facts or {},
                incident_id=incident_id,
                trace=trace
            )
            logger.info(f"SignalRouter: Routed {intent_type} → {signal} (incident={incident_id})")
            return True

        except Exception as e:
            logger.error(f"SignalRouter: Failed to emit {signal}: {e}, falling back to legacy")
            return False

    def close(self):
        if self._pub:
            self._pub.close()
