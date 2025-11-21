# Self-Study → Memory Integration Design

**Date:** 2025-11-21
**Status:** Approved
**Phase:** Self-Mastery Phase 1

## Overview

Bridges component_self_study (knowledge.db) and episodic memory (memory.db + Qdrant), enabling KLoROS to actively recall component knowledge.

## Architecture

**Pattern:** Event-driven with autonomous error recovery

**Components:**
1. component_self_study.py (modified) - Emits LEARNING_COMPLETED via ChemBus
2. klr-study-memory-bridge (new daemon) - Subscribes to learning signals, logs to memory
3. ServiceHealthCorrelator (existing) - Integrates into introspection daemon
4. Dead Letter Queue - SQLite table in memory.db stores failed events

**Signal Flow:**
```
component_self_study → ChemBus(LEARNING_COMPLETED) → bridge daemon → MemoryLogger → memory.db + Qdrant
                                                           ↓ (on failure)
                                                   Dead Letter Queue → Investigation triggered
```

## Key Design Decisions

- **Immediate logging** provides real-time recall
- **Progressive detail** balances richness against noise
- **Event bus** maintains clean separation
- **Autonomous error recovery** never blocks the pipeline

## Signal Structure

**ChemBus Signal Format:**
```python
signal = "LEARNING_COMPLETED"
ecosystem = "introspection"
intensity = 1.0 + (study_depth * 0.5)
facts = {
    "source": "component_study",
    "component_id": "module:component_self_study.py",
    "study_depth": 2,
    "component_type": "module",
    "file_path": "/home/kloros/src/component_self_study.py",
    "studied_at": 1732188000.0,
    # ... additional fields based on depth
}
```

**Extensibility:** Future learning sources (Google Drive, documentation) use the same signal; the source field differentiates them.

## Tiered Detail Logic

**Depth 0-1 (Shallow scan):**
- Fields: component_id, component_type, file_path, studied_at
- Memory: "Scanned component X (type: Y)"

**Depth 2 (Standard study):**
- Fields: Above + purpose, key capabilities
- Memory: "Studied component X: <purpose>. Capabilities: <top 3>"

**Depth 3 (Deep analysis):**
- Fields: Above + dependencies, config_params, examples, findings, improvements
- Memory: "Analyzed component X: <comprehensive summary with findings and improvements>"

## Bridge Daemon Implementation

**Service Name:** klr-study-memory-bridge

**Responsibilities:**
1. Subscribe to LEARNING_COMPLETED signals on ChemBus
2. Transform study data into tiered memory events based on depth
3. Log events via MemoryLogger (generates episodic events + Qdrant embeddings)
4. Handle failures with dead letter queue + investigation trigger

**Structure:**
```python
class StudyMemoryBridge:
    def __init__(self):
        self.memory_logger = MemoryLogger()
        self.subscriber = ChemSub(
            topic="LEARNING_COMPLETED",
            on_json=self._on_learning_completed
        )
        self.dead_letter = DeadLetterQueue(db_path="/home/kloros/.kloros/memory.db")

    def _on_learning_completed(self, signal_data):
        try:
            memory_content = self._format_by_depth(signal_data)
            self.memory_logger.log_event(
                event_type=EventType.DOCUMENTATION_LEARNED,
                content=memory_content,
                metadata=signal_data
            )
        except Exception as e:
            self.dead_letter.store(signal_data, error=str(e))
            self._trigger_investigation(error=e, context=signal_data)
```

## Dead Letter Queue Schema

```sql
CREATE TABLE failed_study_events (
    id INTEGER PRIMARY KEY,
    signal_data TEXT NOT NULL,  -- JSON
    error_message TEXT,
    failed_at REAL,
    retry_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending'  -- pending, investigating, resolved
);
```

**Investigation Trigger:** Emits CAPABILITY_GAP_FOUND with memory system failure details.

## Modifications to Existing Systems

**component_self_study.py:**
- Initialize ChemPub
- Emit LEARNING_COMPLETED after storing each study
- Include all study fields in signal payload

**introspection_daemon.py:**
- Import ServiceHealthCorrelator
- Add as 6th scanner

## Verification Strategy

**Health Check:**
- Start klr-study-memory-bridge
- Verify systemd status and ChemBus subscription
- Confirm MemoryLogger initialized

**End-to-End Flow:**
- Trigger component self-study
- Verify LEARNING_COMPLETED in ChemBus logs
- Query memory.db for DOCUMENTATION_LEARNED events
- Verify Qdrant kloros_knowledge collection grows

**Tiered Detail:**
- Compare depth 1, 2, and 3 memory events
- Confirm content matches expected detail

**Error Handling:**
- Simulate memory system failure
- Verify failed events queue correctly
- Confirm investigation signal emits
- Verify replay mechanism works after recovery

**ServiceHealthCorrelator:**
- Verify scanner initializes in introspection daemon logs
- Check findings appear in /home/kloros/.kloros/scanner_findings/

**24-Hour Observation:**
- Monitor episodic memory growth
- Verify Qdrant vector accumulation
- Check reflection logs show component knowledge recall
- Confirm dead letter queue stays empty

## Success Criteria

- Component studies generate immediate memory events
- Memory events contain appropriate detail for depth
- Failed events queue and trigger investigation
- ServiceHealthCorrelator detects cascading failures
- KLoROS recalls component knowledge during reflection and conversation
