#!/usr/bin/env python3
"""
Reflection Consumer Daemon - Executes reflection cycles in response to trigger signals.

Purpose:
    Listens for Q_REFLECT_TRIGGER signals and performs idle reflection analysis.
    Decouples reflection from voice system audio loop to prevent blocking wake word detection.

Architecture:
    1. Subscribe to Q_REFLECT_TRIGGER signals via UMNSub
    2. Track last_reflection_ts to respect reflection_interval timing
    3. Execute reflection via IdleReflectionManager
    4. Emit Q_REFLECTION_COMPLETE with results via UMNPub
    5. Support maintenance mode awareness
    6. Dead letter queue for failures
    7. Metrics emission every 5 minutes

Signal Flow:
    Q_REFLECT_TRIGGER (subscribed) → IdleReflectionManager.perform_reflection() → Q_REFLECTION_COMPLETE (emitted)

Performance Characteristics:
    - Reflection execution is synchronous and blocking (by design - isolates blocking work from voice)
    - Expected duration: 10-60+ seconds depending on reflection depth
    - Single-threaded execution (one reflection at a time)
    - Interval enforcement prevents rapid-fire triggers (default: 600s between reflections)

This is part of the voice system refactor to remove blocking operations from the audio loop.
"""

import asyncio
import json
import logging
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus import UMNPub, UMNSub
from src.orchestration.core.umn_signals import Q_REFLECT_TRIGGER, Q_REFLECTION_COMPLETE
from src.cognition.mind.reflection import EnhancedIdleReflectionManager as IdleReflectionManager

logger = logging.getLogger(__name__)

MAINTENANCE_MODE_FILE = Path("/home/kloros/.kloros/maintenance_mode")
DEFAULT_FAILED_SIGNALS_LOG = Path("/home/kloros/.kloros/failed_signals.jsonl")


class ReflectionConsumerDaemon:
    """
    Reflection execution consumer daemon.

    Listens to Q_REFLECT_TRIGGER signals and executes reflection cycles via IdleReflectionManager.
    """

    def __init__(
        self,
        failed_signals_log: Path = DEFAULT_FAILED_SIGNALS_LOG,
        chem_pub: Optional[UMNPub] = None,
        chem_sub: Optional[UMNSub] = None,
    ):
        """
        Initialize reflection consumer daemon.

        Args:
            failed_signals_log: Path to dead letter queue for failed signal processing
            chem_pub: Optional UMNPub instance (for testing with mocks)
            chem_sub: Optional UMNSub instance (for testing with mocks)
        """
        self.failed_signals_log = Path(failed_signals_log)
        self.failed_signals_log.parent.mkdir(parents=True, exist_ok=True)

        self._processed_incidents: Set[str] = set()
        self._last_cleanup = time.time()
        self._cleanup_interval_s = 3600
        self.loop = None

        self.last_reflection_ts = 0.0
        self.reflection_interval = 600.0

        self.metrics_lock = threading.Lock()
        self.metrics_reflections_attempted = 0
        self.metrics_reflections_succeeded = 0
        self.metrics_reflections_failed = 0
        self.metrics_reflections_skipped = 0

        self.chem_pub = chem_pub if chem_pub is not None else UMNPub()

        self.reflection_manager = None
        try:
            self.reflection_manager = IdleReflectionManager(kloros_instance=None)
            if hasattr(self.reflection_manager, 'reflection_interval'):
                self.reflection_interval = self.reflection_manager.reflection_interval
            logger.info(f"[reflection_consumer] IdleReflectionManager initialized (interval: {self.reflection_interval}s)")
        except Exception as e:
            logger.error(f"[reflection_consumer] Failed to initialize IdleReflectionManager: {e}", exc_info=True)
            logger.warning("[reflection_consumer] Continuing without reflection manager - will log warnings on triggers")

        if chem_sub is None:
            self.chem_sub = UMNSub(
                topic=Q_REFLECT_TRIGGER,
                on_json=self._on_signal_received,
                zooid_name="reflection_consumer_daemon",
                niche="introspection"
            )
        else:
            self.chem_sub = chem_sub

        self._metrics_thread = threading.Thread(
            target=self._emit_metrics_summary,
            daemon=True
        )
        self._metrics_thread.start()

        logger.info("[reflection_consumer] Initialized")
        logger.info(f"[reflection_consumer] Failed signals log: {self.failed_signals_log}")
        logger.info(f"[reflection_consumer] Subscribed to: {Q_REFLECT_TRIGGER}")
        logger.info(f"[reflection_consumer] Reflection interval: {self.reflection_interval}s")

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
                "daemon": "reflection_consumer_daemon"
            }

            with open(self.failed_signals_log, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.warning(f"[reflection_consumer] Wrote failed signal to dead letter queue: {error}")

        except Exception as e:
            logger.error(f"[reflection_consumer] Failed to write to dead letter queue: {e}", exc_info=True)

    def _cleanup_processed_incidents(self):
        """
        Periodically cleanup old processed incident IDs from memory.

        Keeps memory usage bounded by clearing incident cache every hour.
        """
        current_time = time.time()
        if current_time - self._last_cleanup > self._cleanup_interval_s:
            self._processed_incidents.clear()
            self._last_cleanup = current_time
            logger.debug("[reflection_consumer] Cleaned up processed incidents cache")

    def _emit_metrics_summary(self):
        """Emit METRICS_SUMMARY every 5 minutes."""
        while True:
            time.sleep(300)

            try:
                with self.metrics_lock:
                    attempted = self.metrics_reflections_attempted
                    succeeded = self.metrics_reflections_succeeded
                    failed = self.metrics_reflections_failed
                    skipped = self.metrics_reflections_skipped

                    self.metrics_reflections_attempted = 0
                    self.metrics_reflections_succeeded = 0
                    self.metrics_reflections_failed = 0
                    self.metrics_reflections_skipped = 0

                self.chem_pub.emit(
                    signal="METRICS_SUMMARY",
                    ecosystem="introspection",
                    facts={
                        "daemon": "reflection_consumer",
                        "window_duration_s": 300,
                        "reflections_attempted": attempted,
                        "reflections_succeeded": succeeded,
                        "reflections_failed": failed,
                        "reflections_skipped_interval": skipped,
                        "success_rate": succeeded / max(attempted, 1) if attempted > 0 else 0.0
                    }
                )

            except Exception as e:
                logger.error(f"[reflection_consumer] Metrics summary emission failed: {e}")

    def _on_signal_received(self, msg: Dict[str, Any]):
        """
        Callback for UMNSub when signal received.

        Args:
            msg: Decoded JSON message from chemical bus
        """
        incident_id = msg.get('incident_id')
        if incident_id and incident_id in self._processed_incidents:
            logger.debug(f"[reflection_consumer] Skipping duplicate incident: {incident_id}")
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
        Process Q_REFLECT_TRIGGER signal and execute reflection.

        Args:
            msg: Chemical signal message with signal type and facts
        """
        try:
            signal_type = msg.get('signal')
            facts = msg.get('facts', {})

            logger.info(f"[reflection_consumer] Processing trigger: {signal_type}")
            logger.debug(f"[reflection_consumer] Trigger facts: {facts}")

            if self._is_maintenance_mode():
                logger.info("[reflection_consumer] System in maintenance mode, skipping reflection")
                return

            if signal_type == Q_REFLECT_TRIGGER:
                await self._handle_reflection_trigger(facts)
            else:
                logger.warning(f"[reflection_consumer] Unknown signal type: {signal_type}")

        except Exception as e:
            logger.error(f"[reflection_consumer] Error processing trigger: {e}", exc_info=True)
            self._write_dead_letter(msg, str(e))

    async def _handle_reflection_trigger(self, facts: Dict[str, Any]):
        """
        Handle Q_REFLECT_TRIGGER signal by executing reflection.

        Args:
            facts: Trigger facts containing reason, idle_seconds, reflection_depth, force
        """
        try:
            trigger_reason = facts.get('trigger_reason', 'unknown')
            idle_seconds = facts.get('idle_seconds', 0)
            reflection_depth = facts.get('reflection_depth', 4)
            force = facts.get('force', False)

            with self.metrics_lock:
                self.metrics_reflections_attempted += 1

            logger.info(
                f"[reflection_consumer] Reflection trigger: reason={trigger_reason}, "
                f"idle={idle_seconds}s, depth={reflection_depth}, force={force}"
            )

            if not self.reflection_manager:
                logger.error("[reflection_consumer] No reflection manager available - cannot execute reflection")
                with self.metrics_lock:
                    self.metrics_reflections_failed += 1
                return

            current_time = time.time()
            time_since_last = current_time - self.last_reflection_ts

            if not force and time_since_last < self.reflection_interval:
                remaining = self.reflection_interval - time_since_last
                logger.info(
                    f"[reflection_consumer] Skipping reflection - interval not elapsed "
                    f"(last: {time_since_last:.1f}s ago, need: {self.reflection_interval}s, "
                    f"remaining: {remaining:.1f}s)"
                )
                with self.metrics_lock:
                    self.metrics_reflections_skipped += 1
                return

            logger.info(f"[reflection_consumer] Executing reflection (last reflection: {time_since_last:.1f}s ago)")

            reflection_start = time.time()

            self.reflection_manager.perform_enhanced_reflection()

            reflection_duration = time.time() - reflection_start
            self.last_reflection_ts = time.time()

            logger.info(f"[reflection_consumer] Reflection completed in {reflection_duration:.2f}s")

            with self.metrics_lock:
                self.metrics_reflections_succeeded += 1

            self._emit_completion(
                success=True,
                processing_time_ms=reflection_duration * 1000,
                trigger_reason=trigger_reason,
                reflection_depth=reflection_depth
            )

        except Exception as e:
            logger.error(f"[reflection_consumer] Error executing reflection: {e}", exc_info=True)
            with self.metrics_lock:
                self.metrics_reflections_failed += 1
            self._emit_completion(
                success=False,
                error=str(e),
                trigger_reason=facts.get('trigger_reason', 'unknown')
            )

    def _emit_completion(
        self,
        success: bool,
        processing_time_ms: float = 0.0,
        trigger_reason: str = "unknown",
        reflection_depth: int = 4,
        error: Optional[str] = None
    ):
        """
        Emit Q_REFLECTION_COMPLETE signal with execution results.

        Args:
            success: Whether reflection completed successfully
            processing_time_ms: Time taken for reflection in milliseconds
            trigger_reason: Original trigger reason
            reflection_depth: Number of reflection phases executed
            error: Error message if reflection failed
        """
        try:
            completion_facts = {
                "success": success,
                "processing_time_ms": processing_time_ms,
                "trigger_reason": trigger_reason,
                "reflection_depth": reflection_depth,
                "timestamp": time.time(),
                "source": "reflection_consumer_daemon"
            }

            if error:
                completion_facts["error"] = error

            if success and hasattr(self.reflection_manager, 'enhanced_manager'):
                enhanced = self.reflection_manager.enhanced_manager
                if enhanced and hasattr(enhanced, 'cycle_number'):
                    completion_facts["cycle_number"] = getattr(enhanced, 'cycle_number', 0)

            self.chem_pub.emit(
                signal=Q_REFLECTION_COMPLETE,
                ecosystem="introspection",
                intensity=1.0,
                facts=completion_facts
            )

            logger.info(f"[reflection_consumer] Emitted Q_REFLECTION_COMPLETE: success={success}")

        except Exception as e:
            logger.error(f"[reflection_consumer] Failed to emit completion signal: {e}", exc_info=True)
            raise

    async def run_async(self):
        """
        Run the reflection consumer daemon (async version).

        Maintains the event loop to allow UMNSub callback processing.
        """
        logger.info("[reflection_consumer] Starting reflection consumer daemon")
        self.loop = asyncio.get_event_loop()

        try:
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("[reflection_consumer] Received shutdown signal")
        except Exception as e:
            logger.error(f"[reflection_consumer] Fatal error: {e}", exc_info=True)
        finally:
            self.chem_sub.close()
            self.chem_pub.close()
            logger.info("[reflection_consumer] Daemon stopped")

    def run(self):
        """
        Run the reflection consumer daemon (sync wrapper for asyncio).
        """
        asyncio.run(self.run_async())


def main():
    """Entry point for reflection consumer daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    daemon = ReflectionConsumerDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
