"""
Study Memory Bridge Daemon - KLoROS Self-Study to Episodic Memory Integration

Bridges component_self_study (knowledge.db) and episodic memory (memory.db + Qdrant),
enabling KLoROS to actively recall component knowledge learned through self-study.

Architecture:
- Subscribes to LEARNING_COMPLETED signals on ChemBus
- Transforms study data into tiered memory events based on depth
- Logs via MemoryLogger (generates episodic events + Qdrant embeddings)
- Handles failures with dead letter queue + investigation trigger

Aligned with KLoROS-Prime doctrine: Precision, Self-Consistency, Evolution.
"""

import json
import logging
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from kloros.orchestration.chem_bus_v2 import ChemSub, ChemPub
from kloros_memory.logger import MemoryLogger
from kloros_memory.models import EventType


class DeadLetterQueue:
    """
    Dead letter queue for failed study-to-memory events.

    Stores failed events in SQLite for investigation and replay.
    Enables autonomous error recovery without blocking the pipeline.
    """

    def __init__(self, db_path: str = "/home/kloros/.kloros/memory.db"):
        """
        Initialize dead letter queue.

        Args:
            db_path: Path to memory database
        """
        self.db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize dead letter queue schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS failed_study_events (
                id INTEGER PRIMARY KEY,
                signal_data TEXT NOT NULL,
                error_message TEXT,
                failed_at REAL,
                retry_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending'
            )
        """)
        conn.commit()
        conn.close()

    def store(self, signal_data: Dict[str, Any], error: str) -> int:
        """
        Store a failed event for later replay.

        Args:
            signal_data: The signal data that failed to process
            error: Error message describing the failure

        Returns:
            ID of the stored failed event
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO failed_study_events (signal_data, error_message, failed_at, retry_count, status)
            VALUES (?, ?, ?, 0, 'pending')
        """, (json.dumps(signal_data), error, time.time()))

        event_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logging.warning(f"[study_bridge] Stored failed event {event_id} in dead letter queue: {error}")
        return event_id

    def get_pending(self, limit: int = 10, max_retries: int = 5) -> list[tuple[int, Dict[str, Any]]]:
        """
        Get pending failed events for retry.

        Args:
            limit: Maximum number of events to return
            max_retries: Maximum number of retry attempts before giving up

        Returns:
            List of (event_id, signal_data) tuples
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, signal_data FROM failed_study_events
            WHERE status = 'pending' AND retry_count < ?
            ORDER BY failed_at ASC
            LIMIT ?
        """, (max_retries, limit))

        results = []
        for row in cursor.fetchall():
            event_id = row[0]
            signal_data = json.loads(row[1])
            results.append((event_id, signal_data))

        conn.close()
        return results

    def mark_resolved(self, event_id: int) -> None:
        """
        Mark a failed event as resolved after successful replay.

        Args:
            event_id: ID of the event to mark resolved
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            UPDATE failed_study_events
            SET status = 'resolved'
            WHERE id = ?
        """, (event_id,))
        conn.commit()
        conn.close()

    def increment_retry(self, event_id: int) -> None:
        """
        Increment retry count for a failed event.

        Args:
            event_id: ID of the event to increment
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            UPDATE failed_study_events
            SET retry_count = retry_count + 1
            WHERE id = ?
        """, (event_id,))
        conn.commit()
        conn.close()

    def get_statistics(self) -> Dict[str, int]:
        """
        Get statistics about the dead letter queue.

        Returns:
            Dict with pending, investigating, and resolved counts
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM failed_study_events WHERE status = 'pending'")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM failed_study_events WHERE status = 'investigating'")
        investigating = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM failed_study_events WHERE status = 'resolved'")
        resolved = cursor.fetchone()[0]

        conn.close()

        return {
            "pending": pending,
            "investigating": investigating,
            "resolved": resolved
        }


class StudyMemoryBridge:
    """
    Bridge daemon connecting self-study system to episodic memory.

    Subscribes to LEARNING_COMPLETED signals from component_self_study,
    transforms them into memory events with tiered detail based on depth,
    and logs them for semantic recall.
    """

    def __init__(self):
        """Initialize the study memory bridge."""
        self.memory_logger = MemoryLogger()
        self.dead_letter = DeadLetterQueue(db_path="/home/kloros/.kloros/memory.db")
        self.publisher = ChemPub()

        self.subscriber = ChemSub(
            topic="LEARNING_COMPLETED",
            on_json=self._on_learning_completed
        )

        self.running = True

        logging.info("[study_bridge] StudyMemoryBridge initialized")

    def _format_by_depth(self, signal_data: Dict[str, Any]) -> str:
        """
        Format memory content based on study depth.

        Implements tiered detail logic:
        - Depth 0-1: Component ID, type, file path, studied_at
        - Depth 2: Above + purpose, key capabilities
        - Depth 3: Above + dependencies, config, examples, findings, improvements

        Args:
            signal_data: Signal facts from LEARNING_COMPLETED

        Returns:
            Formatted memory content string
        """
        facts = signal_data.get("facts", {})
        study_depth = facts.get("study_depth", 0)
        component_id = facts.get("component_id", "unknown")
        component_type = facts.get("component_type", "unknown")

        if study_depth <= 1:
            return f"Scanned component {component_id} (type: {component_type})"

        elif study_depth == 2:
            purpose = facts.get("purpose", "No purpose documented")
            capabilities = facts.get("capabilities", [])

            cap_text = ""
            if capabilities:
                top_caps = capabilities[:3]
                cap_text = f". Capabilities: {', '.join(top_caps)}"

            return f"Studied component {component_id}: {purpose}{cap_text}"

        else:
            purpose = facts.get("purpose", "No purpose documented")
            capabilities = facts.get("capabilities", [])
            dependencies = facts.get("dependencies", [])
            config_params = facts.get("config_params", {})
            findings = facts.get("interesting_findings", "")
            improvements = facts.get("potential_improvements", "")

            parts = [f"Analyzed component {component_id}: {purpose}"]

            if capabilities:
                parts.append(f"Capabilities: {', '.join(capabilities[:5])}")

            if dependencies:
                parts.append(f"Dependencies: {', '.join(dependencies[:5])}")

            if config_params:
                param_names = list(config_params.keys())[:3]
                parts.append(f"Config parameters: {', '.join(param_names)}")

            if findings:
                parts.append(f"Findings: {findings}")

            if improvements:
                parts.append(f"Improvements: {improvements}")

            return ". ".join(parts)

    def _on_learning_completed(self, signal_data: Dict[str, Any], is_replay: bool = False) -> None:
        """
        Handle LEARNING_COMPLETED signal from ChemBus.

        Transforms study data into memory event and logs it.
        On failure, stores in dead letter queue and triggers investigation.

        Args:
            signal_data: Signal data from ChemBus
            is_replay: Whether this is a replay from dead letter queue
        """
        try:
            facts = signal_data.get("facts", {})
            component_id = facts.get("component_id", "unknown")

            logging.info(f"[study_bridge] Processing learning completion for {component_id}")

            memory_content = self._format_by_depth(signal_data)

            self.memory_logger.log_event(
                event_type=EventType.DOCUMENTATION_LEARNED,
                content=memory_content,
                metadata=facts
            )

            logging.info(f"[study_bridge] Logged learning event for {component_id}")

        except Exception as e:
            logging.error(f"[study_bridge] Failed to process learning event: {e}", exc_info=True)

            if not is_replay:
                self.dead_letter.store(signal_data, error=str(e))

                self._trigger_investigation(error=e, context=signal_data)

            raise

    def _trigger_investigation(self, error: Exception, context: Dict[str, Any]) -> None:
        """
        Trigger investigation by emitting CAPABILITY_GAP_FOUND signal.

        Args:
            error: The exception that occurred
            context: The signal data that caused the error
        """
        try:
            component_id = context.get("facts", {}).get("component_id", "unknown")

            self.publisher.emit(
                signal="CAPABILITY_GAP_FOUND",
                ecosystem="introspection",
                intensity=2.0,
                facts={
                    "source": "study_memory_bridge",
                    "capability": "memory_logging",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "failed_component": component_id,
                    "context": context
                }
            )

            logging.warning(f"[study_bridge] Triggered investigation for memory system failure: {error}")

        except Exception as e:
            logging.error(f"[study_bridge] Failed to trigger investigation: {e}")

    def replay_failed_events(self) -> int:
        """
        Replay failed events from dead letter queue.

        Returns:
            Number of events successfully replayed
        """
        pending = self.dead_letter.get_pending(limit=10)
        replayed = 0

        for event_id, signal_data in pending:
            try:
                self._on_learning_completed(signal_data, is_replay=True)
                self.dead_letter.mark_resolved(event_id)
                replayed += 1
                logging.info(f"[study_bridge] Successfully replayed event {event_id}")

            except Exception as e:
                self.dead_letter.increment_retry(event_id)
                logging.warning(f"[study_bridge] Failed to replay event {event_id}: {e}")

        return replayed

    def run(self) -> None:
        """Run the bridge daemon main loop."""
        logging.info("[study_bridge] Bridge daemon running")

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        retry_interval = 300
        last_retry = time.time()

        try:
            while self.running:
                time.sleep(1)

                if time.time() - last_retry > retry_interval:
                    replayed = self.replay_failed_events()
                    if replayed > 0:
                        logging.info(f"[study_bridge] Replayed {replayed} failed events")
                    last_retry = time.time()

        except KeyboardInterrupt:
            logging.info("[study_bridge] Received interrupt, shutting down")
        finally:
            self.shutdown()

    def _handle_signal(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logging.info(f"[study_bridge] Received signal {signum}, shutting down")
        self.running = False

    def shutdown(self) -> None:
        """Shutdown the bridge daemon."""
        logging.info("[study_bridge] Shutting down bridge daemon")

        try:
            self.memory_logger.close()
        except Exception as e:
            logging.error(f"[study_bridge] Error closing memory logger: {e}")

        try:
            self.subscriber.close()
        except Exception as e:
            logging.error(f"[study_bridge] Error closing subscriber: {e}")

        try:
            self.publisher.close()
        except Exception as e:
            logging.error(f"[study_bridge] Error closing publisher: {e}")

        logging.info("[study_bridge] Bridge daemon shut down complete")


def main():
    """Main entry point for the daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        bridge = StudyMemoryBridge()
        bridge.run()
    except Exception as e:
        logging.error(f"[study_bridge] Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
