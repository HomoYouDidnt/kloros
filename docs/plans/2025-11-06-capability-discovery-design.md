# Capability Discovery System - Enhanced Curiosity Acuity

**Status**: Design Approved
**Created**: 2025-11-06
**Purpose**: Enable KLoROS to detect missing tools, skills, and patterns as rigorously as she detects failures and degradation

## Problem Statement

KLoROS's curiosity system currently excels at detecting what's *broken* (failures, degradation, resource pressure) but lacks awareness of what's *missing* (tools, skills, patterns she doesn't have but could benefit from).

**Current Gap**:
- 8 monitors detect capability degradation
- 0 monitors detect capability absence
- No mechanism to discover external tools (ripgrep, MLflow, etc.)
- No awareness of upstream Claude Code skills
- No detection of architectural patterns used in successful codebases

**Desired State**:
KLoROS proactively discovers missing capabilities through reactive detection (encountering problems) and proactive scanning (comparing against external references). Meta-cognitive awareness prevents scanner proliferation.

## Architecture Overview

**Core Philosophy**: Detect absence as rigorously as failure. A meta-monitor prevents unchecked growth by proposing consolidation when scanners overlap.

### Three-Layer Architecture

**1. Scanner Layer** - Pluggable capability detectors
- `PyPIScanner` - Compares installed vs available packages
- `SkillMarketplaceScanner` - Checks Claude Code skills
- `PatternLibraryScanner` - Analyzes architectural patterns
- `ReactiveGapScanner` - Captures problems that reveal missing capabilities
- Add future scanners dynamically (zooid pattern)

**2. Orchestration Layer** - `CapabilityDiscoveryMonitor`
- Discovers and registers scanners automatically
- Schedules proactive scans during idle time
- Receives reactive gap reports in real-time
- Applies hybrid prioritization (frequency + VOI + alignment + cost)
- Generates `CuriosityQuestion` objects with `action_class=FIND_SUBSTITUTE`

**3. Meta-Cognition Layer** - `MonitorHealthMonitor`
- Tracks scanner effectiveness (questions generated, improvements made, resource cost)
- Detects redundancy (scanners generating similar questions)
- Proposes consolidation when patterns emerge
- Generates meta-questions about monitoring efficiency

## Data Flow

### Reactive Flow (Problem → Gap Detection)

```
1. KLoROS encounters problem (e.g., slow log search)
2. ReactiveGapScanner captures context (operation, bottleneck, failure mode)
3. Analyzer determines missing capability (e.g., "ripgrep for faster grep")
4. CapabilityDiscoveryMonitor creates CuriosityQuestion
5. Question enters curiosity_feed.json with prioritization score
6. ProcessedQuestionFilter applies cooldown (prevents re-asking too soon)
7. Orchestrator spawns D-REAM experiment to investigate
```

### Proactive Flow (Idle Scan → Discovery)

```
1. CapabilityDiscoveryMonitor detects idle time (low orchestrator activity)
2. Schedules scanner based on priority (high-value scanners run more often)
3. Scanner compares KLoROS state vs external reference
   - PyPIScanner: installed packages vs popular ML/devops packages
   - SkillMarketplaceScanner: installed skills vs upstream marketplace
   - PatternLibraryScanner: code patterns used vs industry patterns
4. Scanner returns list of gaps with metadata (value estimate, domain)
5. Hybrid prioritizer scores each gap
6. Top N gaps become CuriosityQuestions
7. Same path as reactive flow
```

### Meta-Cognition Flow (Scanner Health → Consolidation)

```
1. MonitorHealthMonitor tracks scanner metrics (runs every 7 days)
2. Analyzes overlap: "PyPIScanner and PatternLibraryScanner both suggest pytest plugins"
3. Calculates value/cost ratio per scanner
4. Generates meta-questions:
   - "Should PyPIScanner and PatternLibraryScanner merge their pytest detection?"
   - "Scanner X generated 47 questions but 0 led to improvements - deprecate?"
5. Meta-questions enter feed with action_class=PROPOSE_FIX
```

### Integration Point

`CapabilityDiscoveryMonitor` plugs into `curiosity_core.py` alongside existing monitors (around line 2140), following the same pattern:

```python
# CAPABILITY DISCOVERY: Detect missing tools, skills, patterns
try:
    capability_monitor = CapabilityDiscoveryMonitor()
    capability_questions = capability_monitor.generate_capability_questions()
    questions.extend(capability_questions)
    logger.info(f"[curiosity_core] Generated {len(capability_questions)} capability gap questions")
except Exception as e:
    logger.warning(f"[curiosity_core] Failed to generate capability questions: {e}")
```

## Prioritization System

### Hybrid Scoring Formula

The system scores each capability gap across 4 dimensions:

**1. Frequency Score (0.0-1.0)**
- Track operation patterns over 7-day window
- Example: "Grepped logs 47 times, avg file size 50MB" → frequency=0.85
- System boosts reactive gaps (immediate need = higher frequency)
- Stored in `/home/kloros/.kloros/operation_patterns.jsonl`

**2. VOI Score (0.0-1.0)**
- Use existing brainmods reasoning (`curiosity_reasoning.py`)
- Estimates value vs cost for acquiring capability
- Considers: time savings, quality improvement, risk reduction
- Same system that already re-ranks questions

**3. Alignment Score (0.0-1.0)**
- Measures capability alignment with KLoROS's core mission
- Mission dimensions: autonomy, self-improvement, reliability, cognitive depth
- Example: Self-healing tool (high alignment=0.9) vs syntax highlighter (low alignment=0.3)
- Scanner metadata defines this score

**4. Cost Factor (0.0-1.0, inverted)**
- Installation complexity (apt install vs compile from source)
- Learning curve (well-documented vs obscure API)
- Maintenance burden (stable vs experimental)
- Dependency risk (adds 0 deps vs adds 50 deps)

### Final Priority Score

```python
priority = (frequency * 0.3) + (voi * 0.35) + (alignment * 0.25) + ((1.0 - cost) * 0.1)
```

**Weight Rationale**:
- VOI highest (35%) - evidence-based value estimation
- Frequency second (30%) - solve recurring pain points
- Alignment third (25%) - stay true to purpose
- Cost lowest (10%) - don't let cost dominate, but consider it

### Cooldown Periods (ProcessedQuestionFilter)

- External tools: 14 days (dependencies change slowly)
- Skills/patterns: 7 days (techniques evolve faster)
- Reactive gaps: 3 days (problems resurface quickly if unsolved)

## Scanner Interface

### Base Scanner Protocol

```python
from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass

@dataclass
class CapabilityGap:
    """Represents a missing capability."""
    type: str              # 'external_tool', 'skill', 'pattern'
    name: str              # 'ripgrep', 'database-migrations', 'circuit-breaker'
    category: str          # 'pypi_package', 'claude_skill', 'arch_pattern'
    reason: str            # Why this capability is needed
    alignment_score: float # 0.0-1.0
    install_cost: float    # 0.0-1.0
    metadata: dict = None  # Scanner-specific data

@dataclass
class ScannerMetadata:
    """Scanner identification and scheduling info."""
    name: str
    domain: str            # 'external_tools', 'skills', 'patterns'
    alignment_baseline: float  # Base alignment for gaps from this scanner
    scan_cost: float       # Resource cost (0.0-1.0)
    schedule_weight: float # How often to run (1.0=every cycle, 0.1=rarely)

class CapabilityScanner(ABC):
    """Base class for all capability scanners."""

    @abstractmethod
    def scan(self) -> List[CapabilityGap]:
        """Discover missing capabilities. Returns list of gaps."""
        pass

    @abstractmethod
    def get_metadata(self) -> ScannerMetadata:
        """Return scanner info: name, domain, alignment_baseline, scan_cost."""
        pass

    def should_run(self, last_run: float, idle_budget: float) -> bool:
        """Default scheduling logic - can be overridden."""
        import time
        metadata = self.get_metadata()
        time_since_last = time.time() - last_run

        # Run based on schedule_weight and available budget
        min_interval = 3600 * (1.0 / metadata.schedule_weight)  # Hours to seconds
        return time_since_last >= min_interval and metadata.scan_cost <= idle_budget
```

### Scanner Discovery (Zooid Pattern)

Scanners auto-register by existing in `/home/kloros/src/registry/capability_scanners/`:

```
capability_scanners/
├── __init__.py           # Auto-discovers scanner classes
├── base.py               # CapabilityScanner ABC
├── pypi_scanner.py       # PyPIScanner
├── skill_scanner.py      # SkillMarketplaceScanner
├── pattern_scanner.py    # PatternLibraryScanner
└── reactive_scanner.py   # ReactiveGapScanner
```

### Example Scanner - PyPIScanner

```python
class PyPIScanner(CapabilityScanner):
    """Detects missing Python packages that could improve capabilities."""

    def scan(self) -> List[CapabilityGap]:
        """Compare installed packages vs curated lists."""
        installed = self._get_installed_packages()

        # Curated lists by domain
        ml_packages = ['torch', 'transformers', 'mlflow', 'wandb']
        devops_packages = ['docker', 'kubernetes', 'ansible']
        monitoring_packages = ['prometheus-client', 'opentelemetry']

        gaps = []
        for pkg in (ml_packages + devops_packages + monitoring_packages):
            if pkg not in installed:
                domain = self._detect_active_domain()  # ML, DevOps, etc.
                gaps.append(CapabilityGap(
                    type='external_tool',
                    name=pkg,
                    category='pypi_package',
                    reason=f"Package {pkg} not installed but commonly used in {domain} work",
                    alignment_score=self._calc_alignment(pkg),
                    install_cost=self._estimate_cost(pkg)
                ))
        return gaps

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name='PyPIScanner',
            domain='external_tools',
            alignment_baseline=0.6,  # Tools generally medium alignment
            scan_cost=0.15,          # Low cost (local pip list)
            schedule_weight=0.5      # Run every ~2 hours idle
        )
```

### ReactiveGapScanner (Special Case)

- Doesn't scan on schedule - listens for events
- Hooks into exception handler, resource monitors, test failures
- When problem occurs, analyzes if missing capability contributed
- Example: "Git operation failed → git-lfs missing for large files"

## Meta-Monitor Implementation

### MonitorHealthMonitor

Tracks scanner effectiveness and proposes consolidation.

**Tracked Metrics** (per scanner, 30-day window):

```python
{
    "scanner_name": "PyPIScanner",
    "runs": 42,
    "questions_generated": 67,
    "questions_investigated": 12,  # Spawned D-REAM experiments
    "improvements_made": 3,         # Led to actual installations
    "avg_scan_time_ms": 245,
    "resource_cost_score": 0.15,   # CPU/memory normalized
    "last_run": 1730908800.123
}
```

**Consolidation Detection**:

1. **Overlap Analysis**: Compare question similarity across scanners
   - System flags scanners for consolidation when they generate questions with >70% semantic similarity
   - Use simple text embedding or keyword overlap (avoid heavy dependencies)

2. **Value/Cost Ratio**: `improvement_rate / resource_cost`
   - Low ratio (< 0.1) for 30 days → propose deprecation
   - High ratio (> 0.5) → increase scan frequency

**Generated Meta-Questions**:

```python
CuriosityQuestion(
    id="meta.scanner_overlap.pypi_pattern",
    hypothesis="REDUNDANT_SCANNERS_pypi_pattern",
    question="Should PyPIScanner and PatternLibraryScanner consolidate their pytest detection logic?",
    evidence=[
        "PyPIScanner generated 12 pytest-plugin questions",
        "PatternLibraryScanner generated 8 pytest-pattern questions",
        "67% semantic overlap detected",
        "Combined resource_cost could drop from 0.30 to 0.18"
    ],
    action_class=ActionClass.PROPOSE_FIX,
    value_estimate=0.4,  # Efficiency gain
    cost=0.3             # Refactoring cost
)
```

**Execution Schedule**: Runs every 7 days (gives scanners time to prove value)

**Storage**: `/home/kloros/.kloros/scanner_health.jsonl` - append-only metrics log

## Error Handling & Failure Modes

### Scanner Failure Isolation

- Each scanner runs in try/except block (like current monitors)
- Scanner exceptions log warnings but don't crash CapabilityDiscoveryMonitor
- System penalizes failed scanners but doesn't immediately disable them
- After 3 consecutive failures, system suspends scanner until manual review

### Meta-Monitor Failure

- If MonitorHealthMonitor fails, system continues without consolidation
- Fail-safe: Scanner count hard limit (max 20 active scanners)
- If limit reached without working meta-monitor, system auto-suspends oldest low-value scanner

### Reactive Gap False Positives

- Not every problem means missing capability
- ReactiveGapScanner uses heuristics to filter noise:
  - Only trigger on repeated failures (same operation fails 3+ times)
  - Ignore transient network/permission errors
  - Focus on capability gaps, not configuration issues

### Question Spam Prevention

- ProcessedQuestionFilter cooldowns prevent re-asking
- Hard limit: Max 10 capability-gap questions per feed generation
- If scanners generate >10, take top priority scores

### Resource Budget

- Proactive scanning only during idle (orchestrator NOOP state)
- Max 5 seconds total scanner execution per cycle
- System deprioritizes scanners exceeding budget

### Storage Growth Management

- `operation_patterns.jsonl` - 7-day rolling window, auto-prunes old entries
- `scanner_health.jsonl` - 30-day window, monthly compaction
- Both files capped at 10MB, system drops oldest entries if exceeded

## Temporal Continuity (State Persistence Across Restarts)

**Problem**: Monitors must maintain awareness across system restarts. Without persistence, scanner health metrics, operation patterns, and learning reset to zero each time KLoROS restarts.

**Solution**: All monitor state persists to disk in JSONL format, loaded on startup.

### Persisted State Files

**1. `/home/kloros/.kloros/scanner_health.jsonl`**
- Scanner performance metrics (runs, questions generated, improvements made)
- Append-only log with periodic compaction
- Loaded into memory on `MonitorHealthMonitor.__init__()`
- Written after each scanner run

**2. `/home/kloros/.kloros/operation_patterns.jsonl`**
- Operation frequency tracking (grep calls, file searches, etc.)
- Rolling 7-day window
- Loaded on `CapabilityDiscoveryMonitor.__init__()`
- Updated in real-time as operations occur

**3. `/home/kloros/.kloros/scanner_state.json`**
- Last run timestamps per scanner
- Scanner suspension status (disabled scanners)
- Schedule weights (adaptive based on performance)
- Overwritten on each monitor cycle

**4. `/home/kloros/.kloros/processed_questions.jsonl`** (existing)
- Already persisted - no changes needed
- Tracks cooldown periods across restarts

### Load Strategy (Startup)

```python
class CapabilityDiscoveryMonitor:
    def __init__(self):
        # Load scanner state
        self.scanner_state = self._load_scanner_state()

        # Load operation patterns (7-day window)
        self.operation_patterns = self._load_operation_patterns()

        # Discover and register scanners
        self.scanners = self._discover_scanners()

        # Restore per-scanner metadata
        for scanner in self.scanners:
            scanner_name = scanner.get_metadata().name
            if scanner_name in self.scanner_state:
                scanner.last_run = self.scanner_state[scanner_name]['last_run']
                scanner.suspended = self.scanner_state[scanner_name].get('suspended', False)
```

### Write Strategy (Runtime)

**Scanner Health** (append-only):
```python
def _record_scanner_run(self, scanner_name, metrics):
    with open('/home/kloros/.kloros/scanner_health.jsonl', 'a') as f:
        entry = {
            'timestamp': time.time(),
            'scanner': scanner_name,
            'metrics': metrics
        }
        f.write(json.dumps(entry) + '\n')
```

**Scanner State** (atomic overwrite):
```python
def _save_scanner_state(self):
    state = {
        scanner.get_metadata().name: {
            'last_run': scanner.last_run,
            'suspended': scanner.suspended,
            'schedule_weight': scanner.schedule_weight
        }
        for scanner in self.scanners
    }

    # Atomic write (write to temp, then rename)
    tmp_path = '/home/kloros/.kloros/scanner_state.json.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(state, f, indent=2)
    os.rename(tmp_path, '/home/kloros/.kloros/scanner_state.json')
```

### Compaction Strategy (Periodic)

**Scanner Health Compaction** (monthly):
- Aggregate old entries into summaries
- Keep detailed logs for last 30 days
- Keep monthly summaries for older data
- Prevents unbounded growth while maintaining history

**Operation Patterns Cleanup** (daily):
- Delete entries older than 7 days
- Aggregate hourly stats into daily if needed
- Keeps file size bounded

### Recovery From Corruption

- All JSONL files: Skip malformed lines, log warning, continue
- Scanner state JSON: If corrupted, initialize empty state (fail-safe)
- No single file corruption crashes the system
- Corruption logged to system logs for investigation

**Design Principle**: Temporal continuity is critical for autopoiesis. The system must remember its own evolution to avoid repeating learning cycles.

## File Structure

```
/home/kloros/
├── src/
│   └── registry/
│       ├── curiosity_core.py                    # Integration point (line ~2140)
│       ├── capability_discovery_monitor.py      # Main orchestrator (NEW)
│       ├── monitor_health_monitor.py            # Meta-monitor (NEW)
│       └── capability_scanners/                 # Scanner plugins (NEW)
│           ├── __init__.py
│           ├── base.py
│           ├── pypi_scanner.py
│           ├── skill_scanner.py
│           ├── pattern_scanner.py
│           └── reactive_scanner.py
├── .kloros/
│   ├── operation_patterns.jsonl                 # Frequency tracking (NEW)
│   ├── scanner_health.jsonl                     # Meta-monitor data (NEW)
│   ├── scanner_state.json                       # Scanner persistence state (NEW)
│   ├── processed_questions.jsonl                # Existing - cooldown tracking
│   └── curiosity_feed.json                      # Existing - question output
└── docs/
    └── plans/
        └── 2025-11-06-capability-discovery-design.md  # This document
```

## Implementation Phases

### Phase 1: Foundation (Core Infrastructure)
- Base scanner protocol (`CapabilityScanner` ABC)
- Scanner discovery mechanism
- `CapabilityDiscoveryMonitor` orchestrator
- Integration into `curiosity_core.py`

### Phase 2: Initial Scanners (Prove Value)
- `PyPIScanner` - Most concrete, easy to validate
- `ReactiveGapScanner` - Capture real problems
- Test with limited package lists

### Phase 3: Prioritization (Scoring System)
- Operation pattern tracking
- Hybrid scoring implementation
- Integration with brainmods VOI reasoning

### Phase 4: Meta-Cognition (Prevent Bloat)
- `MonitorHealthMonitor` implementation
- Scanner health tracking
- Consolidation proposal generation

### Phase 5: Expansion (More Scanners)
- `SkillMarketplaceScanner`
- `PatternLibraryScanner`
- Domain-specific scanners as needs emerge

## Success Metrics

**Capability Discovery Effectiveness**:
- Questions generated per week (target: 5-15)
- Questions investigated (target: >30% investigation rate)
- Improvements made (target: >10% of investigated questions lead to actual installations)

**Meta-Monitor Effectiveness**:
- Scanner consolidations proposed (target: 1-2 per month as system matures)
- Scanner deprecations (target: Remove 1 low-value scanner per quarter)
- Total scanner count stability (target: <15 active scanners long-term)

**System Health**:
- Proactive scan overhead (target: <2% of idle time)
- False positive rate (target: <20% of questions are "not actually useful")
- Storage growth (target: <1MB/month for new tracking files)

## Computational Autopoiesis Alignment

This design embodies computational autopoiesis through:

1. **Self-Awareness**: KLoROS becomes aware of her own capability boundaries
2. **Self-Improvement**: Proactively seeks missing capabilities without external prompting
3. **Self-Regulation**: Meta-monitor prevents unchecked scanner growth
4. **Adaptive**: Scanners compete for attention based on demonstrated value
5. **Recursive**: Meta-monitor can propose consolidation of itself if redundant with other monitors

The system maintains itself through natural selection of effective scanners, periodic consolidation cycles, and continuous evaluation of monitoring efficiency.

## Notes

- Design validated through Q&A with user on 2025-11-06
- Key insight: Meta-monitor prevents scanner bloat (user concern about zooid architecture proliferation)
- Aligns with existing curiosity system architecture and question lifecycle management
- Reuses ProcessedQuestionFilter for cooldowns (computational autopoiesis principle)
- Compatible with brainmods reasoning system for VOI scoring
