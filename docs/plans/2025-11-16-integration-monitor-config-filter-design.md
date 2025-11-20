# Integration Monitor Configuration Filter Design

**Date:** 2025-11-16
**Status:** Approved
**Problem:** Integration flow monitor generates false positive "orphaned queue" questions for configuration data

## Problem Statement

The `IntegrationFlowMonitor` detects any list/dict assignment as a potential queue and flags it as "orphaned" if it finds no consumers. This generates false positives for configuration data.

**Example False Positive:**
```python
class SeparatedAudioSystem:
    def __init__(self):
        self.wake_phrases = ["kloros"]  # Configuration, not a queue
```

This gets flagged as `orphaned_queue_wake_phrases` with question: "Data structure 'wake_phrases' is populated but never consumed. Is this a broken integration?"

**Impact:**
- Wasted investigation cycles on configuration data
- RTFM finds generic architecture docs (not specific to config)
- Evidence gathering proceeds unnecessarily
- Clutters curiosity feed with non-actionable questions

## Root Cause

`FlowAnalyzer.visit_Assign()` (line 501) creates a DataFlow for ANY list assignment:
```python
if isinstance(node.value, ast.List):
    # self.queue = []
    self.flows.append(DataFlow(...))  # No config filtering
```

No distinction between:
- **Configuration data:** Initialized with literals, never mutated
- **Operational queues:** Mutated with `.append()`, `.pop()`, etc.

## Solution Overview

Add hybrid pattern detection to distinguish configuration from operational queues:

**Phase 1:** Check initialization pattern (literal values?)
**Phase 2:** Check mutation pattern (queue operations used?)

**Decision Logic:**
- Literal init + No mutations = Configuration (skip)
- Empty init OR mutations = Operational queue (flag)

## Architecture

### New Components

**1. Mutation Tracking (FlowAnalyzer)**
```python
def __init__(self, file_path: Path, source: str):
    # ... existing ...
    self.mutated_attributes: Set[str] = set()  # Track queue mutations
```

**2. Configuration Detection**
```python
def _is_configuration_data(self, attr_name: str, node: ast.Assign) -> bool:
    """
    Check if assignment is configuration vs operational queue.

    Returns True if:
    - Initialized with literal values (not variables/calls)
    - Never mutated with queue operations
    """
    if isinstance(node.value, (ast.List, ast.Dict)):
        has_literals = self._has_literal_values(node.value)
        is_mutated = attr_name in self.mutated_attributes

        # Config = literals AND not mutated
        return has_literals and not is_mutated

    return False

def _has_literal_values(self, node: ast.expr) -> bool:
    """Check if list/dict contains only literal values."""
    if isinstance(node, ast.List):
        return all(isinstance(elt, (ast.Constant, ast.Str, ast.Num))
                   for elt in node.elts)

    elif isinstance(node, ast.Dict):
        return all(isinstance(k, (ast.Constant, ast.Str, ast.Num)) and
                   isinstance(v, (ast.Constant, ast.Str, ast.Num))
                   for k, v in zip(node.keys, node.values))

    return False
```

**3. Mutation Detection (Enhanced visit_Call)**
```python
def visit_Call(self, node):
    """Visit function calls to detect queue operations."""
    # Pattern: self.queue.append(item)
    if isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Attribute):
            if isinstance(node.func.value.value, ast.Name):
                if node.func.value.value.id == 'self':
                    attr_name = node.func.value.attr
                    method_name = node.func.id

                    # Track queue mutations
                    QUEUE_METHODS = {
                        'append', 'pop', 'extend', 'clear',
                        'insert', 'remove', 'popleft'
                    }
                    if method_name in QUEUE_METHODS:
                        self.mutated_attributes.add(attr_name)

    self.generic_visit(node)
```

**4. Integration (Modified visit_Assign)**
```python
def visit_Assign(self, node):
    """Visit assignment to detect queue/list creation."""
    if isinstance(node.targets[0], ast.Attribute):
        attr = node.targets[0]
        if isinstance(attr.value, ast.Name) and attr.value.id == 'self':
            attr_name = attr.attr

            if isinstance(node.value, ast.List):
                # NEW: Skip configuration data
                if self._is_configuration_data(attr_name, node):
                    self.generic_visit(node)
                    return

                # Original: Create DataFlow for operational queue
                self.flows.append(DataFlow(...))

    self.generic_visit(node)
```

## Design Principles

1. **Fail-Open:** If detection uncertain, allow the question (safer than missing real issues)
2. **Pattern-Based:** Uses AST patterns, no runtime execution needed
3. **Minimal Changes:** Adds filtering without changing existing detection logic
4. **No False Negatives:** Won't filter out real orphaned queues

## Implementation Details

### AST Traversal Pattern

The AST visitor already walks the entire tree in a single pass. Since `visit_Call()` processes all nodes including those after `visit_Assign()`, we collect all mutations during traversal and check them in `_is_configuration_data()`.

**Key Insight:** `self.mutated_attributes` is populated DURING the tree walk, so by the time we check it in `_is_configuration_data()`, it may not have seen mutations that occur later in the file.

**Solution:** Keep the current single-pass design but acknowledge edge case: If config is defined at line 10 and mutated at line 100, we'll see the mutation during the same traversal before deciding on the DataFlow.

Actually, wait - we need to be careful here. Let me reconsider...

**Better Approach - Two Pass:**
1. **Pass 1:** Collect all mutations across entire file
2. **Pass 2:** Create DataFlows, checking mutations

OR keep single pass but delay DataFlow creation:

**Single Pass with Deferred Creation:**
```python
def visit_Assign(self, node):
    # Store assignment info, don't create DataFlow yet
    if isinstance(node.value, ast.List):
        self.pending_flows.append((attr_name, node))

    self.generic_visit(node)

# After traversal completes:
def finalize_flows(self):
    for attr_name, node in self.pending_flows:
        if not self._is_configuration_data(attr_name, node):
            self.flows.append(DataFlow(...))
```

**Decision:** Use deferred creation. Simpler than two-pass, handles all edge cases.

### Updated Architecture

**FlowAnalyzer Changes:**
```python
def __init__(self, file_path: Path, source: str):
    # ... existing ...
    self.mutated_attributes: Set[str] = set()
    self.pending_flows: List[Tuple[str, ast.Assign]] = []  # Deferred creation

def visit_Assign(self, node):
    # Store for later, don't create DataFlow yet
    if isinstance(node.targets[0], ast.Attribute):
        attr = node.targets[0]
        if isinstance(attr.value, ast.Name) and attr.value.id == 'self':
            if isinstance(node.value, ast.List):
                self.pending_flows.append((attr.attr, node))

    self.generic_visit(node)

def visit_Call(self, node):
    # Track mutations as before
    # ... mutation detection ...
    self.generic_visit(node)

def finalize_flows(self):
    """Create DataFlows after full traversal, filtering config data."""
    for attr_name, node in self.pending_flows:
        if not self._is_configuration_data(attr_name, node):
            # This is an operational queue, create DataFlow
            self.flows.append(DataFlow(
                producer=self.current_class or "unknown",
                consumer=None,
                channel=attr_name,
                channel_type="queue",
                producer_file=str(self.file_path),
                consumer_file=None,
                line_number=node.lineno
            ))
```

**IntegrationFlowMonitor._analyze_file() Changes:**
```python
def _analyze_file(self, file_path: Path):
    # ... parse source ...

    analyzer = FlowAnalyzer(file_path, source)
    analyzer.visit(tree)
    analyzer.finalize_flows()  # NEW: Finalize after traversal

    self.data_flows.extend(analyzer.flows)
    self.responsibilities.extend(analyzer.responsibilities)
```

## Test Cases

### Should Filter (Configuration):
```python
self.wake_phrases = ["kloros"]  # Literal init, no mutations
self.settings = {"mode": "async"}  # Dict literal, no mutations
```

### Should NOT Filter (Operational Queues):
```python
self.queue = []  # Empty init (no literals)
self.queue.append(item)  # Has mutations

self.buffer = [1, 2, 3]  # Literal init BUT...
self.buffer.pop()  # ...has mutations = operational queue
```

### Edge Cases:
```python
self.items = [var1, var2]  # Not literals - treat as operational
self.config = []  # Empty - treat as operational
self.config = ["default"]  # Literal, no mutations - configuration ✓
```

## Expected Impact

### Before Filter:
- 19 orphaned_queue questions generated
- Most are configuration data (wake_phrases, settings, etc.)
- Investigations waste cycles on non-issues

### After Filter:
- ~5-10 orphaned_queue questions (actual issues)
- Configuration data filtered out
- Investigations focus on real architectural problems

### Log Changes:
```
[integration_monitor] Skipped 14 configuration attributes (wake_phrases, settings, ...)
[integration_monitor] Generated 5 orphaned queue questions (actual issues)
```

## Files Changed

### Modified:
- `/home/kloros/src/registry/integration_flow_monitor.py`
  - Add `mutated_attributes` tracking
  - Add `pending_flows` for deferred creation
  - Add `_is_configuration_data()` method
  - Add `_has_literal_values()` helper
  - Enhance `visit_Call()` for mutation detection
  - Modify `visit_Assign()` to defer DataFlow creation
  - Add `finalize_flows()` method
  - Call `finalize_flows()` in `_analyze_file()`

## Success Criteria

1. ✅ `wake_phrases` not flagged as orphaned queue
2. ✅ Real queues (with `.append()`) still flagged
3. ✅ Configuration dicts filtered correctly
4. ✅ No false negatives (real issues still caught)
5. ✅ Reflection cycle generates <10 orphaned queue questions (down from 19)

## Future Enhancements

- Add explicit `@config` decorator for manual marking
- Detect class-level constants (UPPERCASE_NAME = [...])
- Handle dataclass fields with default_factory
- Support configuration loaded from files (yaml/json)

---

**Design Status:** Approved for implementation
**Next Step:** Implement deferred DataFlow creation with configuration filtering
