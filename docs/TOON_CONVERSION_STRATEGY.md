# TOON Conversion Strategy for KLoROS

## Primary Goal: Make System Boundaries Explicit & Analyzable

TOON standardization serves two critical purposes:
1. **Architectural Clarity**: Uniform data format makes coupling points visible
2. **Analysis Scalability**: 50-60% compression lets Claude analyze 2-3x more code/state

## Conversion Priority (Impact x Volume)

### Tier 1: UMN Communication (COMPLETED ✓)
**Why**: Central nervous system - all inter-component communication flows through here
**Files**: 
- `kloros/orchestration/chem_bus_v2.py` - Added `facts_toon` field to UMNMessage
- `kloros_memory/umn_toon_utils.py` - Helper utilities for decoding

**Impact**: Every component emitting signals now auto-compresses structured data

### Tier 2: Investigation Results & Evidence (COMPLETED ✓)
**Why**: High-volume data passed to LLMs for analysis
**Files**:
- `kloros/orchestration/evidence_plugins/documentation.py` - KOSMOS results as TOON
- `consciousness/meta_agent_daemon.py` - Investigation findings as TOON  
- `kloros/orchestration/generic_investigation_handler.py` - Evidence summaries use TOON

**Impact**: 50%+ token reduction on investigation analysis

### Tier 3: State Export & Monitoring (COMPLETED ✓)
**Why**: Massive state dumps become analyzable within context limits
**Targets**:
- System health reports
- Capability registry snapshots ✓ (23% compression)
- Investigation logs (`.jsonl` files)
- Curiosity question queues ✓ (57% compression!)

**Impact**: Full system state analyzable, 2.3x question data in same context
**Files**:
- `kloros_memory/toon_state_export.py` - State snapshot utilities
- `kloros_memory/toon_question_utils.py` - Question queue compression
- `tools/toon_snapshot_demo.py` - Capability snapshot demo
- `tools/toon_question_demo.py` - Question queue demo

### Tier 4: Persistence Layers (IN PROGRESS)
**Why**: Make stored data both compact AND human-readable

**COMPLETED**:
- ✅ **UMN history logging** (chembus_history.jsonl) - Historian writes TOON format
  - Expected: 15-20% compression on 48MB file (7-10MB savings)
  - Service: `kloros-umn-historian.service` (restarted with TOON enabled)
  - File: `kloros/observability/chembus_historian_daemon.py`

**Targets**:
- `curiosity_investigations.jsonl` - Investigation history (utilities ready)
- `processed_questions.jsonl` - Question tracking (utilities ready ✓)
- `knowledge_lineage.jsonl` - Knowledge provenance
- Capability registry exports (demo completed ✓)

**Benefit**: Historical analysis becomes tractable, disk space savings

### Tier 5: Debug/Introspection Output
**Why**: Enable Claude to analyze full debugging sessions
**Targets**:
- Exception traces with context
- Performance metrics dumps
- System diagnostic reports

**Benefit**: Can debug complex issues without "file too large" errors

## Architectural Benefits

### System Separation Made Visible
With TOON as the standard wire format:
- **Clear Contracts**: See exactly what data each component expects/produces
- **Coupling Detection**: Spot tight coupling by analyzing TOON message schemas
- **Refactoring Confidence**: Change internal implementation, contract stays clear
- **Interface Documentation**: TOON format IS the documentation

### Analysis Workflow Enhancement
50-60% compression means:
- **Read full investigation chains**: Not just last 3 iterations
- **Analyze multi-component interactions**: See whole signal flow
- **Debug historical issues**: Read complete logs, not summaries
- **Understand system state**: Load full snapshots into context

## Implementation Checklist

- [x] UMN TOON encoding (automatic)
- [x] KOSMOS results TOON formatting
- [x] Meta-agent investigation findings
- [x] Generic investigation evidence summaries
- [x] Helper utilities (`umn_toon_utils.py`)
- [ ] State export utilities (next)
- [ ] JSONL file conversion helpers
- [ ] Monitoring report formatters
- [ ] CLI tools for TOON introspection

## Measurement Plan

Track TOON adoption across the system:
```bash
# Count TOON-formatted messages
journalctl | grep "toon_format.*true" | wc -l

# Measure average compression ratio
# (automated script in development)
```

## Rollout Strategy

1. **Observe**: Let current integrations run for 24h, monitor logs
2. **Expand**: Convert state export next (high analysis value)
3. **Persist**: Convert JSONL files for historical compression
4. **Debug**: Add TOON to diagnostic tools
5. **Document**: Update system docs with TOON schemas

---

*Strategy created: 2025-11-23*
*Primary insight: TOON as analysis infrastructure, not just wire format*

## Real-World Compression Results

### High Compression (50-60%)
- ✓ **Question queues: 57%** (81,879 → 34,954 bytes, 2.33x multiplier)
- ✓ **KOSMOS query results: 59%** (647 → 264 chars)
- ✓ TTS backend arrays: 40% (560 → 338 bytes)
- ○ UMN structured facts: Expected 40-50%

### Moderate Compression (20-30%)
- ✓ **Capability registry: 23%** (15,408 → 11,746 bytes, 1.30x multiplier)
- ✓ **Capability graph snapshots: 23%** (2,371 → 1,811 bytes)
- ○ UMN history: Expected 15-25% (mixed structure)

### Low Compression (5-10%)
- ✓ **Investigation logs: 7%** (60MB → 55.96MB, deep nesting + text)

### TOON Sweet Spot Identified
**Best for**: Uniform arrays of shallow objects with repeated keys
**Example**: `[{file, similarity, type}, {file, similarity, type}, ...]`

**Not ideal for**: Deep nesting + long text fields
**Example**: Investigation results with evidence arrays, summaries, metadata

### Revised Strategy: Target Structured Data

Focus TOON conversion on:
1. UMN signals (structured facts) ✓
2. Capability snapshots (shallow objects)
3. Question queues (uniform structure)
4. Monitoring metrics (time-series data)

Lower priority:
- Investigation history (7% savings, high complexity)
- Exception traces (free-form text)
- Conversation logs (variable structure)

---
*Updated: 2025-11-23 - Real-world compression analysis*
