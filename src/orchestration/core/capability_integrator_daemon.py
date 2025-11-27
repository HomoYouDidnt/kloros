#!/usr/bin/env python3
"""
Capability Integrator Daemon - Event-driven module integration service.

Purpose:
    Subscribe to Q_INVESTIGATION_COMPLETE signals and automatically integrate
    discovered modules into the capability registry.

    This daemon version of capability_integrator.py converts the oneshot
    batch processor into an event-driven service that reacts immediately
    to investigation completions.

Architecture:
    1. Subscribe to Q_INVESTIGATION_COMPLETE chemical signals
    2. Load investigation from curiosity_investigations.jsonl
    3. Apply existing integration logic from CapabilityIntegrator
    4. Emit Q_MODULE_INTEGRATED on success
    5. Emit Q_INTEGRATION_FAILED on failures
    6. Write failed signals to dead letter queue

This is Phase 2 of the event-driven orchestrator migration.
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus import _ZmqSub, UMNPub
from src.orchestration.core.maintenance_mode import wait_for_normal_mode
from src.orchestration.core.capability_integrator import CapabilityIntegrator

logger = logging.getLogger(__name__)

INVESTIGATIONS_LOG = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
INTEGRATED_LOG = Path("/home/kloros/.kloros/integrated_capabilities.jsonl")
CAPABILITIES_YAML = Path("/home/kloros/src/registry/capabilities.yaml")
LAST_PROCESSED_TIMESTAMP = Path("/home/kloros/.kloros/capability_integrator_last_processed.txt")
FAILED_SIGNALS_LOG = Path("/home/kloros/.kloros/failed_signals.jsonl")


class CapabilityIntegratorDaemon:
    """
    Event-driven capability integration daemon.

    Subscribes to Q_INVESTIGATION_COMPLETE signals and integrates modules
    into the capability registry using the existing CapabilityIntegrator logic.
    """

    def __init__(
        self,
        investigations_log: Path = INVESTIGATIONS_LOG,
        capabilities_yaml: Path = CAPABILITIES_YAML,
        integrated_log: Path = INTEGRATED_LOG,
        last_processed_timestamp: Path = LAST_PROCESSED_TIMESTAMP,
        failed_signals_log: Path = FAILED_SIGNALS_LOG,
    ):
        """Initialize daemon."""
        wait_for_normal_mode()

        self.investigations_log = investigations_log
        self.capabilities_yaml = capabilities_yaml
        self.integrated_log = integrated_log
        self.last_processed_timestamp = last_processed_timestamp
        self.failed_signals_log = failed_signals_log

        self.integrator = CapabilityIntegrator()
        self.chem_pub = UMNPub()
        self.running = False
        self.integration_count = 0

        self.subscriber = _ZmqSub(
            topic="Q_INVESTIGATION_COMPLETE",
            on_message=self._on_message
        )

        logger.info("[capability_integrator_daemon] Initialized and subscribed to Q_INVESTIGATION_COMPLETE")

    def _on_message(self, topic: str, payload: bytes):
        """Handle incoming Q_INVESTIGATION_COMPLETE signal."""
        try:
            msg = json.loads(payload.decode("utf-8"))

            facts = msg.get("facts", {})
            signal = msg.get("signal", "")
            incident_id = msg.get("incident_id", "")

            if signal == "Q_INVESTIGATION_COMPLETE":
                logger.info(f"[capability_integrator_daemon] Received {signal} (incident={incident_id})")
                self._process_investigation(msg)
            else:
                logger.debug(f"[capability_integrator_daemon] Ignoring signal: {signal}")

        except json.JSONDecodeError as e:
            logger.error(f"[capability_integrator_daemon] Failed to decode JSON: {e}")
            self._write_dead_letter(payload, f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"[capability_integrator_daemon] Failed to process message: {e}", exc_info=True)
            self._write_dead_letter(payload, f"Processing error: {e}")

    def _process_investigation(self, msg: Dict[str, Any]):
        """
        Process investigation complete signal and integrate if appropriate.

        This method wraps the existing CapabilityIntegrator logic and adds
        chemical signal emission for success/failure.
        """
        try:
            facts = msg.get("facts", {})
            investigation_timestamp = facts.get("investigation_timestamp")

            if not investigation_timestamp:
                logger.warning("[capability_integrator_daemon] No investigation_timestamp in signal, skipping")
                return

            investigation = self._load_investigation(investigation_timestamp)

            if not investigation:
                logger.warning(f"[capability_integrator_daemon] Investigation not found: {investigation_timestamp}")
                return

            should_integrate, reason = self.integrator._should_integrate(investigation)

            if not should_integrate:
                logger.debug(f"[capability_integrator_daemon] Skipping integration: {reason}")
                return

            module_path = self.integrator._extract_module_path(investigation)
            if not module_path:
                logger.warning("[capability_integrator_daemon] No module_path in investigation")
                self._emit_integration_failed(investigation, "no_module_path")
                return

            module_name = module_path.split(".")[-1]
            module_info = self.integrator._extract_module_info(investigation)
            probe_results = investigation.get("probe_results", [])

            init_success, init_reason = self.integrator._ensure_module_init(
                module_path, module_name, module_info
            )
            if init_reason == "created":
                logger.info(f"[capability_integrator_daemon] Created __init__.py for {module_name}")

            capability_entry = self.integrator._generate_capability_entry(
                module_name, module_path, module_info, probe_results
            )

            success, update_reason = self.integrator._update_capabilities_yaml(
                module_name, capability_entry
            )

            if success:
                self.integration_count += 1
                self.integrator._mark_integrated(investigation.get("capability", "unknown"), investigation)
                self.integrator.integrated_ids.add(investigation.get("capability", "unknown"))

                logger.info(f"[capability_integrator_daemon] Integrated {module_name} ({module_path})")

                self._emit_module_integrated(module_name, module_path, investigation)

            elif update_reason == "already_exists":
                logger.debug(f"[capability_integrator_daemon] Module {module_name} already exists in registry")

            else:
                logger.error(f"[capability_integrator_daemon] Failed to integrate {module_name}: {update_reason}")
                self._emit_integration_failed(investigation, update_reason)

        except Exception as e:
            logger.error(f"[capability_integrator_daemon] Integration processing failed: {e}", exc_info=True)
            self._write_dead_letter(json.dumps(msg).encode(), f"Integration error: {e}")

    def _load_investigation(self, timestamp: str) -> Dict[str, Any]:
        """Load investigation from log by timestamp."""
        if not self.investigations_log.exists():
            return None

        try:
            with open(self.investigations_log, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    investigation = json.loads(line)
                    if investigation.get("timestamp") == timestamp:
                        return investigation
        except Exception as e:
            logger.error(f"[capability_integrator_daemon] Failed to load investigation: {e}")

        return None

    def _emit_module_integrated(self, module_name: str, module_path: str, investigation: Dict[str, Any]):
        """Emit Q_MODULE_INTEGRATED signal on successful integration."""
        try:
            self.chem_pub.emit(
                signal="Q_MODULE_INTEGRATED",
                ecosystem="orchestration",
                intensity=1.0,
                facts={
                    "module_name": module_name,
                    "module_path": module_path,
                    "capability_key": investigation.get("capability", "unknown"),
                    "integrated_at": datetime.now(timezone.utc).isoformat(),
                    "investigation_timestamp": investigation.get("timestamp"),
                }
            )
            logger.info(f"[capability_integrator_daemon] Emitted Q_MODULE_INTEGRATED: {module_name}")
        except Exception as e:
            logger.error(f"[capability_integrator_daemon] Failed to emit Q_MODULE_INTEGRATED: {e}")

    def _emit_integration_failed(self, investigation: Dict[str, Any], reason: str):
        """Emit Q_INTEGRATION_FAILED signal on integration failure."""
        try:
            self.chem_pub.emit(
                signal="Q_INTEGRATION_FAILED",
                ecosystem="orchestration",
                intensity=1.0,
                facts={
                    "capability_key": investigation.get("capability", "unknown"),
                    "reason": reason,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "investigation_timestamp": investigation.get("timestamp"),
                }
            )
            logger.info(f"[capability_integrator_daemon] Emitted Q_INTEGRATION_FAILED: {reason}")
        except Exception as e:
            logger.error(f"[capability_integrator_daemon] Failed to emit Q_INTEGRATION_FAILED: {e}")

    def _write_dead_letter(self, payload: bytes, error: str):
        """Write failed signal to dead letter queue."""
        try:
            self.failed_signals_log.parent.mkdir(parents=True, exist_ok=True)

            entry = {
                "signal": payload.decode("utf-8", errors="replace"),
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "daemon": "capability_integrator_daemon"
            }

            with open(self.failed_signals_log, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.info(f"[capability_integrator_daemon] Wrote to dead letter queue: {error}")
        except Exception as e:
            logger.error(f"[capability_integrator_daemon] Failed to write dead letter: {e}")

    def run(self):
        """Run daemon main loop."""
        self.running = True
        logger.info("[capability_integrator_daemon] Starting daemon")

        try:
            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[capability_integrator_daemon] Received shutdown signal")
        finally:
            self.shutdown()

    def shutdown(self):
        """Gracefully shutdown daemon."""
        logger.info("[capability_integrator_daemon] Shutting down")
        self.running = False

        try:
            self.subscriber.close()
            self.chem_pub.close()
        except Exception as e:
            logger.error(f"[capability_integrator_daemon] Error during shutdown: {e}")

        logger.info(f"[capability_integrator_daemon] Processed {self.integration_count} integrations total")


def main():
    """Main entry point for daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    daemon = CapabilityIntegratorDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
