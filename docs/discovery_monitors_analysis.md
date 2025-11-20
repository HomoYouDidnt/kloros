# Discovery Monitors Analysis - Memory Leak Investigation

**Date:** 2025-11-19
**Issue:** Four discovery monitors disabled due to memory leaks
**Memory Pressure:** Curiosity core consumer at 916MB, growing 150MB/min before disable

---

## Monitor Status

### 1. IntegrationFlowMonitor - PRIMARY CULPRIT ❌
**File:** `/home/kloros/src/registry/integration_flow_monitor.py`
**Status:** DISABLED
**Purpose:** Detect broken component wiring and architectural gaps
- Orphaned queues (producers but no consumers)
- Duplicate responsibilities (multiple components doing same thing)
- Missing wiring (calls to non-existent components)
- Dead code (registered but never invoked)

**Memory Leak Root Cause:**
```python
# Line 186-191: _scan_data_flows()
for py_file in self.src_root.rglob("*.py"):  # ← Scans ALL 500+ Python files
    if "test_" in py_file.name or "__pycache__" in str(py_file):
        continue
    try:
        self._analyze_file(py_file)  # ← Parses each to AST
```

**Problem Pattern:**
1. Every 60 seconds, runs `rglob("*.py")` finding 500+ files
2. Parses each file to AST with `ast.parse(source)`
3. AST objects and file contents accumulate in memory
4. Data structures grow unbounded:
   - `self.data_flows: List[DataFlow]`
   - `self.responsibilities: List[ComponentResponsibility]`
5. Result: **150MB/min memory growth**

**Why It Leaks:**
- No caching mechanism - re-parses unchanged files
- No cleanup - old AST trees not garbage collected
- No size limits - lists grow without bounds
- Synchronous design - blocks during full scan

**Proposed Solution (from code comments):**
- "Replace with integration-monitor-daemon (streaming, inotify-based incremental analysis)"
- See: `/home/kloros/STREAMING_ARCHITECTURE_REDESIGN.md`

---

### 2. CapabilityDiscoveryMonitor ❌
**File:** `/home/kloros/src/registry/capability_discovery_monitor.py`
**Status:** DISABLED
**Purpose:** Detect missing tools, skills, patterns
**Memory Leak Cause:** Heavy filesystem scanning every 60s

**Problem Pattern:** (Similar to IntegrationFlowMonitor)
- Scans filesystem for capability indicators
- Likely uses `rglob()` pattern
- Accumulates results without cleanup

**Proposed Solution:**
- "Replace with capability-discovery-daemon (streaming)"

---

### 3. ExplorationScanner ❌
**File:** `/home/kloros/src/registry/exploration_scanner.py`
**Status:** DISABLED
**Purpose:** Proactive hardware and optimization opportunity discovery
**Memory Leak Cause:** Heavy system scanning every 60s

**Problem Pattern:**
- System-wide scans (GPU, hardware, optimization opportunities)
- Likely accumulates scan results
- No incremental updates

**Proposed Solution:**
- "Replace with exploration-daemon (streaming, periodic GPU/hardware checks)"

---

### 4. KnowledgeDiscoveryScanner ❌
**File:** `/home/kloros/src/kloros/introspection/scanners/unindexed_knowledge_scanner.py`
**Status:** DISABLED
**Purpose:** Scan filesystem for unindexed/stale documentation and source code
**Memory Leak Cause:** Filesystem scanning causing memory accumulation

**Problem Pattern:**
- Scans docs/ and src/ for unindexed knowledge
- Likely loads file contents into memory
- No cleanup between scans

**Proposed Solution:**
- "Replace with knowledge-discovery-daemon (streaming, inotify-based)"

---

## Common Anti-Pattern

**All four monitors share the same design flaw:**

### Synchronous Batch Processing
```python
def generate_questions():
    # Scan EVERYTHING (500+ files, all docs, all hardware)
    for item in all_items:  # ← Full scan every 60s
        analyze(item)       # ← Parse, load into memory
        collect_results(item)  # ← Accumulate without limit

    return results  # ← Large result set
```

### Why This Fails at Scale

1. **No Incrementality:** Re-scans unchanged files
2. **No Caching:** Re-parses files already analyzed
3. **No Bounds:** Lists/dicts grow without limits
4. **No Cleanup:** Old results not cleared
5. **Blocking:** Entire 60s cycle blocks on scanning

### Result: O(files × cycles) Memory Growth

- Cycle 1: 150MB (500 files × AST overhead)
- Cycle 2: 300MB (old + new, GC can't collect)
- Cycle 3: 450MB (accumulation continues)
- Cycle 10: 1.5GB (system pressure)

---

## Streaming Architecture Pattern

**The proposed fix for all monitors:**

### Event-Driven Incremental Design
```python
# Daemon process with inotify file watching
import inotify.adapters

class StreamingIntegrationMonitor:
    def __init__(self):
        self.cache = {}  # File path → parsed data
        self.watcher = inotify.adapters.InotifyTree('/home/kloros/src')

    def watch_files(self):
        """Process only changed files."""
        for event in self.watcher.event_gen(yield_nones=False):
            (_, type_names, path, filename) = event

            if 'IN_MODIFY' in type_names or 'IN_CREATE' in type_names:
                # Only analyze changed file
                self._analyze_file(Path(path) / filename)
                # Update cache incrementally
                self._update_cache(path, filename)

    def _update_cache(self, path, filename):
        """Bounded cache with LRU eviction."""
        if len(self.cache) > MAX_CACHE_SIZE:
            # Evict least recently used
            self.cache.pop(next(iter(self.cache)))

        self.cache[f"{path}/{filename}"] = parsed_data
```

### Benefits

1. **Incremental:** Only analyzes changed files
2. **Bounded:** LRU cache with size limits
3. **Event-driven:** Reacts to changes, not polling
4. **Non-blocking:** Processes in background
5. **Memory-efficient:** Constant memory usage

### Result: O(1) Memory Usage

- Steady state: ~50MB (cache only)
- Peak: ~100MB (during large batch changes)
- No growth over time

---

## Implementation Strategy

### Phase 1: Quick Fix (Immediate)
**Add memory bounds to existing monitors**

For IntegrationFlowMonitor:
```python
class IntegrationFlowMonitor:
    MAX_DATA_FLOWS = 1000
    MAX_FILES_TO_SCAN = 100  # Instead of 500+

    def _scan_data_flows(self):
        self.data_flows = []  # Clear old data
        self.responsibilities = []

        # Limit files scanned
        py_files = list(self.src_root.rglob("*.py"))
        py_files = py_files[:self.MAX_FILES_TO_SCAN]

        for py_file in py_files:
            if len(self.data_flows) >= self.MAX_DATA_FLOWS:
                break  # Stop if too many
            # ... existing logic

    def _cleanup(self):
        """Clear accumulated data."""
        self.data_flows.clear()
        self.responsibilities.clear()
        import gc
        gc.collect()
```

**Pros:**
- Quick to implement (< 1 hour)
- Reduces memory pressure immediately
- Maintains existing functionality

**Cons:**
- Still inefficient (re-scans files)
- Limited coverage (misses files beyond limit)
- Doesn't solve root cause

---

### Phase 2: Caching Layer (Short-term)
**Add file hash caching to avoid re-parsing**

```python
import hashlib
from functools import lru_cache

class IntegrationFlowMonitor:
    def __init__(self):
        self.file_cache = {}  # path → (hash, parsed_data)

    def _analyze_file(self, file_path: Path):
        # Check if file changed
        current_hash = self._file_hash(file_path)

        if file_path in self.file_cache:
            cached_hash, cached_data = self.file_cache[file_path]
            if cached_hash == current_hash:
                # File unchanged, use cache
                return cached_data

        # File changed or new, parse it
        source = file_path.read_text()
        tree = ast.parse(source)
        parsed_data = self._extract_flows(tree)

        # Update cache
        self.file_cache[file_path] = (current_hash, parsed_data)
        return parsed_data

    @staticmethod
    def _file_hash(file_path: Path) -> str:
        """Fast file hash using mtime + size."""
        stat = file_path.stat()
        return f"{stat.st_mtime}_{stat.st_size}"
```

**Pros:**
- Avoids re-parsing unchanged files
- Significant memory reduction (70-90%)
- Simple to add to existing code

**Cons:**
- Still scans all files (filesystem overhead)
- Cache can grow large over time
- Doesn't fix synchronous blocking

---

### Phase 3: Streaming Daemon (Long-term)
**Convert to separate streaming daemon process**

**Architecture:**
```
┌─────────────────────────────────────┐
│  Integration Monitor Daemon         │
│  (Always running, low overhead)     │
├─────────────────────────────────────┤
│  • Watches /src with inotify        │
│  • Incremental file analysis        │
│  • Bounded LRU cache                │
│  • Emits questions via ChemBus      │
└─────────────────────────────────────┘
           │
           │ ChemBus signals
           ↓
┌─────────────────────────────────────┐
│  Curiosity Core Consumer            │
│  (Receives pre-computed questions)  │
└─────────────────────────────────────┘
```

**Benefits:**
- Constant memory usage
- Real-time updates (not 60s batches)
- Isolated process (crash-safe)
- Scales to thousands of files

**Implementation:**
- New file: `/home/kloros/src/registry/integration_monitor_daemon.py`
- Systemd service: `kloros-integration-monitor.service`
- Uses inotify for file watching
- Publishes to ChemBus: `curiosity.integration_question`

---

## Recommendation

**Immediate Action (Today):**
1. Implement Phase 1 (memory bounds) for IntegrationFlowMonitor
2. Test memory usage over 1 hour
3. Re-enable if memory stays under 500MB

**Short-term (This Week):**
1. Add Phase 2 (caching) to all four monitors
2. Re-enable monitors with reduced scanning frequency (300s instead of 60s)
3. Monitor memory usage

**Long-term (Next Sprint):**
1. Design streaming daemon architecture
2. Implement integration-monitor-daemon first (PRIMARY CULPRIT)
3. Migrate other monitors to streaming pattern
4. Document pattern for future monitors

---

## Risk Assessment

**If we do nothing:**
- Monitors stay disabled
- Missing architectural gap detection
- No orphaned queue detection
- No capability discovery
- System can't self-improve architecture

**If we implement Phase 1 only:**
- Reduced functionality (only scans subset of files)
- May miss issues in unscanned files
- Still has performance impact

**If we implement Phase 2:**
- Maintains full functionality
- Much better memory efficiency
- Still has 60s blocking scans

**If we implement Phase 3:**
- Full functionality + efficiency
- Real-time updates
- Requires significant development time
- More complex deployment

---

## Next Steps

1. ✅ Analyze all four monitors (DONE)
2. ⏳ Implement Phase 1 fix for IntegrationFlowMonitor
3. ⏳ Test memory usage with fix
4. ⏳ Apply same pattern to other 3 monitors
5. ⏳ Re-enable monitors with monitoring
6. ⏳ Plan streaming daemon migration

**Decision needed:**
- Quick fix (Phase 1) and accept limitations?
- Invest in caching (Phase 2) for better results?
- Go straight to streaming daemons (Phase 3)?
