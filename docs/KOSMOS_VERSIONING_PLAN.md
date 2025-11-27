# KOSMOS Versioning & Lineage Tracking - Implementation Summary

## Status: Design Complete, Ready for Integration

### What's Been Built

#### 1. Knowledge Lineage Log Module ✅
**File:** `/home/kloros/src/kloros_memory/knowledge_lineage.py`

**Features:**
- Append-only JSON Lines log at `~/.kloros/knowledge_lineage.jsonl`
- `LineageEvent` dataclass for structured event tracking
- `KnowledgeLineageLog` class with methods:
  - `log_event()` - Append new lineage event
  - `get_version_history(file_path)` - Full history of a file
  - `get_events_in_range(start, end)` - Time-range queries
  - `get_latest_version(file_path)` - Most recent version
  - Hash computation helpers

**Event Structure:**
```json
{
  "timestamp": "2025-11-23T09:00:00.000Z",
  "event_type": "indexed",
  "file_path": "/home/kloros/docs/KOSMOS_SYSTEM.md",
  "version": 1,
  "change_type": "new",
  "content_hash": "sha256:abc123",
  "summary_hash": "sha256:def456",
  "git_commit": "a1b2c3d4",
  "git_message": "Add KOSMOS documentation",
  "indexed_by": "manual",
  "summary_preview": "KOSMOS is..."
}
```

#### 2. Git Integration Design ✅
**Designed methods:**
- `_get_git_info(file_path)` - Extract commit, branch, message
- Git repo detection
- Short commit hash (12 chars)
- Last commit message for file

#### 3. Enhanced Metadata Schema ✅
**Designed additions to Qdrant payload:**
```python
{
    # ... existing fields ...
    
    # Versioning
    "version": 1,
    "content_hash": "sha256:abc123",
    "summary_hash": "sha256:def456",
    "git_commit": "a1b2c3d4",
    "git_repo": "/home/kloros/src",
    "git_branch": "main",
    "git_message": "Add feature X",
    
    # Lineage
    "indexed_by": "unindexed_scanner",
    "change_type": "new",  # new | updated | reindexed
    "previous_version": 0,
    "content_changed": True,
}
```

### Integration Plan

#### Step 1: Add Imports to kosmos.py
```python
import subprocess
from .knowledge_lineage import get_lineage_log, LineageEvent
```

#### Step 2: Add Git Helper Methods to KOSMOS Class
- `_get_git_info(file_path)` - 50 lines
- `_compute_content_hash(content)` - 3 lines
- `_get_previous_version_info(file_path)` - 20 lines

#### Step 3: Enhance summarize_and_index() Method
Insert after `temporal_metadata` extraction:
1. Get previous version from Qdrant
2. Compute content/summary hashes
3. Get git info
4. Determine version number and change type
5. Create and log LineageEvent
6. Add versioning metadata to payload

**Estimated changes:** ~60 lines of code

#### Step 4: Add Version Query API
New methods to add to KOSMOS class:
```python
def get_version_history(file_path: str) -> List[Dict]:
    """Get full version history of a file."""
    
def get_lineage_events(start_time: str, end_time: str) -> List[Dict]:
    """Get all lineage events in time range."""
    
def query_at_time(query: str, timestamp: str) -> List[Dict]:
    """Search knowledge as it existed at specific time."""
```

### Benefits Once Integrated

1. **Temporal Queries**
   ```python
   # What did KOSMOS know on Oct 1st?
   kosmos.query_at_time("UMN architecture", "2025-10-01")
   ```

2. **Version History**
   ```python
   # See how understanding evolved
   history = kosmos.get_version_history("/home/kloros/docs/CHEMBUS.md")
   # Returns: v1 (2025-10-01), v2 (2025-10-15), v3 (2025-11-20)
   ```

3. **Git Linkage**
   - Every indexed document links to git commit
   - Trace knowledge changes to code changes
   - "When did we learn about feature X?" → "Commit a1b2c3d4"

4. **Audit Trail**
   - Complete history of what entered the canon and when
   - Change detection: content vs summary changes
   - Attribution: which component triggered indexing

5. **Knowledge Evolution**
   - Track how summaries improved over time
   - Detect contradictions between versions
   - Rollback if needed

### Example Lineage Log Output

After integration, `~/.kloros/knowledge_lineage.jsonl` would contain:

```json
{"timestamp": "2025-11-23T08:00:00Z", "event_type": "indexed", "file_path": "/home/kloros/docs/KOSMOS_SYSTEM.md", "version": 1, "change_type": "new", "git_commit": "f3a7b92c", "summary_preview": "KOSMOS is the canonical source of truth..."}
{"timestamp": "2025-11-23T09:00:00Z", "event_type": "indexed", "file_path": "/home/kloros/docs/KOSMOS_SYSTEM.md", "version": 2, "change_type": "updated", "git_commit": "f3a7b92c", "summary_preview": "KOSMOS: Kosmos Obey Structured Memory..."}
{"timestamp": "2025-11-23T10:00:00Z", "event_type": "indexed", "file_path": "/home/kloros/docs/CHEMBUS_V2.md", "version": 1, "change_type": "new", "git_commit": "e9d4c1a8", "summary_preview": "UMN v2 is a signal-based message bus..."}
```

### Next Steps

1. ✅ Design complete
2. ✅ Lineage log module created
3. ⏳ Integrate into kosmos.py (60 lines of code changes)
4. ⏳ Test with real indexing operations
5. ⏳ Update KOSMOS_SYSTEM.md documentation
6. ⏳ Restart services to activate

### Files Created

- `/home/kloros/src/kloros_memory/knowledge_lineage.py` ✅
- `/tmp/kosmos_versioning_design.md` ✅
- `/tmp/git_helpers.py` (reference implementation) ✅
- `/tmp/kosmos_versioning_patch.py` (integration guide) ✅

### Impact

**Zero breaking changes** - Existing KOSMOS functionality unchanged, only enhanced with:
- New metadata fields in Qdrant (backward compatible)
- New lineage log file (independent of existing operations)
- New query methods (additive, not replacing)

**Canonical Authority Enhanced:**
- KOSMOS now has **memory of its own evolution**
- Can answer "when did I learn this?" 
- Provides audit trail for Adam to review what entered the canon

**Adam → KOSMOS → KLoROS hierarchy strengthened:**
- Adam can query: "What did KOSMOS know on date X?"
- Adam can review lineage: "What changed in version Y?"
- Adam can verify: "Was this in the canon when decision Z was made?"

---

**Status:** Ready for integration when you approve. Estimated integration time: 30 minutes.
