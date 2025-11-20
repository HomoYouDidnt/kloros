# Capability Discovery System

## Overview

KLoROS automatically detects missing tools, skills, and patterns through the capability discovery system. This system complements existing failure detection by identifying *absent* capabilities rather than *broken* ones.

## Architecture

### Three Layers

1. **Scanner Layer** - Pluggable capability detectors
   - `PyPIScanner` - Missing Python packages
   - Future: `SkillScanner`, `PatternScanner`, `ReactiveGapScanner`

2. **Orchestration Layer** - `CapabilityDiscoveryMonitor`
   - Auto-discovers scanners from `capability_scanners/` package
   - Schedules scanner execution during idle time
   - Applies hybrid prioritization (frequency + VOI + alignment + cost)
   - Generates `CuriosityQuestion` objects

3. **Meta-Cognition Layer** - `MonitorHealthMonitor` (future)
   - Tracks scanner effectiveness
   - Proposes consolidation when scanners overlap
   - Prevents scanner bloat

## How It Works

### Scanner Scheduling

Scanners run based on:
- `schedule_weight` - How often to run (1.0=every hour, 0.1=every 10 hours)
- `last_run` - When scanner last executed
- `idle_budget` - Available CPU time budget
- `suspended` - Whether scanner is disabled

### Prioritization Formula

```python
priority = (frequency * 0.3) + (voi * 0.35) + (alignment * 0.25) + ((1-cost) * 0.1)
```

- **Frequency** (30%): How often related operation occurs
- **VOI** (35%): Value-of-information score (from brainmods)
- **Alignment** (25%): Alignment with core mission
- **Cost** (10%): Installation/learning cost

### Temporal Continuity

State persists across restarts:
- `/home/kloros/.kloros/scanner_state.json` - Last run times, suspension status
- `/home/kloros/.kloros/operation_patterns.jsonl` - 7-day operation frequency window

## Adding New Scanners

1. Create scanner class in `src/registry/capability_scanners/`
2. Inherit from `CapabilityScanner`
3. Implement `scan()` and `get_metadata()`
4. Scanner auto-discovers on next run

Example:

```python
from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

class MyScanner(CapabilityScanner):
    def scan(self) -> List[CapabilityGap]:
        # Detect capability gaps
        return [...]

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name='MyScanner',
            domain='my_domain',
            alignment_baseline=0.7,
            scan_cost=0.2,
            schedule_weight=0.5
        )
```

## Configuration

No configuration needed - system is self-organizing through:
- Auto-discovery of scanners
- Adaptive scheduling based on value
- State persistence for continuity

## Monitoring

Check logs for:
- `[capability_monitor] Discovered N scanners` - Scanner registration
- `[capability_monitor] Running scanner: X` - Scanner execution
- `[capability_monitor] Generated N capability questions` - Question output

## Design Document

See `docs/plans/2025-11-06-capability-discovery-design.md` for full architecture and rationale.
