#!/usr/bin/env python3
"""
Intent Router - Transitional bridge from intent files to chemical signals.

Purpose:
    Watches /home/kloros/.kloros/intents/ directory using inotify and converts
    legacy intent files into chemical signals on the ZMQ bus.

Architecture:
    1. Watch intents directory with inotify
    2. Read intent JSON files when written
    3. Map intent types to chemical signals (discover.module.* → Q_CURIOSITY_INVESTIGATE)
    4. Emit signals to ZMQ chemical bus
    5. Delete successfully processed intent files
    6. Write failures to dead letter queue

This is a transitional component - when KLoROS generates signals directly,
this daemon becomes obsolete.
"""

import json
import time
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

from kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub

logger = logging.getLogger(__name__)

DEFAULT_INTENT_DIR = "/home/kloros/.kloros/intents"
DEFAULT_DLQ_PATH = "/home/kloros/.kloros/failed_signals.jsonl"


class IntentRouter:
    """
    Routes intent files to chemical signals.
    """

    def __init__(self, intent_dir: str = DEFAULT_INTENT_DIR, dlq_path: str = DEFAULT_DLQ_PATH):
        self.intent_dir = Path(intent_dir)
        self.dlq_path = Path(dlq_path)
        self.chem_pub = ChemPub()
        self.processed_count = 0

        # Subscribe to Q_RUN_SCANNER signals for direct scanner execution
        self.scanner_sub = ChemSub(
            topic="Q_RUN_SCANNER",
            on_json=self._on_run_scanner_signal,
            zooid_name="intent_router_scanner",
            niche="introspection"
        )

        logger.info(f"[intent_router] Initialized with intent_dir={self.intent_dir}")
        logger.info(f"[intent_router] Dead letter queue: {self.dlq_path}")
        logger.info(f"[intent_router] Subscribed to Q_RUN_SCANNER signals")

    def _route_intent(self, intent_file: Path):
        """
        Read intent file and emit appropriate chemical signal.

        Args:
            intent_file: Path to intent JSON file
        """
        try:
            with open(intent_file, 'r') as f:
                intent = json.load(f)

            intent_type = intent.get('type') or intent.get('intent_type', '')
            intent_id = intent.get('id', 'unknown')
            intent_data = intent.get('data', {})

            if intent_type in ['discover.module', 'reinvestigate', 'curiosity_investigate',
                               'curiosity_propose_fix', 'curiosity_find_substitute', 'curiosity_explore']:
                signal_type = "Q_CURIOSITY_INVESTIGATE"
                facts = {
                    "question": intent_data.get('question', ''),
                    "question_id": intent_data.get('question_id', intent_id),
                    "priority": intent.get('priority', intent_data.get('priority', 'normal')),
                    "evidence": intent_data.get('evidence', []),
                    "hypothesis": intent_data.get('hypothesis', ''),
                    "capability_key": intent_data.get('capability_key', ''),
                    "action_class": intent_data.get('action_class', 'investigate')
                }

                self._emit_signal(signal_type, facts)

                intent_file.unlink()
                logger.info(f"[intent_router] Routed {intent_type} and deleted {intent_file.name}")
                self.processed_count += 1

            elif intent_type == "run_scanner":
                scanner_name = intent.get("scanner")

                if not scanner_name:
                    logger.error(f"[intent_router] run_scanner intent missing scanner name")
                    self._write_dead_letter(intent_file, "Missing scanner name")
                    intent_file.unlink()
                    return

                logger.info(f"[intent_router] Running scanner: {scanner_name}")

                try:
                    result = subprocess.run(
                        ["/home/kloros/.venv/bin/python3", "-m", f"src.registry.capability_scanners.{scanner_name}_scanner"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        cwd="/home/kloros"
                    )

                    if result.returncode != 0:
                        logger.error(f"[intent_router] Scanner {scanner_name} failed: {result.stderr}")
                    else:
                        logger.info(f"[intent_router] Scanner {scanner_name} completed successfully")

                except subprocess.TimeoutExpired:
                    logger.error(f"[intent_router] Scanner {scanner_name} timed out after 60s")

                except Exception as e:
                    logger.error(f"[intent_router] Scanner {scanner_name} execution error: {e}")

                intent_file.unlink()
                self.processed_count += 1

            else:
                logger.warning(f"[intent_router] Unknown intent type: {intent_type}")
                self._write_dead_letter(intent_file, f"Unknown intent type: {intent_type}")
                intent_file.unlink()

        except json.JSONDecodeError as e:
            logger.error(f"[intent_router] Failed to parse JSON from {intent_file}: {e}")
            self._write_dead_letter(intent_file, f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"[intent_router] Failed to route {intent_file}: {e}")
            self._write_dead_letter(intent_file, str(e))

    def _emit_signal(self, signal_type: str, facts: Dict[str, Any]):
        """
        Emit chemical signal to ZMQ bus.

        Args:
            signal_type: Signal name (e.g., Q_CURIOSITY_INVESTIGATE)
            facts: Signal facts dictionary
        """
        self.chem_pub.emit(
            signal=signal_type,
            ecosystem="introspection",
            intensity=1.0,
            facts=facts
        )
        logger.info(f"[intent_router] Emitted {signal_type}: {facts.get('question_id', 'unknown')}")

    def _on_run_scanner_signal(self, msg: Dict[str, Any]):
        """
        Handle Q_RUN_SCANNER signal by executing scanner subprocess.

        Args:
            msg: Signal message containing facts dict with 'scanner' field
        """
        facts = msg.get('facts', msg)
        scanner_name = facts.get("scanner")

        if not scanner_name:
            logger.error(f"[intent_router] Q_RUN_SCANNER signal missing scanner name")
            return

        logger.info(f"[intent_router] Running scanner from signal: {scanner_name}")

        try:
            result = subprocess.run(
                ["/home/kloros/.venv/bin/python3", "-m", f"src.registry.capability_scanners.{scanner_name}_scanner"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/home/kloros"
            )

            if result.returncode != 0:
                logger.error(f"[intent_router] Scanner {scanner_name} failed: {result.stderr}")
            else:
                logger.info(f"[intent_router] Scanner {scanner_name} completed successfully")

        except subprocess.TimeoutExpired:
            logger.error(f"[intent_router] Scanner {scanner_name} timed out after 60s")

        except Exception as e:
            logger.error(f"[intent_router] Scanner {scanner_name} execution error: {e}")

    def _write_dead_letter(self, intent_file: Path, error: str):
        """
        Write failed intent to dead letter queue.

        Args:
            intent_file: Path to failed intent file
            error: Error message
        """
        try:
            self.dlq_path.parent.mkdir(parents=True, exist_ok=True)

            dlq_entry = {
                "intent_file": str(intent_file),
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "daemon": "intent_router"
            }

            with open(self.dlq_path, 'a') as f:
                f.write(json.dumps(dlq_entry) + "\n")

            logger.warning(f"[intent_router] Wrote dead letter for {intent_file.name}")

        except Exception as e:
            logger.error(f"[intent_router] Failed to write dead letter: {e}", exc_info=True)

    def run(self):
        """
        Start watching intents directory with inotify.
        """
        import inotify.adapters

        logger.info(f"[intent_router] Starting intent file watcher on {self.intent_dir}")

        self.intent_dir.mkdir(parents=True, exist_ok=True)

        # Process any existing intent files first (backlog from before daemon started)
        existing_intents = list(self.intent_dir.glob("*.json"))
        if existing_intents:
            logger.info(f"[intent_router] Found {len(existing_intents)} existing intent files, processing backlog...")
            for intent_file in existing_intents:
                logger.info(f"[intent_router] Processing existing file: {intent_file.name}")
                self._route_intent(intent_file)
            logger.info(f"[intent_router] Backlog processing complete")

        watcher = inotify.adapters.Inotify()
        watcher.add_watch(str(self.intent_dir))

        logger.info("[intent_router] Watcher ready, waiting for new intent files...")

        try:
            for event in watcher.event_gen(yield_nones=False):
                (_, type_names, path, filename) = event

                if 'IN_CLOSE_WRITE' in type_names:
                    # CRITICAL: Ignore .tmp files to avoid race condition
                    # Observer writes to .tmp, closes it (triggers IN_CLOSE_WRITE),
                    # then renames to .json. We only process .json files.
                    if not filename.endswith('.json'):
                        logger.debug(f"[intent_router] Ignoring non-json file: {filename}")
                        continue

                    intent_file = Path(path) / filename
                    logger.debug(f"[intent_router] Detected new file: {filename}")
                    self._route_intent(intent_file)

        except KeyboardInterrupt:
            logger.info("[intent_router] Received shutdown signal")
        except Exception as e:
            logger.error(f"[intent_router] Fatal error: {e}", exc_info=True)
        finally:
            self.chem_pub.close()
            logger.info(f"[intent_router] Daemon stopped (processed {self.processed_count} intents)")


def main():
    """Entry point for intent router daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    router = IntentRouter()
    router.run()


if __name__ == "__main__":
    main()
