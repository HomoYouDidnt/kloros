#!/usr/bin/env python3
"""
KLoROS Policy Engine - Autonomous decision-making daemon for major workflows.

Purpose:
    KLoROS's conscious decision-making for triggering major system workflows.
    Subscribes to advisory signals from monitors and decides whether to trigger
    actions like D-REAM execution or PHASE epochs based on policy rules.

Architecture:
    1. Subscribe to advisory signals via chemical bus (ChemSub)
    2. Evaluate advisories against policy rules
    3. Emit trigger signals when policy conditions are met
    4. Support maintenance mode awareness

Advisory Signals Subscribed:
    - Q_PROMOTIONS_DETECTED: Unacknowledged D-REAM promotions exist

Trigger Signals Emitted:
    - Q_DREAM_TRIGGER: KLoROS decided to run D-REAM

Policy Logic:
    Current: Simple rule-based decisions
        - If promotions detected → trigger D-REAM

    Future: Introspective LLM reasoning considering:
        - Full system context
        - Recent failures or issues
        - Resource availability
        - Historical patterns

This is Phase 4 of the event-driven orchestrator migration.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub

logger = logging.getLogger(__name__)

MAINTENANCE_MODE_FILE = Path("/home/kloros/.kloros/maintenance_mode")
DEFAULT_FAILED_SIGNALS_LOG = Path("/home/kloros/.kloros/failed_signals.jsonl")


class KLoROSPolicyEngine:
    """
    Autonomous policy engine for KLoROS orchestration decisions.

    Listens to advisory signals and triggers major workflows based on policy rules.
    """

    def __init__(
        self,
        failed_signals_log: Path = DEFAULT_FAILED_SIGNALS_LOG,
        chem_pub: Optional[ChemPub] = None,
        chem_sub: Optional[ChemSub] = None,
    ):
        """
        Initialize KLoROS policy engine.

        Args:
            failed_signals_log: Path to dead letter queue for failed signal processing
            chem_pub: Optional ChemPub instance (for testing with mocks)
            chem_sub: Optional ChemSub instance (for testing with mocks)
        """
        self.failed_signals_log = Path(failed_signals_log)
        self.failed_signals_log.parent.mkdir(parents=True, exist_ok=True)

        self._processed_incidents: Set[str] = set()
        self._last_cleanup = time.time()
        self._cleanup_interval_s = 3600
        self.loop = None

        self.chem_pub = chem_pub if chem_pub is not None else ChemPub()

        if chem_sub is None:
            self.chem_sub = ChemSub(
                topic="Q_PROMOTIONS_DETECTED",
                on_json=self._on_signal_received
            )
        else:
            self.chem_sub = chem_sub

        logger.info("[kloros_policy] Initialized")
        logger.info(f"[kloros_policy] Failed signals log: {self.failed_signals_log}")
        logger.info("[kloros_policy] Subscribed to: Q_PROMOTIONS_DETECTED")

    def _is_maintenance_mode(self) -> bool:
        """
        Check if system is in maintenance mode.

        Returns:
            True if maintenance mode is active
        """
        return MAINTENANCE_MODE_FILE.exists()

    def _write_dead_letter(self, signal: Dict[str, Any], error: str):
        """
        Write failed signal to dead letter queue.

        Args:
            signal: The signal that failed to process
            error: Error message describing the failure
        """
        try:
            entry = {
                "signal": signal,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "daemon": "kloros_policy_engine"
            }

            with open(self.failed_signals_log, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.warning(f"[kloros_policy] Wrote failed signal to dead letter queue: {error}")

        except Exception as e:
            logger.error(f"[kloros_policy] Failed to write to dead letter queue: {e}", exc_info=True)

    def _cleanup_processed_incidents(self):
        """
        Periodically cleanup old processed incident IDs from memory.

        Keeps memory usage bounded by clearing incident cache every hour.
        """
        current_time = time.time()
        if current_time - self._last_cleanup > self._cleanup_interval_s:
            self._processed_incidents.clear()
            self._last_cleanup = current_time
            logger.debug("[kloros_policy] Cleaned up processed incidents cache")

    def _on_signal_received(self, msg: Dict[str, Any]):
        """
        Callback for ChemSub when signal received.

        Args:
            msg: Decoded JSON message from chemical bus
        """
        incident_id = msg.get('incident_id')
        if incident_id and incident_id in self._processed_incidents:
            logger.debug(f"[kloros_policy] Skipping duplicate incident: {incident_id}")
            return

        if incident_id:
            self._processed_incidents.add(incident_id)

        self._cleanup_processed_incidents()

        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(self._process_advisory(msg), self.loop)
        else:
            asyncio.create_task(self._process_advisory(msg))

    async def _process_advisory(self, msg: Dict[str, Any]):
        """
        Evaluate advisory signal and decide whether to trigger action.

        Args:
            msg: Chemical signal message with signal type and facts
        """
        try:
            signal_type = msg.get('signal')
            facts = msg.get('facts', {})

            logger.info(f"[kloros_policy] Processing advisory: {signal_type}")
            logger.debug(f"[kloros_policy] Advisory facts: {facts}")

            if self._is_maintenance_mode():
                logger.info("[kloros_policy] System in maintenance mode, skipping policy action")
                return

            if signal_type == "Q_PROMOTIONS_DETECTED":
                await self._handle_promotions_detected(facts)
            else:
                logger.warning(f"[kloros_policy] Unknown signal type: {signal_type}")

        except Exception as e:
            logger.error(f"[kloros_policy] Error processing advisory: {e}", exc_info=True)
            self._write_dead_letter(msg, str(e))

    async def _handle_promotions_detected(self, facts: Dict[str, Any]):
        """
        Handle Q_PROMOTIONS_DETECTED advisory signal.

        Policy: If promotions exist → trigger D-REAM

        Args:
            facts: Signal facts containing promotion details
        """
        try:
            promotion_count = facts.get('promotion_count', 0)

            if promotion_count <= 0:
                logger.debug("[kloros_policy] No promotions to process")
                return

            logger.info(
                f"[kloros_policy] Policy decision: {promotion_count} promotions detected → "
                "triggering D-REAM"
            )

            trigger_facts = {
                "reason": "unacknowledged_promotions_detected",
                "topic": None,
                "promotion_count": promotion_count,
                "source": "kloros_policy_engine",
                "oldest_promotion_age_hours": facts.get('oldest_promotion_age_hours')
            }

            self._emit_trigger("Q_DREAM_TRIGGER", trigger_facts)

        except Exception as e:
            logger.error(f"[kloros_policy] Error handling promotions: {e}", exc_info=True)
            raise

    def _emit_trigger(self, signal_type: str, facts: Dict[str, Any]):
        """
        Emit trigger signal to execute major workflow.

        Args:
            signal_type: Trigger signal name (e.g., Q_DREAM_TRIGGER)
            facts: Trigger facts with decision context
        """
        try:
            self.chem_pub.emit(
                signal=signal_type,
                ecosystem="orchestration",
                intensity=1.0,
                facts=facts
            )
            logger.info(f"[kloros_policy] Emitted {signal_type} with facts: {facts}")

        except Exception as e:
            logger.error(f"[kloros_policy] Failed to emit trigger {signal_type}: {e}", exc_info=True)
            raise

    async def run_async(self):
        """
        Run the policy engine daemon (async version).

        Maintains the event loop to allow ChemSub callback processing.
        """
        logger.info("[kloros_policy] Starting policy engine daemon")
        self.loop = asyncio.get_event_loop()

        try:
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("[kloros_policy] Received shutdown signal")
        except Exception as e:
            logger.error(f"[kloros_policy] Fatal error: {e}", exc_info=True)
        finally:
            self.chem_sub.close()
            self.chem_pub.close()
            logger.info("[kloros_policy] Daemon stopped")

    def run(self):
        """
        Run the policy engine daemon (sync wrapper for asyncio).
        """
        asyncio.run(self.run_async())


def main():
    """Entry point for KLoROS policy engine daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    engine = KLoROSPolicyEngine()
    engine.run()


if __name__ == "__main__":
    main()
