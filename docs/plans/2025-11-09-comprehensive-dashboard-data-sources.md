# Comprehensive Dashboard - Data Source Discovery

**Created:** 2025-11-09
**Purpose:** Map all available monitoring data for dashboard design
**Status:** Discovery Complete - Ready for Brainstorming

## Data Sources Identified

### 1. D-REAM Evolution & Tournament System

**Location:** `/home/kloros/.kloros/intents/curiosity_*.json`

**Available Data:**
- Tournament results with 8 candidates per experiment
- Fitness scores (currently showing 0.0 due to bug fix in progress)
- SPICA variant performance metrics:
  - `exact_match_mean` - Answer accuracy (0.0 - 1.0)
  - `latency_p50_ms` / `latency_p95_ms` - Response times
  - `memory_peak_mb` - Peak memory usage
  - `cpu_percent` - CPU utilization
  - `query_count` - Total queries processed
- Champion selection and strategy parameters
- Search space configuration
- Experiment status (complete/running/failed)
- Instance IDs (e.g., spica-b8c0cea8, spica-a3d8f398...)
- PHASE test results (passed/failed/total)

**Example Structure:**
```json
{
  "experiment_result": {
    "mode": "tournament",
    "status": "complete",
    "champion": {"name": "conservative", "temperature": 0.3},
    "champion_fitness": 0.0,
    "total_candidates": 8,
    "artifacts": {
      "tournament": {
        "instances": ["spica-b8c0cea8", ...],
        "total_replicas": 64,
        "results": {
          "passed": 64,
          "failed": 0,
          "results": [...]
        }
      }
    }
  }
}
```

---

### 2. Curiosity System

**Location:** `/home/kloros/.kloros/intents/`

**Available Data:**
- Active curiosity questions
- Question metadata:
  - `question_id` - Unique identifier
  - `question` - Human-readable question text
  - `hypothesis` - What KLoROS is investigating
  - `value_estimate` - Expected benefit (0.0 - 1.0)
  - `cost_estimate` - Expected effort (0.0 - 1.0)
  - `action_class` - investigate/integrate/discover
  - `capability_key` - What capability this relates to
- Evidence supporting the question
- Dream experiment configuration
- Processing workflow status

**Processing Status Categories:**
- `applied/` - Successfully integrated fixes
- `spawned/` - Tournaments currently running
- `deduplicated/` - Duplicate questions filtered
- `error/` - Processing errors
- `failed/` - Failed experiments
- `incomplete/` - Partial results
- `llm_generation_failed/` - LLM failures
- `queue_overflow/` - Queue capacity issues
- `spawn_error_RuntimeError/` - Runtime errors during spawn
- `tests_failed/` - PHASE tests failed
- `unknown/` - Unclassified status

**Intent Count:** Hundreds of processed intents with full history

---

### 3. Integration Issues & Concerns

**Location:** `/home/kloros/.kloros/integration_issues/`

**Available Data:**
- 50+ orphaned queue detections
- Missing wiring issues
- Duplicate responsibility warnings
- Dead code identification
- Per-issue structure:
  - Channel name (e.g., `fitness_history`)
  - Producer file path
  - Evidence list
  - Problem description
  - Recommendations
  - Status (pending/reviewing/resolved)
  - Generation timestamp

**Issue Types:**
- Orphaned queues (data structures that fill but never drain)
- Missing wiring (calls to non-existent components)
- Duplicate responsibilities (multiple components doing same thing)
- Initialization gaps (components used but never initialized)

---

### 4. Reasoning Traces

**Location:** `/home/kloros/.kloros/reasoning_traces/`

**Available Data:**
- Trace ID
- User query
- Processing steps:
  - `query_received` - Initial query
  - `context_retrieval` - RAG context loading
  - `llm_generation` - Response generation
- Step timestamps and durations
- Final response
- Total duration
- Success/error status
- Error messages (e.g., matrix dimension mismatches)

**Trace Count:** Hundreds of traces with full reasoning history

---

### 5. Shadow Deployment Validation

**Location:** `/home/kloros/.kloros/metrics/shadow_*.json`

**Available Data:**
- Niche name (maintenance_housekeeping, observability_logging)
- Start time and elapsed hours
- Target hours (24h validation period)
- Execution counts:
  - `total_executions`
  - `successful_executions`
  - `failed_executions`
- Drift metrics:
  - `max_drift_percentage`
  - `avg_drift_percentage`
  - `current_drift_percentage`
- Error counts:
  - `legacy_error_count`
  - `wrapper_error_count`
- Status flags:
  - `rollback_triggered` (boolean)
  - `promotion_eligible` (boolean)
- Last updated timestamp

**Current Status:** 23h/24h complete, 0.0% drift, ready for promotion

---

### 6. System Health & Resource Monitoring

**Location:** `/home/kloros/.kloros/metrics/`

**Available Data:**
- Memory metrics (`kloros_observer_memory.json`):
  - RSS (Resident Set Size) in MB
  - VMS (Virtual Memory Size) in MB
  - Percent of total system memory
  - Baseline memory
  - Growth from baseline
  - Timestamp
  - Status (ok/warning/critical)
  - Action taken (if any)
- Niche health (`niche_health.json`)
- Service status from systemctl
- Process resource usage from ps

**Services Monitored:**
- kloros.service (main voice assistant)
- dream.service (evolutionary runner)
- kloros-observer.service (event collection)
- kloros-orchestrator.service (coordination)
- klr-phase-consumer.service (test consumer)
- Various timers and one-shot services

---

### 7. Active SPICA Instances

**Location:** `/home/kloros/experiments/spica/instances/`

**Available Data:**
- 13 active SPICA variant directories
- Instance IDs (spica-{hash})
- Per-instance performance data
- Isolation configuration
- CPU affinity settings
- Network egress controls
- Lineage immutability status

---

### 8. Logs

**Location:** `/home/kloros/.kloros/logs/`

**Available Data:**
- Daily JSONL logs (kloros-YYYYMMDD.jsonl)
- Service-specific logs
- Shadow daemon stdout/stderr
- Monitor logs
- Rotation history back to September 2025

---

## Data Not Yet Located

Need to explore further:
- [ ] D-REAM experiment history (beyond curiosity intents)
- [ ] PHASE test suite definitions
- [ ] KLoROS decision logs (if separate from reasoning traces)
- [ ] Performance baselines and trends
- [ ] Alert history and escalations
- [ ] Configuration change history

---

## Dashboard Design Questions

When you return, we'll discuss:

1. **Priority Categories** - Which data is most important to see at a glance?
2. **Refresh Rates** - What needs real-time updates vs periodic?
3. **Alert Thresholds** - When should dashboard highlight issues?
4. **Historical Depth** - How much history to show (1h, 24h, 7d)?
5. **Visualization Style** - Terminal UI, web UI, both?
6. **Drill-Down Paths** - How to explore from summary to detail?
7. **Actionability** - Can dashboard trigger actions or just observe?

---

## Technical Implementation Notes

**Data Formats:**
- JSON for metrics and structured data
- Markdown for issues and concerns
- JSONL for logs
- No centralized database - file-based storage

**Update Patterns:**
- Shadow metrics: Updated continuously during validation
- Curiosity intents: Created on question generation
- Reasoning traces: One per query
- Integration issues: Scanned periodically by orchestrator
- System health: Polled every N seconds

**Access Patterns:**
- All data readable by user `kloros`
- Most data in `/home/kloros/.kloros/`
- Some experiment data in `/home/kloros/experiments/`
- Logs rotated daily, compressed after N days
