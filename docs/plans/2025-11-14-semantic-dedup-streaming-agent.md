# Semantic Deduplication Streaming Agent Implementation Plan

**Goal**: Refactor semantic deduplication from batch processing (every 60s) to event-driven streaming via chemical bus.

**Problem**:
- Current system reprocesses ALL 1,717 investigations every 60 seconds
- GPU semantic deduplication runs 1,717 times per batch
- Logs spam with individual "Updated evidence" messages
- Inefficient: 30-minute processing time reduced to 3.7s with incremental tracking, but still processes all investigations

**Solution**:
- Create dedicated semantic dedup consumer daemon
- Event-driven: Process investigations as they complete
- Batch GPU processing: Accumulate 10 investigations or 30s timeout
- Clean aggregate logging: One summary per batch
- Real-time: No waiting for orchestrator tick

---

## Architecture

### Current Flow (Batch)
```
Investigation Consumer → Write to JSONL
↓ (wait up to 60s)
Orchestrator Tick → capability_integrator.process_investigations()
  → Load ALL 1,717 investigations
  → Filter already processed (1,717 - N new)
  → For each NEW investigation:
    → semantic_store.update_from_investigation() (GPU)
    → Log "Updated evidence for modules: X"
  → Mark as processed
```

### New Flow (Event-Driven Streaming)
```
Investigation Consumer → Write to JSONL → Emit Q_INVESTIGATION_COMPLETE(investigation_id)
↓ (immediate)
Semantic Dedup Consumer (daemon):
  - Subscribe to Q_INVESTIGATION_COMPLETE
  - Accumulate investigations in buffer
  - When buffer reaches 10 items OR 30s timeout:
    → Batch GPU processing (1 embedding pass for all 10)
    → Update semantic evidence
    → Mark all 10 as processed
    → Log: "Processed 10 investigations, updated evidence for 3 modules"
↓
Capability Integrator (in orchestrator):
  - Skip semantic processing (already done)
  - Only handle capability registry integration
```

---

## Implementation Tasks

### Task 1: Add Signal Mapping
**File**: `/home/kloros/src/kloros/orchestration/signal_router_v2.py`

Add to `INTENT_TO_SIGNAL` dict (around line 14):
```python
"investigation_complete": ("Q_INVESTIGATION_COMPLETE", "introspection"),
```

**Verification**:
- Signal can be routed via `SignalRouter.route_intent("investigation_complete", ...)`

---

### Task 2: Emit Signal from Investigation Consumer
**File**: `/home/kloros/src/kloros/orchestration/investigation_consumer_daemon.py`

**Location**: After writing investigation to JSONL (around line 140-147)

**Add**:
```python
from .chem_bus_v2 import ChemPub

# In __init__:
self.chem_pub = ChemPub()

# After writing to JSONL (line 147):
try:
    self.chem_pub.emit(
        signal="Q_INVESTIGATION_COMPLETE",
        ecosystem="introspection",
        intensity=1.0,
        facts={
            "investigation_timestamp": investigation.get("timestamp"),
            "module_name": investigation.get("module_name"),
            "question_id": question_id,
            "status": investigation.get("status")
        }
    )
    logger.debug(f"[investigation_consumer] Emitted Q_INVESTIGATION_COMPLETE for {question_id}")
except Exception as e:
    logger.warning(f"[investigation_consumer] Failed to emit signal: {e}")
```

**Verification**:
- Check logs for "Emitted Q_INVESTIGATION_COMPLETE"
- Use `sudo journalctl -u klr-investigation-consumer -f | grep "Emitted Q_INVESTIGATION_COMPLETE"`

---

### Task 3: Create Semantic Dedup Consumer Daemon
**File**: `/home/kloros/src/kloros/orchestration/semantic_dedup_consumer_daemon.py`

**Full Implementation**:
```python
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

            # Load full investigation
            investigation = self._load_investigation(timestamp)
            if not investigation:
                logger.warning(f"[semantic_dedup] Could not load investigation {timestamp}")
                continue

            if investigation.get("status") != "completed":
                continue

            # Update semantic evidence (GPU operation batched by sentence-transformers)
            try:
                modules = self.semantic_store.update_from_investigation(investigation)
                updated_modules.update(modules)

                # Mark as processed
                module_name = investigation.get("module_name", "unknown")
                self._mark_processed(timestamp, module_name)
                processed_count += 1

            except Exception as e:
                logger.error(f"[semantic_dedup] Failed to process {timestamp}: {e}", exc_info=True)

        batch_duration = time.time() - batch_start

        # Aggregate logging
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

    def handle_signal(self, topic: str, payload: bytes):
        """Handle Q_INVESTIGATION_COMPLETE signal."""
        try:
            msg = json.loads(payload.decode('utf-8'))
            facts = msg.get('facts', {})

            investigation_timestamp = facts.get('investigation_timestamp')
            status = facts.get('status')

            if not investigation_timestamp:
                logger.warning("[semantic_dedup] Received signal without investigation_timestamp")
                return

            # Skip if already processed
            if investigation_timestamp in self.processed_ids:
                logger.debug(f"[semantic_dedup] Already processed {investigation_timestamp}, skipping")
                return

            # Only process completed investigations
            if status != "completed":
                logger.debug(f"[semantic_dedup] Investigation {investigation_timestamp} not completed, skipping")
                return

            # Add to pending batch
            self.pending_investigations.append(investigation_timestamp)
            logger.debug(f"[semantic_dedup] Added {investigation_timestamp} to batch ({len(self.pending_investigations)}/{BATCH_SIZE})")

            # Process batch if threshold reached
            if self._should_process_batch():
                self._process_batch()

        except Exception as e:
            logger.error(f"[semantic_dedup] Error handling signal: {e}", exc_info=True)

    def run(self):
        """Run the consumer daemon."""
        logger.info("[semantic_dedup] Starting semantic dedup consumer")
        logger.info(f"[semantic_dedup] Batch config: size={BATCH_SIZE}, timeout={BATCH_TIMEOUT_SECONDS}s")

        # Subscribe to investigation completion signals
        subscriber = ChemSub(
            topic="Q_INVESTIGATION_COMPLETE",
            on_message=self.handle_signal
        )

        logger.info("[semantic_dedup] Subscribed to Q_INVESTIGATION_COMPLETE")

        # Main loop with periodic batch processing
        try:
            while self.running:
                time.sleep(5)  # Wake up every 5s to check timeout

                if self._should_process_batch():
                    self._process_batch()

        except KeyboardInterrupt:
            logger.info("[semantic_dedup] Received shutdown signal")
        finally:
            # Process any remaining pending investigations
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

    # Handle shutdown gracefully
    def shutdown_handler(signum, frame):
        logger.info("[semantic_dedup] Received signal, shutting down")
        consumer.running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    consumer.run()


if __name__ == "__main__":
    main()
```

**Verification**:
- Run standalone: `python3 /home/kloros/src/kloros/orchestration/semantic_dedup_consumer_daemon.py`
- Check it subscribes without errors
- Verify batching logic with test signals

---

### Task 4: Remove Semantic Processing from Capability Integrator
**File**: `/home/kloros/src/kloros/orchestration/capability_integrator.py`

**Remove** lines 362-385 (semantic evidence enrichment loop):
```python
# SEMANTIC EVIDENCE ENRICHMENT: Update evidence for all completed investigations
# This triggers the recursive learning loop
all_updated_modules: Set[str] = set()
new_investigations = 0
for investigation in investigations:
    # Skip already semantically processed investigations
    timestamp = investigation.get("timestamp", "")
    if timestamp in self.semantic_processed_ids:
        continue

    if investigation.get("status") == "completed":
        new_investigations += 1
        try:
            updated_modules = self.semantic_store.update_from_investigation(investigation)
            all_updated_modules.update(updated_modules)
            self._mark_semantic_processed(investigation)
        except Exception as e:
            logger.warning(f"[integrator] Failed to enrich semantic evidence: {e}", exc_info=True)

already_processed = len(investigations) - new_investigations
logger.info(f"[integrator] Semantic processing: {new_investigations} new, {already_processed} already processed (skipped)")

if all_updated_modules:
    logger.info(f"[integrator] Semantic evidence updated for {len(all_updated_modules)} modules: {', '.join(list(all_updated_modules)[:5])}")
```

**Replace with**:
```python
# NOTE: Semantic evidence processing now handled by semantic_dedup_consumer_daemon
# This reduces orchestrator overhead and enables real-time event-driven processing
logger.debug(f"[integrator] Processing {len(investigations)} investigations (semantic dedup handled by daemon)")
```

**Verification**:
- Orchestrator logs no longer show "Semantic processing: X new, Y already processed"
- Capability integration still works (only adds to capabilities.yaml)

---

### Task 5: Create Systemd Service
**File**: `/etc/systemd/system/klr-semantic-dedup.service`

```ini
[Unit]
Description=KLoROS Semantic Deduplication Consumer
After=network.target klr-chem-proxy.service
Wants=klr-chem-proxy.service

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros
ExecStart=/home/kloros/.venv/bin/python3 /home/kloros/src/kloros/orchestration/semantic_dedup_consumer_daemon.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=klr-semantic-dedup

# Resource limits
MemoryMax=8G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
```

**Environment Drop-in**: `/etc/systemd/system/klr-semantic-dedup.service.d/env.conf`
```ini
[Service]
EnvironmentFile=/home/kloros/.kloros_env
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="PYTHONPATH=/home/kloros/src"
```

**Commands**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable klr-semantic-dedup.service
sudo systemctl start klr-semantic-dedup.service
sudo systemctl status klr-semantic-dedup.service
```

**Verification**:
- `sudo systemctl status klr-semantic-dedup` shows active (running)
- `sudo journalctl -u klr-semantic-dedup -f` shows subscription confirmation

---

### Task 6: Verification & Testing

**Test 1: Signal Flow**
```bash
# Watch for investigation completion signals
sudo journalctl -u klr-investigation-consumer -f | grep "Emitted Q_INVESTIGATION_COMPLETE"

# Watch for batch processing
sudo journalctl -u klr-semantic-dedup -f | grep "Batch complete"
```

**Test 2: Log Cleanliness**
```bash
# Should see NO spam (batch summaries only)
sudo journalctl -u klr-semantic-dedup --since "5 minutes ago" --no-pager | grep "Updated evidence"

# Should see clean aggregate logs
sudo journalctl -u klr-semantic-dedup --since "5 minutes ago" --no-pager | grep "Batch complete"
```

**Test 3: Performance**
- Batch of 10 investigations should complete in <5 seconds (GPU batch efficiency)
- No more 30-minute processing times
- Real-time: Investigations processed within 30 seconds of completion

**Test 4: Integration**
```bash
# Trigger new module discovery to generate investigation
# Verify it gets processed by semantic dedup daemon
# Verify orchestrator can still integrate it without semantic processing
sudo journalctl -u kloros-orchestrator -f | grep "integrator"
```

---

## Success Criteria

✅ **Event-Driven**: Investigations processed within 30s of completion (not waiting for orchestrator tick)
✅ **No Reprocessing**: Each investigation processed exactly once
✅ **Efficient GPU**: Batch processing reduces GPU overhead 10x
✅ **Clean Logs**: No more "Updated evidence" spam, only aggregate summaries
✅ **Scalable**: Can handle high investigation throughput via batching
✅ **Maintainable**: Clear separation of concerns (investigation → dedup → integration)

---

## Rollback Plan

If issues occur, disable the new system:

```bash
# Stop semantic dedup daemon
sudo systemctl stop klr-semantic-dedup.service
sudo systemctl disable klr-semantic-dedup.service

# Revert capability_integrator.py changes (restore semantic processing)
git checkout src/kloros/orchestration/capability_integrator.py

# System returns to batch processing mode
```

---

## Future Enhancements

1. **Emit Q_EVIDENCE_UPDATED** signal after batch processing for downstream consumers
2. **Add metrics**: Track batch sizes, processing times, GPU utilization
3. **Dynamic batching**: Adjust batch size based on investigation rate
4. **Parallel processing**: Multiple dedup workers for high throughput
5. **Compression**: Archive old processed investigations to reduce JSONL size
