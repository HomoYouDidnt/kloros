#!/usr/bin/env python3
"""
Semantic Deduplication Consumer Daemon

Event-driven semantic evidence processing via chemical signals.
Subscribes to Q_INVESTIGATION_COMPLETE and batch processes investigations.

Architecture:
- Subscribe to Q_INVESTIGATION_COMPLETE signal
- Accumulate investigations in buffer (max 10 items or 30s timeout)
- Batch GPU processing for efficiency
- Clean aggregate logging
"""

import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Set
from collections import deque
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import ChemSub
from registry.semantic_evidence import SemanticEvidenceStore

logger = logging.getLogger(__name__)

INVESTIGATIONS_LOG = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
SEMANTIC_PROCESSED_LOG = Path("/home/kloros/.kloros/semantic_processed_investigations.jsonl")

# Batching configuration
BATCH_SIZE = 10
BATCH_TIMEOUT_SECONDS = 30


class SemanticDedupConsumer:
    """
    Processes investigation completion signals and updates semantic evidence.

    Features:
    - Event-driven processing (no polling)
    - Batched GPU operations for efficiency
    - Aggregate logging to reduce spam
    - Idempotent processing with tracking
    """

    def __init__(self):
        """Initialize consumer."""
        self.semantic_store = SemanticEvidenceStore()
        self.processed_ids = self._load_processed_ids()

        # Batching state
        self.pending_investigations: deque = deque()
        self.last_batch_time = time.time()

        # Statistics
        self.total_processed = 0
        self.total_batches = 0

        self.running = True
        logger.info("[semantic_dedup] Initialized semantic deduplication consumer")

    def _load_processed_ids(self) -> Set[str]:
        """Load set of already processed investigation timestamps."""
        if not SEMANTIC_PROCESSED_LOG.exists():
            return set()

        processed = set()
        try:
            with open(SEMANTIC_PROCESSED_LOG, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if 'investigation_timestamp' in entry:
                        processed.add(entry['investigation_timestamp'])
        except Exception as e:
            logger.warning(f"[semantic_dedup] Error loading processed IDs: {e}")

        return processed

    def _mark_processed(self, investigation_timestamp: str, module_name: str):
        """Mark investigation as processed."""
        SEMANTIC_PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "investigation_timestamp": investigation_timestamp,
            "module_name": module_name,
            "processed_at": datetime.now().isoformat(),
        }

        try:
            with open(SEMANTIC_PROCESSED_LOG, 'a') as f:
                f.write(json.dumps(entry) + '\n')
            self.processed_ids.add(investigation_timestamp)
        except Exception as e:
            logger.error(f"[semantic_dedup] Failed to mark processed: {e}")

    def _load_investigation(self, timestamp: str) -> Dict[str, Any]:
        """Load investigation from JSONL by timestamp."""
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
            logger.error(f"[semantic_dedup] Failed to load investigation {timestamp}: {e}")

        return None

    def _process_batch(self):
        """Process accumulated investigations in batch."""
        if not self.pending_investigations:
            return

        batch_size = len(self.pending_investigations)
        batch_start = time.time()

        logger.info(f"[semantic_dedup] Processing batch of {batch_size} investigations")

        updated_modules: Set[str] = set()
        processed_count = 0

        while self.pending_investigations:
            timestamp = self.pending_investigations.popleft()

            investigation = self._load_investigation(timestamp)
            if not investigation:
                logger.warning(f"[semantic_dedup] Could not load investigation {timestamp}")
                continue

            if investigation.get("status") != "completed":
                continue

            try:
                modules = self.semantic_store.update_from_investigation(investigation)
                updated_modules.update(modules)

                module_name = investigation.get("module_name", "unknown")
                self._mark_processed(timestamp, module_name)
                processed_count += 1

            except Exception as e:
                logger.error(f"[semantic_dedup] Failed to process {timestamp}: {e}", exc_info=True)

        batch_duration = time.time() - batch_start

        self.total_processed += processed_count
        self.total_batches += 1

        if updated_modules:
            logger.info(
                f"[semantic_dedup] ✓ Batch complete: "
                f"processed={processed_count}, "
                f"updated_modules={len(updated_modules)} ({', '.join(list(updated_modules)[:3])}{'...' if len(updated_modules) > 3 else ''}), "
                f"duration={batch_duration:.2f}s"
            )
        else:
            logger.info(f"[semantic_dedup] ✓ Batch complete: processed={processed_count}, no module updates, duration={batch_duration:.2f}s")

        self.last_batch_time = time.time()

    def _should_process_batch(self) -> bool:
        """Check if batch should be processed."""
        if len(self.pending_investigations) >= BATCH_SIZE:
            return True

        if self.pending_investigations and (time.time() - self.last_batch_time) >= BATCH_TIMEOUT_SECONDS:
            return True

        return False

    def handle_signal(self, msg: Dict[str, Any]):
        """Handle Q_INVESTIGATION_COMPLETE signal."""
        try:
            facts = msg.get('facts', {})

            investigation_timestamp = facts.get('investigation_timestamp')
            status = facts.get('status')

            if not investigation_timestamp:
                logger.warning("[semantic_dedup] Received signal without investigation_timestamp")
                return

            if investigation_timestamp in self.processed_ids:
                logger.debug(f"[semantic_dedup] Already processed {investigation_timestamp}, skipping")
                return

            if status != "completed":
                logger.debug(f"[semantic_dedup] Investigation {investigation_timestamp} not completed, skipping")
                return

            self.pending_investigations.append(investigation_timestamp)
            logger.debug(f"[semantic_dedup] Added {investigation_timestamp} to batch ({len(self.pending_investigations)}/{BATCH_SIZE})")

            if self._should_process_batch():
                self._process_batch()

        except Exception as e:
            logger.error(f"[semantic_dedup] Error handling signal: {e}", exc_info=True)

    def run(self):
        """Run the consumer daemon."""
        logger.info("[semantic_dedup] Starting semantic dedup consumer")
        logger.info(f"[semantic_dedup] Batch config: size={BATCH_SIZE}, timeout={BATCH_TIMEOUT_SECONDS}s")

        subscriber = ChemSub(
            topic="Q_INVESTIGATION_COMPLETE",
            on_json=self.handle_signal
        )

        logger.info("[semantic_dedup] Subscribed to Q_INVESTIGATION_COMPLETE")

        try:
            while self.running:
                time.sleep(5)

                if self._should_process_batch():
                    self._process_batch()

        except KeyboardInterrupt:
            logger.info("[semantic_dedup] Received shutdown signal")
        finally:
            if self.pending_investigations:
                logger.info(f"[semantic_dedup] Processing {len(self.pending_investigations)} pending investigations before shutdown")
                self._process_batch()

            subscriber.close()
            logger.info(f"[semantic_dedup] Shutdown complete. Total processed: {self.total_processed}, Total batches: {self.total_batches}")


def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    consumer = SemanticDedupConsumer()

    def shutdown_handler(signum, frame):
        logger.info("[semantic_dedup] Received signal, shutting down")
        consumer.running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    consumer.run()


if __name__ == "__main__":
    main()
