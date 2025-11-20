#!/usr/bin/env python3
"""
Action Consumer Daemon - KLoROS's hands to fix what she investigates.

Purpose:
    Subscribe to Q_INVESTIGATION_COMPLETE signals and trigger autonomous fixes
    when investigations find actionable solutions.

    This daemon gives KLoROS the ability to:
    - SEE investigation results (eyes)
    - ACT on actionable findings (hands)
    - SPAWN SPICA instances to test fixes
    - LEARN from fix success/failure

Architecture:
    1. Subscribe to Q_INVESTIGATION_COMPLETE chemical signals
    2. Check if investigation has actionable solution (analysis.actionable == true)
    3. For actionable findings:
       - Spawn SPICA instance with fix attempt
       - Apply documented solution or generated code patch
       - Run tests in isolation
       - Place successful fixes in escrow for review
    4. Track success/failure rates for learning
"""

import json
import logging
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import _ZmqSub, ChemPub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode
from integrations.spica_spawn import spawn_instance

logger = logging.getLogger(__name__)

INVESTIGATIONS_LOG = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
ACTIONS_LOG = Path("/home/kloros/.kloros/autonomous_actions.jsonl")


class ActionConsumer:
    """
    KLoROS's autonomous action system - watches investigations and acts on findings.

    This is the missing link between:
    - Investigation (understanding problems)
    - Action (fixing problems)
    """

    def __init__(self):
        wait_for_normal_mode()

        self.running = False
        self.chem_pub = ChemPub()
        self.action_count = 0
        self.success_count = 0
        self.failure_count = 0

        # Resource limits - start conservative
        self.max_concurrent_actions = 2
        self.action_semaphore = threading.Semaphore(self.max_concurrent_actions)

        # Metrics
        self.metrics_lock = threading.Lock()
        self.metrics_actions_attempted = 0
        self.metrics_actions_succeeded = 0
        self.metrics_actions_failed = 0

        self.subscriber = _ZmqSub(
            topic="Q_INVESTIGATION_COMPLETE",
            on_message=self._on_message
        )

        logger.info("[action_consumer] Initialized and subscribed to Q_INVESTIGATION_COMPLETE")

        # Start metrics thread
        self._metrics_thread = threading.Thread(
            target=self._emit_metrics_summary,
            daemon=True
        )
        self._metrics_thread.start()

    def _emit_metrics_summary(self):
        """Emit METRICS_SUMMARY every 5 minutes."""
        while True:
            time.sleep(300)

            try:
                with self.metrics_lock:
                    attempted = self.metrics_actions_attempted
                    succeeded = self.metrics_actions_succeeded
                    failed = self.metrics_actions_failed
                    self.metrics_actions_attempted = 0
                    self.metrics_actions_succeeded = 0
                    self.metrics_actions_failed = 0

                self.chem_pub.emit(
                    signal="METRICS_SUMMARY",
                    ecosystem="introspection",
                    facts={
                        "daemon": "action_consumer",
                        "window_duration_s": 300,
                        "actions_attempted": attempted,
                        "actions_succeeded": succeeded,
                        "actions_failed": failed,
                        "success_rate": succeeded / max(attempted, 1)
                    }
                )

            except Exception as e:
                logger.error(f"[action_consumer] Metrics summary emission failed: {e}")

    def _on_message(self, topic: str, payload: bytes):
        """Handle incoming Q_INVESTIGATION_COMPLETE signal."""
        try:
            msg = json.loads(payload.decode("utf-8"))

            facts = msg.get("facts", {})
            signal = msg.get("signal", "")

            if signal == "Q_INVESTIGATION_COMPLETE":
                investigation_timestamp = facts.get("investigation_timestamp")
                question_id = facts.get("question_id", "unknown")

                logger.info(f"[action_consumer] Received investigation completion for {question_id}")

                # Load full investigation from log
                investigation = self._load_investigation(investigation_timestamp)

                if not investigation:
                    logger.warning(f"[action_consumer] Investigation not found: {investigation_timestamp}")
                    return

                # Check if investigation is actionable
                if self._is_actionable(investigation):
                    logger.info(f"[action_consumer] 👁️ EYES: Found actionable solution for {question_id}")

                    # Spawn action attempt in background thread
                    thread = threading.Thread(
                        target=self._attempt_autonomous_action,
                        args=(investigation,),
                        daemon=True
                    )
                    thread.start()
                else:
                    logger.debug(f"[action_consumer] Investigation {question_id} not actionable")

        except json.JSONDecodeError as e:
            logger.error(f"[action_consumer] Failed to decode JSON: {e}")
        except Exception as e:
            logger.error(f"[action_consumer] Failed to process message: {e}", exc_info=True)

    def _load_investigation(self, timestamp: str) -> Dict[str, Any]:
        """Load investigation from log by timestamp."""
        if not timestamp:
            return None

        if not INVESTIGATIONS_LOG.exists():
            return None

        try:
            with open(INVESTIGATIONS_LOG, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    investigation = json.loads(line)
                    if investigation.get("timestamp") == timestamp:
                        return investigation
        except Exception as e:
            logger.error(f"[action_consumer] Failed to load investigation: {e}")

        return None

    def _is_actionable(self, investigation: Dict[str, Any]) -> bool:
        """
        Check if investigation found an actionable solution.

        Returns True if:
        - Analysis contains 'actionable': true
        - Has specific action_type (not 'unknown')
        - Provides recommendation
        """
        analysis = investigation.get("analysis", {})

        if not analysis.get("actionable"):
            return False

        action_type = analysis.get("action_type", "unknown")
        if action_type == "unknown":
            return False

        recommendation = analysis.get("recommendation", "")
        if not recommendation or len(recommendation) < 10:
            return False

        return True

    def _attempt_autonomous_action(self, investigation: Dict[str, Any]):
        """
        Attempt autonomous action based on investigation findings.

        This gives KLoROS hands to fix what her eyes discovered.
        """
        with self.action_semaphore:
            question_id = investigation.get("question_id", "unknown")
            analysis = investigation.get("analysis", {})
            action_type = analysis.get("action_type", "unknown")
            recommendation = analysis.get("recommendation", "")

            logger.info(f"[action_consumer] 🤲 HANDS: Attempting {action_type} fix for {question_id}")

            action_start = time.time()
            action_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "question_id": question_id,
                "action_type": action_type,
                "recommendation": recommendation,
                "investigation_timestamp": investigation.get("timestamp"),
                "status": "attempted"
            }

            try:
                with self.metrics_lock:
                    self.metrics_actions_attempted += 1

                # For now, spawn SPICA instance with documented solution
                # Future: LLM code generation for complex fixes
                spica_id = self._spawn_fix_instance(investigation)

                if spica_id:
                    action_record["spica_id"] = spica_id
                    action_record["status"] = "spawned"
                    action_record["duration_ms"] = int((time.time() - action_start) * 1000)

                    logger.info(f"[action_consumer] ✓ Spawned SPICA instance {spica_id} for {question_id}")

                    with self.metrics_lock:
                        self.metrics_actions_succeeded += 1
                    self.success_count += 1

                    # Emit success signal
                    self.chem_pub.emit(
                        signal="Q_ACTION_SPAWNED",
                        ecosystem="introspection",
                        facts={
                            "question_id": question_id,
                            "spica_id": spica_id,
                            "action_type": action_type
                        }
                    )
                else:
                    action_record["status"] = "failed"
                    action_record["error"] = "SPICA spawn returned None"

                    with self.metrics_lock:
                        self.metrics_actions_failed += 1
                    self.failure_count += 1

            except Exception as e:
                logger.error(f"[action_consumer] Action attempt failed for {question_id}: {e}")
                action_record["status"] = "failed"
                action_record["error"] = str(e)
                action_record["duration_ms"] = int((time.time() - action_start) * 1000)

                with self.metrics_lock:
                    self.metrics_actions_failed += 1
                self.failure_count += 1

            # Log action attempt
            self._log_action(action_record)
            self.action_count += 1

    def _spawn_fix_instance(self, investigation: Dict[str, Any]) -> str:
        """
        Spawn SPICA instance to test the fix.

        Returns:
            spica_id if successful, None otherwise
        """
        question_id = investigation.get("question_id", "unknown")
        analysis = investigation.get("analysis", {})

        try:
            # Spawn instance with investigation context
            spica_id = spawn_instance(
                mutations={
                    "investigation_context": {
                        "question_id": question_id,
                        "action_type": analysis.get("action_type"),
                        "recommendation": analysis.get("recommendation"),
                        "confidence": analysis.get("confidence", 0.0)
                    }
                },
                notes=f"Autonomous fix attempt for {question_id}",
                auto_prune=True
            )

            return spica_id

        except Exception as e:
            logger.error(f"[action_consumer] SPICA spawn failed: {e}")
            return None

    def _log_action(self, action_record: Dict[str, Any]):
        """Log action attempt to actions log."""
        try:
            ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)

            with open(ACTIONS_LOG, 'a') as f:
                f.write(json.dumps(action_record) + '\n')

        except Exception as e:
            logger.error(f"[action_consumer] Failed to log action: {e}")

    def run(self):
        """Run daemon main loop."""
        self.running = True
        logger.info("[action_consumer] 👁️🤲 Action consumer daemon running - giving KLoROS eyes and hands")

        try:
            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[action_consumer] Received shutdown signal")
        finally:
            self.shutdown()

    def shutdown(self):
        """Gracefully shutdown daemon."""
        logger.info("[action_consumer] Shutting down")
        self.running = False

        try:
            self.subscriber.close()
            self.chem_pub.close()
        except Exception as e:
            logger.error(f"[action_consumer] Error during shutdown: {e}")

        logger.info(f"[action_consumer] Processed {self.action_count} actions "
                   f"({self.success_count} succeeded, {self.failure_count} failed)")


def main():
    """Main entry point for daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    daemon = ActionConsumer()
    daemon.run()


if __name__ == "__main__":
    main()
