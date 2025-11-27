#!/usr/bin/env python3
"""
CuriosityCore Consumer Daemon - Converts capability gaps into curiosity questions.

Subscribes to CAPABILITY_GAP signals from introspection scanners and uses
CuriosityCore to generate investigation questions, writing them to curiosity_feed.json.

This is the bridge between proactive system observation (introspection) and
question generation (curiosity).
"""

import sys
import json
import logging
import os
import time
import tracemalloc
from pathlib import Path
from typing import Dict, Any

import psutil

sys.path.insert(0, str(Path(__file__).parents[3]))
sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

from src.orchestration.core.umn_bus import UMNSub, UMNPub
from src.orchestration.core.maintenance_mode import wait_for_normal_mode
from src.cognition.mind.cognition.curiosity_core import CuriosityCore
from src.cognition.mind.cognition.capability_evaluator import CapabilityEvaluator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

CURIOSITY_FEED = Path("/home/kloros/.kloros/curiosity_feed.json")


class CuriosityCoreConsumerDaemon:
    """
    CuriosityCore consumer daemon.

    Listens for CAPABILITY_GAP signals and generates curiosity questions.
    """

    def __init__(self, proactive_interval: float = 60.0):
        """Initialize CuriosityCore consumer daemon.

        Args:
            proactive_interval: Seconds between proactive question generation (default: 60s)
        """
        self.running = True
        self.gap_count = 0
        self.question_count = 0
        self.proactive_interval = proactive_interval
        self.last_proactive_ts = 0.0

        tracemalloc.start()
        self.last_memory_snapshot = time.time()

        # Initialize CuriosityCore and capability evaluator
        try:
            self.evaluator = CapabilityEvaluator()
            self.capability_matrix = self.evaluator.evaluate_all()
            self.curiosity_core = CuriosityCore(feed_path=CURIOSITY_FEED, enable_daemon_subscriptions=True)
            logger.info(f"[curiosity_core_consumer] Initialized with {self.capability_matrix.total_count} capabilities")
        except Exception as e:
            logger.warning(f"[curiosity_core_consumer] Could not initialize: {e}")
            self.evaluator = None
            self.capability_matrix = None
            self.curiosity_core = None

        # Always initialize UMNPub for SYSTEM_HEALTH monitoring
        try:
            self.chem_pub = UMNPub()
        except Exception as e:
            logger.warning(f"[curiosity_core_consumer] Could not initialize UMNPub: {e}")
            self.chem_pub = None

        # Subscribe to capability gap signals
        self.chem_sub = UMNSub(
            topic="CAPABILITY_GAP",
            on_json=self._on_capability_gap,
            zooid_name="curiosity_core_consumer",
            niche="curiosity"
        )

        self.cleanup_duplicate_questions()

    def _on_capability_gap(self, msg: Dict[str, Any]) -> None:
        """
        Callback invoked for each CAPABILITY_GAP message.

        Args:
            msg: CAPABILITY_GAP message dict
        """
        if not self.running:
            return

        try:
            wait_for_normal_mode()

            facts = msg.get("facts", {})
            gap_type = facts.get("gap_type")
            gap_name = facts.get("gap_name")
            gap_category = facts.get("gap_category")

            logger.info(f"[curiosity_core_consumer] Received capability gap: {gap_category}/{gap_name}")
            self.gap_count += 1

            # Generate questions from this gap
            if self.curiosity_core:
                questions = self._generate_questions_for_gap(facts)

                if questions:
                    self._append_to_curiosity_feed(questions)
                    self.question_count += len(questions)
                    logger.info(f"[curiosity_core_consumer] Generated {len(questions)} questions for gap {gap_name}")
                else:
                    logger.debug(f"[curiosity_core_consumer] No questions generated for gap {gap_name}")
            else:
                logger.warning(f"[curiosity_core_consumer] CuriosityCore not initialized, skipping gap")

        except Exception as e:
            logger.error(f"[curiosity_core_consumer] Error processing capability gap: {e}", exc_info=True)

    def _generate_questions_for_gap(self, gap_facts: Dict[str, Any]) -> list:
        """
        Generate curiosity questions for a capability gap.

        Args:
            gap_facts: Facts about the capability gap

        Returns:
            List of CuriosityQuestion objects
        """
        try:
            # Refresh capability matrix to include this gap
            if self.evaluator:
                self.capability_matrix = self.evaluator.evaluate_all()

            # Generate all questions from current matrix
            feed = self.curiosity_core.generate_questions_from_matrix(self.capability_matrix)

            # Return all questions (CuriosityCore deduplicates internally)
            return feed.questions if feed else []

        except Exception as e:
            logger.error(f"[curiosity_core_consumer] Error generating questions: {e}", exc_info=True)
            return []

    def _append_to_curiosity_feed(self, questions: list) -> None:
        """
        Emit questions directly to investigation consumers via CuriosityCore.emit_questions_to_bus.

        This bypasses the file-based handoff and curiosity_processor middleman.

        Args:
            questions: List of CuriosityQuestion objects (used only for logging)
        """
        try:
            if self.curiosity_core and self.curiosity_core.chem_pub:
                result = self.curiosity_core.emit_questions_to_bus()
                logger.debug(f"[curiosity_core_consumer] Emitted {result.get('emitted', 0)} questions directly")
            else:
                logger.warning("[curiosity_core_consumer] Direct emission unavailable, writing to feed file")
                self.curiosity_core.write_feed_json()

        except Exception as e:
            logger.error(f"[curiosity_core_consumer] Error emitting questions: {e}", exc_info=True)

    def run(self) -> None:
        """
        Main daemon loop - proactive question generation + reactive gap processing.

        Generates questions proactively every 60 seconds (like old orchestrator did)
        AND reactively when CAPABILITY_GAP signals arrive.
        This makes KLoROS truly autonomous - continuously examining capabilities
        rather than waiting only for detected gaps.
        """
        import time

        logger.info("[curiosity_core_consumer] Starting CuriosityCore consumer daemon")
        logger.info(f"[curiosity_core_consumer] Subscribed to CAPABILITY_GAP signals")
        logger.info(f"[curiosity_core_consumer] Proactive generation interval: {self.proactive_interval}s")
        logger.info(f"[curiosity_core_consumer] Writing to: {CURIOSITY_FEED}")

        try:
            while self.running:
                wait_for_normal_mode()

                # Proactive question generation on timer
                now = time.time()
                if now - self.last_proactive_ts >= self.proactive_interval:
                    logger.debug(f"[curiosity_core_consumer] Proactive question generation triggered")
                    self._generate_all_questions()
                    self.last_proactive_ts = now

                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[curiosity_core_consumer] Keyboard interrupt received")

        finally:
            self.shutdown()

    def _check_memory_usage(self) -> None:
        """
        Check memory and trigger cleanup if needed.

        Triggers proactive cleanup at 4500MB and emergency cleanup at 5000MB.
        These thresholds scale appropriately for the 62GB system RAM.
        """
        try:
            mem_info = psutil.Process().memory_info()
            mem_mb = mem_info.rss / 1024 / 1024

            if mem_mb > 5000:
                logger.error(f"[curiosity_core_consumer] Memory critical: {mem_mb:.1f}MB, triggering emergency cleanup")
                self._emergency_cleanup()
            elif mem_mb > 4500:
                logger.warning(f"[curiosity_core_consumer] Memory high: {mem_mb:.1f}MB, triggering proactive cleanup")
                self._proactive_cleanup()
        except Exception as e:
            logger.debug(f"[curiosity_core_consumer] Error checking memory: {e}")

    def _proactive_cleanup(self) -> None:
        """
        Release memory before hitting limits.

        Trims curiosity feed to last 100 questions, clears caches, and runs garbage collection.
        """
        try:
            if CURIOSITY_FEED.exists():
                with open(CURIOSITY_FEED, 'r') as f:
                    feed = json.load(f)

                if len(feed.get('questions', [])) > 100:
                    feed['questions'] = feed['questions'][-100:]
                    with open(CURIOSITY_FEED, 'w') as f:
                        json.dump(feed, f, indent=2)
                    logger.info(f"[curiosity_core_consumer] Trimmed curiosity feed to 100 questions")

            if hasattr(self, 'curiosity_core') and self.curiosity_core:
                semantic_store = getattr(self.curiosity_core, 'semantic_store', None)
                if semantic_store and hasattr(semantic_store, 'clear_cache'):
                    semantic_store.clear_cache()

            import gc
            gc.collect()
            logger.info("[curiosity_core_consumer] Proactive cleanup completed")
        except Exception as e:
            logger.error(f"[curiosity_core_consumer] Error during proactive cleanup: {e}", exc_info=True)

    def _emergency_cleanup(self) -> None:
        """
        Aggressive cleanup at critical memory levels.

        Trims to last 20 questions, clears all caches, forces garbage collection,
        and emits SYSTEM_HEALTH signal for external monitoring.
        """
        try:
            if CURIOSITY_FEED.exists():
                with open(CURIOSITY_FEED, 'r') as f:
                    feed = json.load(f)
                feed['questions'] = feed['questions'][-20:]
                with open(CURIOSITY_FEED, 'w') as f:
                    json.dump(feed, f, indent=2)
                logger.warning(f"[curiosity_core_consumer] Emergency: Trimmed curiosity feed to 20 questions")

            if hasattr(self, 'curiosity_core') and self.curiosity_core:
                semantic_store = getattr(self.curiosity_core, 'semantic_store', None)
                if semantic_store and hasattr(semantic_store, 'clear_cache'):
                    semantic_store.clear_cache()

            import gc
            gc.collect()

            if hasattr(self, 'chem_pub') and self.chem_pub:
                mem_mb = psutil.Process().memory_info().rss / 1024 / 1024
                self.chem_pub.emit(
                    signal="SYSTEM_HEALTH",
                    ecosystem="orchestration",
                    facts={
                        "component": "curiosity_core_consumer",
                        "status": "memory_critical",
                        "memory_mb": mem_mb
                    }
                )

            logger.warning("[curiosity_core_consumer] Emergency cleanup completed")
        except Exception as e:
            logger.error(f"[curiosity_core_consumer] Error during emergency cleanup: {e}", exc_info=True)

    def _log_memory_top_consumers(self) -> None:
        """
        Log top memory consumers for diagnostics.

        Runs every 5 minutes to track memory allocation patterns.
        """
        try:
            if time.time() - self.last_memory_snapshot < 300:
                return

            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')

            logger.debug("[curiosity_core_consumer][memory_profile] Top 10 memory consumers:")
            for stat in top_stats[:10]:
                logger.debug(f"  {stat}")

            self.last_memory_snapshot = time.time()
        except Exception as e:
            logger.debug(f"[curiosity_core_consumer] Error logging memory profile: {e}")

    def _generate_all_questions(self) -> None:
        """
        Generate all curiosity questions proactively.

        This is called on a timer to continuously examine the system,
        just like the old orchestrator did.
        """
        if not self.curiosity_core:
            logger.warning("[curiosity_core_consumer] CuriosityCore not initialized, skipping proactive generation")
            return

        try:
            # Refresh capability matrix
            if self.evaluator:
                self.capability_matrix = self.evaluator.evaluate_all()

            # Generate all questions from current matrix
            feed = self.curiosity_core.generate_questions_from_matrix(self.capability_matrix)
            questions = feed.questions if feed else []

            if questions:
                # Emit directly to investigation consumers (bypasses processor middleman)
                result = self.curiosity_core.emit_questions_to_bus()
                self.question_count += result.get('emitted', 0)
                logger.info(f"[curiosity_core_consumer] Proactive generation: "
                           f"{result.get('emitted', 0)} emitted, "
                           f"{result.get('skipped_low_value', 0)} low-value, "
                           f"{result.get('skipped_processed', 0)} already processed")
            else:
                logger.debug("[curiosity_core_consumer] Proactive generation: 0 questions")

            # Check memory usage after generation
            self._check_memory_usage()

            # Log memory profiling info periodically
            self._log_memory_top_consumers()

        except Exception as e:
            logger.error(f"[curiosity_core_consumer] Proactive generation failed: {e}", exc_info=True)

    def cleanup_duplicate_questions(self) -> None:
        """
        Remove duplicate/orphaned questions from curiosity feed on startup.

        Removes questions with null evidence_hash and consolidates duplicate
        capability_key entries (keeping highest value_estimate).

        This helps prevent infinite loops where low-confidence followup questions
        repeatedly regenerate.
        """
        try:
            if not CURIOSITY_FEED.exists():
                logger.debug("[curiosity_core_consumer] Curiosity feed not found, skipping cleanup")
                return

            with open(CURIOSITY_FEED, 'r') as f:
                feed = json.load(f)

            if not feed.get('questions'):
                logger.debug("[curiosity_core_consumer] No questions in feed, skipping cleanup")
                return

            initial_count = len(feed['questions'])

            questions = feed['questions']

            removed_null_hash = [q for q in questions if q.get('evidence_hash') is None]
            questions = [q for q in questions if q.get('evidence_hash') is not None]
            null_hash_count = len(removed_null_hash)

            seen_keys = {}
            unique_questions = []
            duplicate_count = 0

            for q in questions:
                key = q.get('capability_key')
                if key:
                    if key not in seen_keys:
                        seen_keys[key] = q.get('value_estimate', 0)
                        unique_questions.append(q)
                    elif q.get('value_estimate', 0) > seen_keys[key]:
                        for i, existing_q in enumerate(unique_questions):
                            if existing_q.get('capability_key') == key:
                                unique_questions[i] = q
                                duplicate_count += 1
                                break
                    else:
                        duplicate_count += 1
                else:
                    unique_questions.append(q)

            feed['questions'] = unique_questions
            final_count = len(unique_questions)

            with open(CURIOSITY_FEED, 'w') as f:
                json.dump(feed, f, indent=2)

            logger.info(f"[curiosity_core_consumer] Cleanup complete: "
                       f"initial={initial_count}, removed_null_hash={null_hash_count}, "
                       f"removed_duplicates={duplicate_count}, final={final_count}")

        except Exception as e:
            logger.error(f"[curiosity_core_consumer] Error during cleanup: {e}", exc_info=True)

    def shutdown(self) -> None:
        """Shutdown daemon gracefully."""
        logger.info(f"[curiosity_core_consumer] Shutting down...")
        logger.info(f"[curiosity_core_consumer] Total gaps processed: {self.gap_count}")
        logger.info(f"[curiosity_core_consumer] Total questions generated: {self.question_count}")
        self.running = False
        if hasattr(self, 'chem_sub'):
            self.chem_sub.close()


def main():
    """Entry point for CuriosityCore consumer daemon."""
    daemon = CuriosityCoreConsumerDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
