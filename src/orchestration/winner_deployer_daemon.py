#!/usr/bin/env python3
"""
Winner Deployer Daemon - Event-driven D-REAM winner deployment service.

Purpose:
    Subscribe to Q_DREAM_COMPLETE signals and automatically deploy
    D-REAM winners to close the autonomous learning loop.

    This daemon version of winner_deployer.py converts the oneshot
    batch processor into an event-driven service that reacts immediately
    to D-REAM cycle completions.

Architecture:
    1. Subscribe to Q_DREAM_COMPLETE chemical signals
    2. Scan winners directory for new winners
    3. Apply existing deployment logic from WinnerDeployer
    4. Emit Q_WINNER_DEPLOYED on success
    5. Emit Q_DEPLOYMENT_FAILED on failures
    6. Write failed signals to dead letter queue

This is Phase 2 of the event-driven orchestrator migration.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import _ZmqSub, ChemPub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode
from kloros.orchestration.winner_deployer import WinnerDeployer

logger = logging.getLogger(__name__)

WINNERS_DIR = Path("/home/kloros/artifacts/dream/winners")
DREAM_CONFIG_PATH = Path("/home/kloros/src/dream/config/dream.yaml")
STATE_PATH = Path("/home/kloros/.kloros/winner_deployer_state.json")
FAILED_SIGNALS_LOG = Path("/home/kloros/.kloros/failed_signals.jsonl")


class WinnerDeployerDaemon:
    """
    Event-driven D-REAM winner deployment daemon.

    Subscribes to Q_DREAM_COMPLETE signals and deploys winners
    using the existing WinnerDeployer logic.
    """

    def __init__(
        self,
        winners_dir: Path = WINNERS_DIR,
        dream_config_path: Path = DREAM_CONFIG_PATH,
        state_path: Path = STATE_PATH,
        failed_signals_log: Path = FAILED_SIGNALS_LOG,
        autonomy_level: int = None,
    ):
        """Initialize daemon."""
        wait_for_normal_mode()

        self.winners_dir = winners_dir
        self.dream_config_path = dream_config_path
        self.state_path = state_path
        self.failed_signals_log = failed_signals_log

        if autonomy_level is None:
            autonomy_level = int(os.getenv("KLR_AUTONOMY_LEVEL", "0"))
        self.autonomy_level = autonomy_level

        self.deployer = WinnerDeployer(
            winners_dir=self.winners_dir,
            dream_config_path=self.dream_config_path,
            state_path=self.state_path,
            autonomy_level=self.autonomy_level
        )

        self.chem_pub = ChemPub()
        self.running = False
        self.deployment_count = 0

        self.subscriber = _ZmqSub(
            topic="Q_DREAM_COMPLETE",
            on_message=self._on_message
        )

        logger.info("[winner_deployer_daemon] Initialized and subscribed to Q_DREAM_COMPLETE")

    def _on_message(self, topic: str, payload: bytes):
        """Handle incoming Q_DREAM_COMPLETE signal."""
        try:
            msg = json.loads(payload.decode("utf-8"))

            facts = msg.get("facts", {})
            signal = msg.get("signal", "")
            incident_id = msg.get("incident_id", "")

            if signal == "Q_DREAM_COMPLETE":
                logger.info(f"[winner_deployer_daemon] Received {signal} (incident={incident_id})")
                self._process_deployment(msg)
            else:
                logger.debug(f"[winner_deployer_daemon] Ignoring signal: {signal}")

        except json.JSONDecodeError as e:
            logger.error(f"[winner_deployer_daemon] Failed to decode JSON: {e}")
            self._write_dead_letter(payload, f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"[winner_deployer_daemon] Failed to process message: {e}", exc_info=True)
            self._write_dead_letter(payload, f"Processing error: {e}")

    def _process_deployment(self, msg: Dict[str, Any]):
        """
        Process D-REAM complete signal and deploy winners.

        This method wraps the existing WinnerDeployer logic and adds
        chemical signal emission for success/failure.
        """
        try:
            facts = msg.get("facts", {})
            dream_cycle_id = facts.get("dream_cycle_id", "unknown")

            logger.info(f"[winner_deployer_daemon] Running deployment cycle for D-REAM cycle {dream_cycle_id}")

            result = self.deployer.watch_and_deploy()

            deployed = result.get("deployed", 0)
            failed = result.get("failed", 0)
            skipped = result.get("skipped", 0)

            logger.info(f"[winner_deployer_daemon] Deployment result: deployed={deployed}, failed={failed}, skipped={skipped}")

            if deployed > 0:
                self.deployment_count += deployed
                self._emit_winner_deployed(dream_cycle_id, deployed, result)

            if failed > 0:
                self._emit_deployment_failed(dream_cycle_id, failed, result)

        except Exception as e:
            logger.error(f"[winner_deployer_daemon] Deployment processing failed: {e}", exc_info=True)
            self._write_dead_letter(json.dumps(msg).encode(), f"Deployment error: {e}")
            self._emit_deployment_failed(msg.get("facts", {}).get("dream_cycle_id", "unknown"), 1, {"error": str(e)})

    def _emit_winner_deployed(self, dream_cycle_id: str, count: int, result: Dict[str, Any]):
        """Emit Q_WINNER_DEPLOYED signal on successful deployment."""
        try:
            self.chem_pub.emit(
                signal="Q_WINNER_DEPLOYED",
                ecosystem="orchestration",
                intensity=1.0,
                facts={
                    "dream_cycle_id": dream_cycle_id,
                    "winners_deployed": count,
                    "deployed_at": datetime.now(timezone.utc).isoformat(),
                    "deployment_result": result,
                }
            )
            logger.info(f"[winner_deployer_daemon] Emitted Q_WINNER_DEPLOYED: {count} winners")
        except Exception as e:
            logger.error(f"[winner_deployer_daemon] Failed to emit Q_WINNER_DEPLOYED: {e}")

    def _emit_deployment_failed(self, dream_cycle_id: str, count: int, result: Dict[str, Any]):
        """Emit Q_DEPLOYMENT_FAILED signal on deployment failure."""
        try:
            self.chem_pub.emit(
                signal="Q_DEPLOYMENT_FAILED",
                ecosystem="orchestration",
                intensity=1.0,
                facts={
                    "dream_cycle_id": dream_cycle_id,
                    "failures": count,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "deployment_result": result,
                }
            )
            logger.info(f"[winner_deployer_daemon] Emitted Q_DEPLOYMENT_FAILED: {count} failures")
        except Exception as e:
            logger.error(f"[winner_deployer_daemon] Failed to emit Q_DEPLOYMENT_FAILED: {e}")

    def _write_dead_letter(self, payload: bytes, error: str):
        """Write failed signal to dead letter queue."""
        try:
            self.failed_signals_log.parent.mkdir(parents=True, exist_ok=True)

            entry = {
                "signal": payload.decode("utf-8", errors="replace"),
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "daemon": "winner_deployer_daemon"
            }

            with open(self.failed_signals_log, 'a') as f:
                f.write(json.dumps(entry) + '\n')

            logger.info(f"[winner_deployer_daemon] Wrote to dead letter queue: {error}")
        except Exception as e:
            logger.error(f"[winner_deployer_daemon] Failed to write dead letter: {e}")

    def run(self):
        """Run daemon main loop."""
        self.running = True
        logger.info("[winner_deployer_daemon] Starting daemon")

        try:
            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[winner_deployer_daemon] Received shutdown signal")
        finally:
            self.shutdown()

    def shutdown(self):
        """Gracefully shutdown daemon."""
        logger.info("[winner_deployer_daemon] Shutting down")
        self.running = False

        try:
            self.subscriber.close()
            self.chem_pub.close()
        except Exception as e:
            logger.error(f"[winner_deployer_daemon] Error during shutdown: {e}")

        logger.info(f"[winner_deployer_daemon] Processed {self.deployment_count} deployments total")


def main():
    """Main entry point for daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    daemon = WinnerDeployerDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
