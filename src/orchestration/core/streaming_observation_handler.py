#!/usr/bin/env python3
"""
StreamingObservationHandler - Fast path for urgent system events

Complements batch reflection with real-time event-driven curiosity.

Architecture:
  - Batch Reflection (Deep Path): Comprehensive analysis every 300s
  - Streaming Handler (Fast Path): Immediate reaction to critical events

Design: Parallel paths approach - both feed the same investigation pipeline.

Author: Claude Code
Date: 2025-11-16
"""

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus import UMNPub, _ZmqSub
from src.orchestration.core.maintenance_mode import wait_for_normal_mode

logger = logging.getLogger(__name__)

EVENTS_LOG = Path("/home/kloros/.kloros/streaming_events.jsonl")


class StreamingObservationHandler:
    """
    Fast path for urgent system events requiring immediate curiosity.

    Filters OBSERVATION signals for actionable events and generates
    high-priority investigation questions in real-time.
    """

    def __init__(self):
        wait_for_normal_mode()

        self.running = False
        self.chem_pub = UMNPub()
        self.event_count = 0
        self.question_count = 0

        self.metrics_lock = threading.Lock()
        self.metrics_events_processed = 0
        self.metrics_questions_generated = 0

        EVENTS_LOG.parent.mkdir(parents=True, exist_ok=True)

        self.subscriber = _ZmqSub(
            topic="OBSERVATION",
            on_message=self._on_message
        )

        logger.info("[streaming_obs] Initialized and subscribed to OBSERVATION signals")

    def _is_urgent_event(self, observation: Dict[str, Any]) -> bool:
        """
        Determine if observation requires immediate investigation.

        Returns True for:
        - Permission errors
        - Capability gaps
        - Resource pressure
        - Critical errors
        - System degradation
        """
        facts = observation.get("facts", {})
        incident_id = facts.get("incident_id", "")
        ok = facts.get("ok", True)
        niche = facts.get("niche", "")

        if not ok:
            if "permission" in incident_id.lower():
                return True

            if "capability" in niche.lower():
                return True

            if "resource" in incident_id.lower():
                return True

            if any(keyword in incident_id.lower() for keyword in ["critical", "fatal", "error"]):
                return True

        return False

    def _extract_event_context(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant context from observation for question generation.

        Returns:
            Context dict with event type, details, and evidence
        """
        facts = observation.get("facts", {})

        return {
            "incident_id": facts.get("incident_id", "unknown"),
            "niche": facts.get("niche", "unknown"),
            "ok": facts.get("ok", True),
            "ttr_ms": facts.get("ttr_ms", 0),
            "ecosystem": observation.get("ecosystem", "unknown"),
            "timestamp": observation.get("ts", time.time()),
            "raw_facts": facts
        }

    def _generate_question_from_event(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate curiosity question from urgent event.

        Args:
            context: Event context dict

        Returns:
            Question dict ready for Q_CURIOSITY_INVESTIGATE emission, or None
        """
        incident_id = context.get("incident_id", "")
        niche = context.get("niche", "")

        if "permission" in incident_id.lower():
            file_path = context["raw_facts"].get("file_path", "unknown")

            question = {
                "question_id": f"permission_denied_{hash(file_path) & 0xFFFFFF:06x}",
                "question": f"Why can't KLoROS read {file_path}? This seems wrong for my own codebase.",
                "priority": 9.0,
                "hypothesis": f"PERMISSION_DENIED_{file_path}",
                "evidence": [
                    f"Permission denied on {file_path}",
                    f"Detected via OBSERVATION signal at {context.get('timestamp')}"
                ],
                "action_class": "investigate",
                "urgency": "high",
                "source": "streaming_observation"
            }

            logger.info(f"[streaming_obs] 🚨 Generated URGENT question: {question['question_id']}")
            return question

        if "capability" in niche.lower() and not context.get("ok"):
            capability_name = context["raw_facts"].get("capability_name", "unknown")

            question = {
                "question_id": f"capability_gap_{capability_name}",
                "question": f"Capability '{capability_name}' is missing or degraded. What substitute can I use?",
                "priority": 8.5,
                "hypothesis": f"CAPABILITY_GAP_{capability_name}",
                "evidence": [
                    f"Capability check failed: {capability_name}",
                    f"Niche: {niche}",
                    f"TTR: {context.get('ttr_ms')}ms"
                ],
                "action_class": "find_substitute",
                "urgency": "high",
                "source": "streaming_observation"
            }

            logger.info(f"[streaming_obs] 🚨 Generated URGENT question: {question['question_id']}")
            return question

        if "resource" in incident_id.lower():
            resource_type = "unknown"
            if "memory" in incident_id.lower():
                resource_type = "memory"
            elif "cpu" in incident_id.lower():
                resource_type = "cpu"
            elif "disk" in incident_id.lower():
                resource_type = "disk"

            question = {
                "question_id": f"resource_pressure_{resource_type}",
                "question": f"{resource_type.upper()} pressure detected. Should I take action?",
                "priority": 7.5,
                "hypothesis": f"RESOURCE_PRESSURE_{resource_type.upper()}",
                "evidence": [
                    f"Resource alert: {incident_id}",
                    f"TTR: {context.get('ttr_ms')}ms"
                ],
                "action_class": "investigate",
                "urgency": "medium",
                "source": "streaming_observation"
            }

            logger.info(f"[streaming_obs] ⚠️  Generated question: {question['question_id']}")
            return question

        return None

    def _emit_question(self, question: Dict[str, Any]):
        """
        Emit question as high-priority Q_CURIOSITY_INVESTIGATE signal.

        Args:
            question: Question dict
        """
        try:
            self.chem_pub.emit(
                signal="Q_CURIOSITY_INVESTIGATE",
                ecosystem="introspection",
                intensity=question.get("priority", 5.0) / 10.0,
                facts={
                    "question_id": question["question_id"],
                    "question": question["question"],
                    "hypothesis": question["hypothesis"],
                    "evidence": question["evidence"],
                    "action_class": question["action_class"],
                    "urgency": question.get("urgency", "normal"),
                    "source": "streaming_observation",
                    "timestamp": time.time()
                }
            )

            with self.metrics_lock:
                self.metrics_questions_generated += 1

            logger.info(
                f"[streaming_obs] ✓ Emitted {question['question_id']} "
                f"(priority={question.get('priority', 5.0):.1f})"
            )

        except Exception as e:
            logger.error(f"[streaming_obs] Failed to emit question: {e}", exc_info=True)

    def _log_event(self, observation: Dict[str, Any], question: Optional[Dict[str, Any]]):
        """
        Log event to streaming_events.jsonl for debugging.

        Args:
            observation: Original OBSERVATION signal
            question: Generated question dict, or None
        """
        try:
            log_entry = {
                "timestamp": time.time(),
                "observation": observation,
                "question_generated": question is not None,
                "question_id": question.get("question_id") if question else None
            }

            with open(EVENTS_LOG, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            logger.warning(f"[streaming_obs] Failed to log event: {e}")

    def _on_message(self, topic: str, payload: bytes):
        """
        Handle incoming OBSERVATION signal.

        Args:
            topic: Signal topic (should be "OBSERVATION")
            payload: JSON payload bytes
        """
        try:
            msg = json.loads(payload.decode("utf-8"))

            with self.metrics_lock:
                self.metrics_events_processed += 1

            if not self._is_urgent_event(msg):
                return

            self.event_count += 1

            context = self._extract_event_context(msg)

            question = self._generate_question_from_event(context)

            if question:
                self._emit_question(question)
                self.question_count += 1

            self._log_event(msg, question)

        except Exception as e:
            logger.error(f"[streaming_obs] Error processing observation: {e}", exc_info=True)

    def _log_metrics(self):
        """
        Periodically log metrics.
        """
        while self.running:
            time.sleep(60)

            with self.metrics_lock:
                events = self.metrics_events_processed
                questions = self.metrics_questions_generated

            logger.info(
                f"[streaming_obs] Metrics: {events} events processed, "
                f"{questions} questions generated"
            )

    def run(self):
        """
        Run streaming observation handler.
        """
        self.running = True

        logger.info("[streaming_obs] Starting StreamingObservationHandler")
        logger.info("[streaming_obs] Fast path active - urgent events will generate immediate questions")

        metrics_thread = threading.Thread(target=self._log_metrics, daemon=True)
        metrics_thread.start()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("[streaming_obs] Shutting down gracefully...")
            self.running = False


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    handler = StreamingObservationHandler()
    handler.run()


if __name__ == "__main__":
    main()
