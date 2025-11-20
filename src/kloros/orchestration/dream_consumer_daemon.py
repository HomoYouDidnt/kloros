#!/usr/bin/env python3
"""
D-REAM Consumer Daemon - Executes D-REAM in response to trigger signals.

Purpose:
    Listens for Q_DREAM_TRIGGER signals from the KLoROS policy engine and
    executes D-REAM evolutionary optimization cycles. Emits Q_DREAM_COMPLETE
    signals with execution results.

Architecture:
    1. Subscribe to Q_DREAM_TRIGGER signals via chemical bus (ChemSub)
    2. Extract trigger facts (reason, topic, promotion_count)
    3. Execute D-REAM via dream_trigger.run_once()
    4. Emit Q_DREAM_COMPLETE signal with execution results
    5. Support maintenance mode awareness
    6. Dead letter queue for failures

Signal Flow:
    Q_DREAM_TRIGGER (subscribed) → dream_trigger.run_once() → Q_DREAM_COMPLETE (emitted)

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
from kloros.orchestration import dream_trigger

logger = logging.getLogger(__name__)

MAINTENANCE_MODE_FILE = Path("/home/kloros/.kloros/maintenance_mode")
DEFAULT_FAILED_SIGNALS_LOG = Path("/home/kloros/.kloros/failed_signals.jsonl")


class DreamConsumerDaemon:
    """
    D-REAM execution consumer daemon.

    Listens to Q_DREAM_TRIGGER signals and executes D-REAM cycles.
    """

    def __init__(
        self,
        failed_signals_log: Path = DEFAULT_FAILED_SIGNALS_LOG,
        chem_pub: Optional[ChemPub] = None,
        chem_sub: Optional[ChemSub] = None,
    ):
        """
        Initialize D-REAM consumer daemon.

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
                topic="Q_DREAM_TRIGGER",
                on_json=self._on_signal_received
            )
        else:
            self.chem_sub = chem_sub

        logger.info("[dream_consumer] Initialized")
        logger.info(f"[dream_consumer] Failed signals log: {self.failed_signals_log}")
        logger.info("[dream_consumer] Subscribed to: Q_DREAM_TRIGGER")

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
                "daemon": "dream_consumer_daemon"
            }

            with open(self.failed_signals_log, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.warning(f"[dream_consumer] Wrote failed signal to dead letter queue: {error}")

        except Exception as e:
            logger.error(f"[dream_consumer] Failed to write to dead letter queue: {e}", exc_info=True)

    def _cleanup_processed_incidents(self):
        """
        Periodically cleanup old processed incident IDs from memory.

        Keeps memory usage bounded by clearing incident cache every hour.
        """
        current_time = time.time()
        if current_time - self._last_cleanup > self._cleanup_interval_s:
            self._processed_incidents.clear()
            self._last_cleanup = current_time
            logger.debug("[dream_consumer] Cleaned up processed incidents cache")

    def _on_signal_received(self, msg: Dict[str, Any]):
        """
        Callback for ChemSub when signal received.

        Args:
            msg: Decoded JSON message from chemical bus
        """
        incident_id = msg.get('incident_id')
        if incident_id and incident_id in self._processed_incidents:
            logger.debug(f"[dream_consumer] Skipping duplicate incident: {incident_id}")
            return

        if incident_id:
            self._processed_incidents.add(incident_id)

        self._cleanup_processed_incidents()

        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(self._process_trigger(msg), self.loop)
        else:
            asyncio.create_task(self._process_trigger(msg))

    async def _process_trigger(self, msg: Dict[str, Any]):
        """
        Process Q_DREAM_TRIGGER signal and execute D-REAM.

        Args:
            msg: Chemical signal message with signal type and facts
        """
        try:
            signal_type = msg.get('signal')
            facts = msg.get('facts', {})

            logger.info(f"[dream_consumer] Processing trigger: {signal_type}")
            logger.debug(f"[dream_consumer] Trigger facts: {facts}")

            if self._is_maintenance_mode():
                logger.info("[dream_consumer] System in maintenance mode, skipping D-REAM execution")
                return

            if signal_type == "Q_DREAM_TRIGGER":
                await self._handle_dream_trigger(facts)
            else:
                logger.warning(f"[dream_consumer] Unknown signal type: {signal_type}")

        except Exception as e:
            logger.error(f"[dream_consumer] Error processing trigger: {e}", exc_info=True)
            self._write_dead_letter(msg, str(e))

    async def _handle_dream_trigger(self, facts: Dict[str, Any]):
        """
        Handle Q_DREAM_TRIGGER signal by executing D-REAM.

        Args:
            facts: Trigger facts containing reason, topic, promotion_count
        """
        try:
            topic = facts.get('topic')
            reason = facts.get('reason', 'unknown')
            promotion_count = facts.get('promotion_count', 0)

            logger.info(
                f"[dream_consumer] Executing D-REAM: reason={reason}, topic={topic}, "
                f"promotion_count={promotion_count}"
            )

            result = dream_trigger.run_once(topic=topic)

            logger.info(
                f"[dream_consumer] D-REAM execution completed: exit_code={result.exit_code}, "
                f"generation={result.generation}, duration={result.duration_s:.1f}s"
            )

            self._emit_completion(result, facts)

        except Exception as e:
            logger.error(f"[dream_consumer] Error executing D-REAM: {e}", exc_info=True)
            raise

    def _emit_completion(self, result, trigger_facts: Dict[str, Any]):
        """
        Emit Q_DREAM_COMPLETE signal with execution results.

        Args:
            result: DreamResult from dream_trigger.run_once()
            trigger_facts: Original trigger facts for context
        """
        try:
            completion_facts = {
                "exit_code": result.exit_code,
                "generation": result.generation,
                "promotion_path": str(result.promotion_path) if result.promotion_path else None,
                "telemetry_path": str(result.telemetry_path) if result.telemetry_path else None,
                "run_tag": result.run_tag,
                "duration_s": result.duration_s,
                "success": result.exit_code == 0,
                "trigger_reason": trigger_facts.get('reason'),
                "trigger_topic": trigger_facts.get('topic'),
                "promotion_count": trigger_facts.get('promotion_count'),
                "source": "dream_consumer_daemon"
            }

            self.chem_pub.emit(
                signal="Q_DREAM_COMPLETE",
                ecosystem="orchestration",
                intensity=1.0,
                facts=completion_facts
            )

            logger.info(f"[dream_consumer] Emitted Q_DREAM_COMPLETE: success={completion_facts['success']}")

        except Exception as e:
            logger.error(f"[dream_consumer] Failed to emit completion signal: {e}", exc_info=True)
            raise

    async def run_async(self):
        """
        Run the dream consumer daemon (async version).

        Maintains the event loop to allow ChemSub callback processing.
        """
        logger.info("[dream_consumer] Starting dream consumer daemon")
        self.loop = asyncio.get_event_loop()

        try:
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("[dream_consumer] Received shutdown signal")
        except Exception as e:
            logger.error(f"[dream_consumer] Fatal error: {e}", exc_info=True)
        finally:
            self.chem_sub.close()
            self.chem_pub.close()
            logger.info("[dream_consumer] Daemon stopped")

    def run(self):
        """
        Run the dream consumer daemon (sync wrapper for asyncio).
        """
        asyncio.run(self.run_async())


def main():
    """Entry point for D-REAM consumer daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    daemon = DreamConsumerDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
