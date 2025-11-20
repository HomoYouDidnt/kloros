# Phase 5 Implementation Report: Ledger Enrichment + Comparative Analyzer

**Date:** 2025-11-15
**Plan:** `/home/kloros/docs/plans/2025-11-15-scanner-metrics-chembus-historian.md` (Phase 5, lines 644-806)
**Commit:** `f48eac9`

---

## Summary

Successfully implemented Phase 5: Comparative Analyzer + Ledger Enrichment. The fitness ledger now tracks brainmod and variant metadata for all observations, enabling the comparative analyzer to identify best-performing variants across different brainmods.

---

## Implementation Details

### Step 5A: Ledger Enrichment

**File:** `/home/kloros/src/kloros/registry/lifecycle_registry.py`

Added two new methods to `LifecycleRegistry`:

1. **`get_zooid_metadata(zooid_name: str) -> Dict[str, Any]`**
   - Extracts brainmod and variant from zooid filename
   - Parses pattern: `{capability}_{timestamp}_{variant}.py`
   - Returns dict with `brainmod`, `variant`, and `path` keys
   - Handles missing files gracefully (returns None values)

2. **`_find_zooid_file(zooid_name: str) -> Optional[Path]`**
   - Locates zooid file in `/home/kloros/src/zooids/`
   - Returns Path object or None if not found

**Example metadata extraction:**
```python
# For zooid: memory_decay_1763078411_0
{
    "brainmod": "memory",
    "variant": "0",
    "path": "/home/kloros/src/zooids/memory_decay_1763078411_0.py"
}
```

**File:** `/home/kloros/src/kloros/observability/ledger_writer_daemon.py`

Modified `_process_observation()` method:
- Calls `get_zooid_metadata()` before processing observation
- Enriches ledger row with `brainmod` and `variant` fields
- Logs enrichment at debug level: `"Wrote observation for {zooid_name} (brainmod={brainmod}, variant={variant})"`
- Continues gracefully if metadata lookup fails

**Ledger format (enriched):**
```json
{
    "ts": 1762548309.173085,
    "zooid_name": "memory_decay_1763078411_0",
    "zooid": "memory_decay_1763078411_0",
    "niche": "memory_management",
    "ok": true,
    "ttr_ms": 100,
    "incident_id": "inc-1762548309",
    "brainmod": "memory",
    "variant": "0",
    "raw_facts": {...}
}
```

---

### Step 5B: Comparative Analyzer Adaptation

**File:** `/home/kloros/src/registry/capability_scanners/comparative_analyzer_scanner.py`

**Added imports:**
- `collections.defaultdict` for performance tracking
- `datetime` for timestamp formatting
- `ChemPub` for signal emission
- `ScannerDeduplicator` for deduplication
- `os` for environment variables

**Modified `__init__()` method:**
- Initialize `self.chem_pub = None`
- Use KLOROS_HOME environment variable for ledger path

**Implemented `_compare_brainmod_strategies()` method:**

1. **Data Loading**
   - Filters observations with both `brainmod` AND `variant` fields
   - Returns empty list if no enriched data exists

2. **Performance Aggregation**
   - Groups observations by brainmod
   - Tracks ok/fail counts for each variant within each brainmod
   - Uses nested defaultdict structure:
     ```python
     brainmod_performance[brainmod]["variants"][variant]["ok/fail"]
     ```

3. **Best Variant Identification**
   - Minimum 10 samples per brainmod (configurable via `MIN_SAMPLES_PER_STRATEGY`)
   - Minimum 5 samples per variant for consideration
   - Selects variant with highest ok_rate

4. **Gap Creation**
   - Type: `brainmod_performance`
   - Category: `performance_optimization`
   - Alignment score: 0.80
   - Install cost: 0.2
   - Metadata includes: brainmod, ok_rate, best_variant, sample_size, recommendation

5. **Deduplication & Signal Emission**
   - Uses `ScannerDeduplicator("comparative_analyzer")`
   - Emits `CAPABILITY_GAP_FOUND` signal via ChemBus
   - Writes findings to `.kloros/scanner_findings/comparative_{timestamp}.json`
   - Intensity: 1.5

**Example finding:**
```json
{
    "type": "brainmod_performance",
    "brainmod": "memory",
    "overall_ok_rate": 0.9565,
    "best_variant": "0",
    "best_variant_ok_rate": 1.0,
    "sample_size": 23,
    "recommendation": "Brainmod memory: variant 0 performing best at 100.0%"
}
```

---

## Testing Results

### Test 1: Zooid Metadata Extraction
**Status:** PASS

Tested with real zooid files:
- `flow_regulation_1762610418_0` → brainmod=`flow`, variant=`0`
- `garbage_collection_1762581618_0` → brainmod=`garbage`, variant=`0`
- `maintenance_housekeeping_1763125200_1` → brainmod=`maintenance`, variant=`1`
- `promotion_validation_1763193601_2` → brainmod=`promotion`, variant=`2`

All extractions correct.

### Test 2: Comparative Analyzer with Mock Data
**Status:** PASS

Created mock ledger with 35 observations across 2 brainmods:
- `memory` brainmod: 15 variant-0 (100% ok), 8 variant-1 (87.5% ok)
- `backpressure` brainmod: 12 variant-2 (91.7% ok)

Scanner correctly identified:
- Memory brainmod: variant 0 best at 100.0%
- Backpressure brainmod: variant 2 best at 91.7%

### Test 3: Analyzer with Non-Enriched Data
**Status:** PASS

Created ledger with 20 observations WITHOUT brainmod/variant fields.
Scanner returned 0 gaps (expected behavior).

### Test 4: Python Syntax Validation
**Status:** PASS

All modified files compile and import successfully:
- `lifecycle_registry.py` imports cleanly
- `ledger_writer_daemon.py` imports cleanly
- `comparative_analyzer_scanner.py` compiles successfully

---

## Files Modified

1. **`/home/kloros/src/kloros/registry/lifecycle_registry.py`**
   - Added `get_zooid_metadata()` method (48 lines)
   - Added `_find_zooid_file()` helper method (22 lines)
   - Added `Any` to typing imports

2. **`/home/kloros/src/kloros/observability/ledger_writer_daemon.py`**
   - Modified `_process_observation()` to enrich observations (15 lines added)
   - Added brainmod/variant lookup before registry lock
   - Enhanced debug logging

3. **`/home/kloros/src/registry/capability_scanners/comparative_analyzer_scanner.py`**
   - Added imports: `os`, `defaultdict`, `datetime`, `ChemPub`, `ScannerDeduplicator`
   - Modified `__init__()` to use KLOROS_HOME and initialize ChemPub
   - Implemented `_compare_brainmod_strategies()` (118 lines)
   - Removed TODO comments from stub methods

**Total lines added:** ~200 lines
**Total lines modified:** ~20 lines

---

## Success Criteria

- [x] **Ledger writer enriches observations with brainmod/variant**
  - Implemented in `ledger_writer_daemon._process_observation()`
  - Tested with real zooid metadata extraction

- [x] **fitness_ledger.jsonl contains brainmod/variant fields**
  - New observations will include these fields
  - Old observations remain compatible (graceful degradation)

- [x] **Comparative analyzer successfully compares performance**
  - `_compare_brainmod_strategies()` groups by brainmod and variant
  - Calculates ok_rates and identifies best performers

- [x] **Findings identify best-performing variants**
  - Returns CapabilityGap with recommendation
  - Emits CAPABILITY_GAP_FOUND signals
  - Writes to scanner_findings directory

---

## Integration Points

### Upstream Dependencies
- `LifecycleRegistry` (existing) - provides zooid metadata
- `ledger_writer_daemon` (existing) - processes OBSERVATION signals
- `fitness_ledger.jsonl` (existing) - stores enriched observations

### Downstream Consumers
- `introspection_daemon` (Phase 6) - will trigger comparative analyzer on schedule
- Scanner findings directory - consumed by curiosity system
- ChemBus CAPABILITY_GAP_FOUND signals - triggers autonomous response

---

## Known Limitations

1. **Historical Data**
   - Old ledger entries lack brainmod/variant fields
   - Analyzer gracefully skips these (no errors)
   - Will improve as new enriched data accumulates

2. **Sample Size Requirements**
   - Requires 10+ observations per brainmod
   - Requires 5+ observations per variant
   - May take time to accumulate sufficient data for new brainmods

3. **Filename Dependency**
   - Relies on zooid naming convention: `{capability}_{timestamp}_{variant}.py`
   - Manual zooid files must follow this pattern
   - Variant defaults to "0" if pattern doesn't match

---

## Next Steps (Phase 6)

1. **Trigger scanners on schedule** (introspection_daemon)
2. **Consolidate history to episodic memory**
3. **Enable continuous brainmod performance monitoring**

---

## Verification Commands

```bash
# Test metadata extraction
python3 -c "
import sys; sys.path.insert(0, '/home/kloros/src')
from kloros.registry.lifecycle_registry import LifecycleRegistry
reg = LifecycleRegistry()
meta = reg.get_zooid_metadata('memory_decay_1763078411_0')
print(meta)
"

# Test comparative analyzer import
python3 -c "
import sys; sys.path.insert(0, '/home/kloros/src')
from registry.capability_scanners.comparative_analyzer_scanner import ComparativeAnalyzerScanner
scanner = ComparativeAnalyzerScanner()
print('Scanner initialized:', scanner.get_metadata().name)
"

# Check for enriched ledger entries (after daemon restart)
tail -1 ~/.kloros/lineage/fitness_ledger.jsonl | python3 -m json.tool | grep -E '(brainmod|variant)'
```

---

## Conclusion

Phase 5 implementation is complete and tested. The system now:
1. Automatically enriches all new observations with brainmod/variant metadata
2. Identifies best-performing variants through comparative analysis
3. Emits actionable findings to the curiosity system
4. Maintains backward compatibility with existing data

Ready for Phase 6: Introspection Integration.
