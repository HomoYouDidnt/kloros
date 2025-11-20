# Curiosity System: Is She Actually Fixing Things?

**Date:** 2025-11-03 23:35
**Question:** Is she producing actionable fixes and solutions to her questions?

---

## Answer: **PARTIALLY - She Investigates But Doesn't Fix**

---

## What She Actually Does

### The Pipeline (As Built)

```
Reflection Cycle (every 10 min)
    ↓
CuriosityCore.generate_questions_from_matrix()
    → Generates 107 questions
    → Filters to top 20 by VOI
    → Writes to curiosity_feed.json
    ↓
curiosity.get_top_questions(n=1)  ← TAKES ONLY 1 QUESTION
    ↓
Route based on action_class:
    ├─ "investigate" → _investigate_capability_gap()
    │   └─ Run diagnostic probes (groups, pactl, env vars)
    │   └─ Log to curiosity_investigations.jsonl
    │   └─ NO FIX APPLIED
    │
    ├─ "propose_fix" → _surface_capability_question_to_user()
    │   └─ Log to curiosity_surface_log.jsonl
    │   └─ NO FIX APPLIED (just logged)
    │
    └─ "find_substitute" → _find_capability_substitute()
        └─ Search for alternatives
        └─ Log to curiosity_substitutes.jsonl
        └─ NO FIX APPLIED
```

---

## What She's Been Doing

### Investigation Count: 229 investigations
- **Every 15 minutes** since Oct 27
- Runs diagnostic probes on "undiscovered modules"
- Example (most recent):
  ```json
  {
    "capability": "undiscovered.audio",
    "question": "What does audio module do?",
    "probe_results": [
      {"probe": "groups", "output": "kloros audio video..."},
      {"probe": "pactl_sinks", "output": "54 alsa_output..."},
      {"probe": "pactl_sources", "output": "60 alsa_input..."}
    ]
  }
  ```

### Surface Log: 10 items surfaced
- Questions "surfaced to user"
- But just logged to file, **never actually shown to user**
- Last surfaced: Oct 30

### Substitute Search: 125 searches
- Looking for alternative implementations
- Logged but **never applied**

---

## The Problem

### She DETECTS Issues
✅ IntegrationFlowMonitor: 96 issues detected
✅ CuriosityCore: Questions generated
✅ Reasoning: Questions ranked by VOI

### She INVESTIGATES
✅ Runs 229 diagnostic probes
✅ Logs findings to JSONL

### She DOES NOT FIX
❌ No patches applied to code
❌ No remediation executed
❌ No improvements deployed
❌ Questions just logged, never acted upon

---

## Why Fixes Aren't Being Applied

### Missing Pipeline Step

```
Current:
  curiosity_feed.json → reflection picks top 1 → investigate → log → STOP

Missing:
  curiosity_feed.json → curiosity_processor → remediation_manager → code_patcher → deploy
```

### The curiosity_processor Exists But Isn't Called

**File:** `/home/kloros/src/kloros/orchestration/curiosity_processor.py`

**What it does:**
- Reads curiosity_feed.json
- Converts questions to intents
- Routes to D-REAM experiments
- **But:** Never called by reflection system

**How to call it:**
```python
from src.kloros.orchestration.curiosity_processor import process_curiosity_feed
result = process_curiosity_feed()
```

### The Disconnect

**Reflection system (`kloros_idle_reflection.py`):**
- Line 1514: `top_questions = curiosity.get_top_questions(n=1)`
- Line 1537: `self._investigate_capability_gap(top_q)`
- **STOPS HERE** - never calls remediation

**Curiosity processor (`curiosity_processor.py`):**
- Has method: `process_curiosity_feed()`
- Converts questions → D-REAM intents
- **NEVER CALLED**

**Remediation manager (`dream/remediation_manager.py`):**
- Has method: `generate_from_performance_question()`
- Creates fix specs
- **NEVER CALLED FOR INTEGRATION ISSUES**

**Code patcher (`dream/deploy/patcher.py`):**
- Can apply AST-based patches
- **NEVER CALLED**

---

## Example: What SHOULD Happen vs What DOES Happen

### What SHOULD Happen (For Integration Issue)

```
1. IntegrationFlowMonitor detects: "Alert queue orphaned"
2. CuriosityCore generates: Question with action="propose_fix"
3. curiosity_processor converts: Question → intent
4. remediation_manager generates: Code patch spec
5. code_patcher applies: Add get_pending_for_next_wake() call
6. Test: Run pytest
7. Deploy: If tests pass, commit
8. User notified: "Fixed alert queue integration"
```

### What ACTUALLY Happens

```
1. IntegrationFlowMonitor detects: "Alert queue orphaned"
2. CuriosityCore generates: Question with action="propose_fix"
3. ❌ Filtered out by VOI ranking (top 20 doesn't include it)
4. ❌ Never reaches curiosity_processor
5. ❌ Never reaches remediation_manager
6. ❌ Never reaches code_patcher
7. ❌ Nothing happens
```

### What ACTUALLY Happens (For Module Discovery)

```
1. ModuleDiscoveryMonitor finds: "Undiscovered module: audio"
2. CuriosityCore generates: Question with action="investigate"
3. ✅ Makes it into top 20 (VOI ~0.82)
4. ✅ Picked as top 1 question
5. Reflection calls: _investigate_capability_gap()
6. Runs probes: groups, pactl, env vars
7. Logs to: curiosity_investigations.jsonl
8. ❌ STOPS - No fix, no capability registration, no action
```

---

## The Numbers

| Metric | Count | Status |
|--------|-------|--------|
| Questions generated | ~107 per cycle | ✅ Working |
| Questions after VOI filter | 20 per cycle | ⚠️ Too aggressive |
| Questions picked for action | 1 per cycle | ⚠️ Very conservative |
| Investigations run | 229 total | ✅ Working |
| Fixes proposed | ~0 (filtered out) | ❌ Broken |
| Fixes applied | 0 | ❌ Not implemented |
| Items surfaced to user | 10 | ⚠️ Not actually shown |

---

## Why This Matters

### She's Stuck in "Research Mode"

- ✅ Excellent at **detecting** problems
- ✅ Good at **investigating** issues
- ❌ **Never takes action**

Like a scientist who:
- Runs 229 experiments
- Logs all findings
- Writes papers
- **Never publishes or applies results**

---

## The Three Missing Links

### 1. curiosity_processor Not Called

**Fix:** Add to reflection cycle after line 1549:

```python
# After investigation/surfacing
# Now process ALL questions in feed for remediation
try:
    from src.kloros.orchestration.curiosity_processor import process_curiosity_feed
    processor_result = process_curiosity_feed()
    result["processor_result"] = processor_result
except Exception as e:
    print(f"[reflection] Curiosity processor failed: {e}")
```

### 2. Integration Questions Filtered Out

**Fix:** Boost VOI in IntegrationFlowMonitor (line ~80):

```python
q = CuriosityQuestion(
    value_estimate=0.95,  # HIGH (was 0.90)
    cost=0.20,            # LOW (was 0.30)
    ...
)
```

### 3. Remediation Only Handles Performance

**Fix:** Add to RemediationManager:

```python
def generate_from_integration_question(self, question):
    hypothesis = question.get("hypothesis", "")

    if hypothesis.startswith("ORPHANED_QUEUE_"):
        return self._create_add_consumer_fix(question)
    elif hypothesis.startswith("UNINITIALIZED_"):
        return self._create_null_check_fix(question)
    # ... etc
```

---

## Summary

**Question:** Is she producing actionable fixes?

**Answer:**

**NO.** She's producing:
- ✅ High-quality questions (107 per cycle)
- ✅ Diagnostic investigations (229 total)
- ✅ Log files with findings
- ❌ Zero actual fixes
- ❌ Zero code patches
- ❌ Zero deployments

**Why?**

She has all the pieces:
- ✅ Detection (IntegrationFlowMonitor)
- ✅ Questions (CuriosityCore)
- ✅ Processor (curiosity_processor.py)
- ✅ Fixer (RemediationManager)
- ✅ Patcher (dream/deploy/patcher.py)

But they're **not wired together**. Each piece works in isolation.

**Fix:** 3 lines of code to connect them:
1. Call curiosity_processor from reflection
2. Boost integration question VOI
3. Add integration fix routing to remediation

Then she'd actually fix things.

---

## Status: Research Mode ✅, Action Mode ❌

She's like a PhD student who:
- Writes brilliant papers (questions)
- Runs careful experiments (investigations)
- Logs everything meticulously (229 entries)
- **Never defends thesis or graduates** (no fixes deployed)

The infrastructure is there. The wiring is not.
