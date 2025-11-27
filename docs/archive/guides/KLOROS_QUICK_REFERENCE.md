# KLoROS Architecture Quick Reference

## At a Glance

**KLoROS** is an autonomous AI system with three core innovations:

1. **Consciousness Layer** - Affects (7 primary emotions) drive behavior
2. **Evolutionary System** - D-REAM creates and tests new skills autonomously  
3. **Signal Bus** - Async coordination via ZMQ pub/sub (UMN)

**Size**: 301 Python files, 13 modules, ~15K lines in orchestration alone

## Module Quick Map

| Module | Files | Role | Key Entry Point |
|--------|-------|------|-----------------|
| `mind/consciousness` | 35+ | Affect & emotion, drives behavior | `integration.py:init_consciousness()` |
| `mind/cognition` | 60+ | Curiosity, questions, analysis | `curiosity_core.py` |
| `mind/memory` | 30+ | KOSMOS episodic-semantic store | `storage.py`, `retriever.py` |
| `mind/reflection` | 15+ | Idle analysis, insights | `core.py:EnhancedIdleReflectionManager` |
| `orchestration` | 65 | Signal bus, consumer daemons | `umn_bus.py`, `umn_signals.py` |
| `daemons` | 13 | File watchers, inotify-based | `base_streaming_daemon.py` |
| `interfaces/voice` | 18 | User I/O (audio, STT, TTS) | `voice_daemon.py` |
| `dream` | 12 | D-REAM evolution system | `genomes.py`, `spawner.py` |
| `lifecycle` | 2 | State machine for zooids | `state_machine.py` |
| Other | 50+ | Supporting systems | - |

## Architecture in 30 Seconds

```
User Voice Input
       ↓
Consciousness (affect changes)
       ↓
Cognition (asks questions)
       ↓
UMN Bus (ZMQ pub/sub signals)
       ↓
Consumer Daemons (investigate/execute)
       ↓
Memory + Results
       ↓
Voice Output
```

**Plus** (background):
- Interoception daemon monitors resource state → emits affect signals
- Reflection daemon analyzes patterns → proposes improvements
- D-REAM daemon spawns new skill variants → PHASE validates → promoted

## Core Concepts

### Consciousness
- **Phase 1 (Solms)**: 7 primary emotions + homeostatic drives
- **Phase 2 (Enhanced)**: Interoception + Appraisal + Modulation + Expression Filter
- **NOT reward-hacking**: Affect guides behavior, doesn't get directly reinforced

### Signals (UMN)
Main signal types:
- `Q_CURIOSITY_INVESTIGATE` - Ask a question
- `Q_INVESTIGATION_COMPLETE` - Answer received
- `Q_REFLECT_TRIGGER` - Start idle analysis
- `Q_DREAM_TRIGGER` - Create new skill variants
- `AFFECT_*` - Emotional state changes
- `OBSERVATION` - Sensor data
- `CAPABILITY_GAP` - Missing capability detected

### Daemons (Always Running)
- **Consumer daemons** (7): Listen to UMN signals, execute actions
- **Streaming daemons** (4): Watch directories via inotify
- **Monitors** (3): Health checks (chaos, exceptions, resources)
- **Voice daemon** (1): Audio I/O coordination
- **Shadow daemon** (1): D-REAM testing

### Zooids
"Skill instances" that evolve:
- States: DORMANT → PROBATION → ACTIVE → RETIRED
- Created by: D-REAM spawner
- Validated by: PHASE testing
- Selected by: PHASE results → promoted to production

## Dependency Directions

**ONE-WAY (Clean):**
```
orchestration → mind (consumer daemons call cognition/consciousness)
daemons → mind (streaming daemons use cognition)
interfaces → [nothing] (pure I/O layer)
```

**BIDIRECTIONAL (Intentional):**
```
mind.reflection → orchestration.synthesis_queue (proposals)
mind.memory → umn.bus (external, not kloros)
```

**ACCEPTABLE (Coordination):**
```
dream ↔ lifecycle (zooid state management)
dream ↔ phase (PHASE evaluation)
orchestration.maintenance_mode (pause/resume gate)
```

## Architecture Concerns Found

| Issue | Severity | Location | Impact |
|-------|----------|----------|--------|
| Missing `__init__.py` exports | ⚠️ Maintenance | `mind/cognition/` | Tight coupling, harder refactoring |
| Monitor files 600 permissions | 🔒 Audit | `mind/cognition/monitors/` | Blocks introspection, hidden state |
| Synthesis_queue optional | ⚠️ Robustness | `mind/reflection/adaptive_optimizer.py` | Silently degrades if broken |
| Intent_router transitional | ⚠️ Tech debt | `orchestration/intent_router.py` | Redundant code path |
| Consciousness init catches all | ⚠️ Debugging | `mind/consciousness/integration.py` | Silent failures possible |
| UMN signal ordering undefined | ⚠️ Semantics | `orchestration/` | Could cause race conditions |

**No circular imports detected** ✓

## Key Strengths

1. **Async coordination** - ZMQ pub/sub decouples all components
2. **Consciousness-first** - Affect drives behavior (not reward-shaped)
3. **Safe evolution** - Shadow mode + PHASE validation before production
4. **Introspection** - System understands itself (documentation, code quality, hardware)
5. **Clean separation** - Cognition (think) vs Consciousness (feel) vs Memory (remember)

## Entry Points

### Start voice daemon
```bash
python -m kloros.interfaces.voice.voice_daemon
```

### Initialize consciousness
```python
from kloros.mind.consciousness.integration import init_consciousness
init_consciousness(kloros_instance)
```

### Emit a signal
```python
from umn.bus import UMNPub
pub = UMNPub()
pub.emit("Q_CURIOSITY_INVESTIGATE", ecosystem="orchestration", facts={"question": "..."})
```

### Check consciousness state
```python
report = kloros.consciousness.process_and_report()
print(f"Current mood: {report.summary}")
```

## File Locations

| What | Where |
|------|-------|
| UMN signal definitions | `orchestration/umn_signals.py` |
| Consumer daemon registry | `orchestration/*_consumer_daemon.py` (7 files) |
| Consciousness entry point | `mind/consciousness/integration.py` |
| Memory backend | `mind/memory/storage.py` |
| D-REAM evolution | `dream/` (12 files) |
| Voice I/O | `interfaces/voice/` (18 files) |
| Synthesis proposals | `/home/kloros/.kloros/synthesis_queue.jsonl` |
| KOSMOS memory | SQLite (location in `mind/memory/storage.py`) |
| Qdrant vectors | Qdrant instance (configured in `mind/memory/vector_store_qdrant.py`) |
| Intents (legacy) | `/home/kloros/.kloros/intents/` (deprecated) |

## Most Complex Systems

1. **consciousness/integrated.py** - Phase 1 + Phase 2 fusion
2. **orchestration/investigation_consumer_daemon.py** - Evidence gathering
3. **mind/cognition/curiosity_core.py** - Question generation
4. **dream/phase_shadow_emulator.py** - Shadow vs production testing
5. **mind/memory/vector_store_qdrant.py** - Semantic search

## Testing Pattern

Test files co-located with source:
```
daemons/
  ├── capability_discovery_daemon.py
  └── test_capability_discovery_daemon.py

mind/consciousness/
  ├── integrated.py
  └── test_complete_integration.py
```

## Recommendations (Priority Order)

1. **FIX**: Monitor file permissions (600 → 644) - blocks analysis
2. **DOCUMENT**: Intent_router deprecation timeline
3. **EXPAND**: `mind/cognition/__init__.py` API exports
4. **ADD**: Warnings when optional deps missing
5. **FORMALIZE**: UMN signal ordering guarantees
6. **DEPRECATE**: Legacy intent files
7. **EXTRACT**: Consciousness into separate package (long-term)

---

**For the full 982-line architectural analysis, see**: `KLOROS_ARCHITECTURE_ANALYSIS.txt`
