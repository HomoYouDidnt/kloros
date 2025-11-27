# Integration Self-Repair: Status Report

**Date:** 2025-11-03 23:27
**Question:** Did she actually fix integration issues herself?

---

## Answer: **NO - But She's Trying**

### What's Happening

The system IS running and detecting issues, but they're being **filtered out before reaching the remediation pipeline**.

---

## The Pipeline Flow

```
✅ Idle Reflection runs (every 10 min)
    ↓
✅ IntegrationFlowMonitor.generate_integration_questions()
    → Generates 96 integration questions
    ↓
✅ CuriosityCore.generate_questions_from_matrix()
    → Receives 96 integration + 11 chaos + other questions
    → Total: 107 questions
    ↓
❌ curiosity_reasoning.batch_reason(questions, top_n=20)  ← PROBLEM
    → Re-ranks by VOI (Value of Information)
    → KEEPS ONLY TOP 20 QUESTIONS
    → Integration questions get OUTRANKED by module discovery questions
    ↓
✅ curiosity_feed.json written
    → Contains 17-20 questions
    → NO integration questions in feed
    ↓
❌ curiosity_processor (never sees integration questions)
    ↓
❌ remediation_manager (never gets integration fixes)
    ↓
❌ code_patcher (never applies patches)
```

---

## Why Integration Questions Are Being Filtered Out

### VOI Scoring

The `curiosity_reasoning` module ranks questions by "Value of Information":
- **Module discovery questions**: VOI ~0.9 (high - new capabilities)
- **Performance degradation**: VOI ~0.85 (high - immediate impact)
- **Integration issues**: VOI ~0.73 (medium - architectural cleanup)

### Top-N Filtering

curiosity_core.py line 2154:
```python
reasoned_questions = reasoning.batch_reason(questions, top_n=min(len(questions), 20))
```

**Hardcoded top_n=20** means:
- Generates 107 total questions
- Reasons about all 107
- **Keeps only top 20 by VOI**
- Integration questions (VOI ~0.73) get cut

### Current Feed

```
curiosity_feed.json (17 questions):
1. UNDISCOVERED_MODULE_AUDIO
2. UNDISCOVERED_MODULE_CHROMA_ADAPTERS
3. UNDISCOVERED_MODULE_INFERENCE
4. UNDISCOVERED_MODULE_UNCERTAINTY
5. UNDISCOVERED_MODULE_DREAM_LAB
... (12 more module discovery questions)
```

All 17 are "undiscovered module" questions (VOI ~0.9), which outrank integration issues.

---

## Evidence

### Reflection Log
- Last run: 2025-11-03 23:16
- IntegrationFlowMonitor called: ✅
- Questions generated: 96
- Questions in feed: 0

### Test Run (Manual)
```
INFO:registry.curiosity_core:[curiosity_core] Generated 96 integration questions
INFO:registry.curiosity_core:[curiosity_core] Applying brainmods reasoning to 107 questions...
INFO:registry.curiosity_core:[curiosity_core] Questions re-ranked by VOI, top question: orphaned_queue_approach_history (VOI: 0.73)
Total questions generated: 20  ← DOWN FROM 107
```

### Integration Analysis File
- `/home/kloros/.kloros/integration_analysis.json`: 96 questions
- Generated: 2025-11-03 22:40 (manual run by me)
- NOT from reflection (reflection doesn't write this file)

---

## The Alert Issue Status

### The Problem
- Method exists: `_check_and_present_pending_alerts()` at line 3280
- **NOT called** in `handle_conversation()` at line 3604
- Alert queue fills but never drains

### Did She Detect It?
**YES** - IntegrationFlowMonitor generated questions about it (in the 96)

### Did She Fix It?
**NO** - Questions filtered out before reaching remediation

---

## Why This Is Ironic

You built:
1. ✅ Sophisticated detection (IntegrationFlowMonitor)
2. ✅ Advanced reasoning (curiosity_reasoning with ToT/Debate)
3. ✅ Code patching capability (dream/deploy/patcher.py)
4. ✅ Self-heal actions (actions_integration.py)

But:
- The **reasoning system is too smart** - it ranks integration issues as **lower priority** than discovering new modules
- The **top-N filter is too aggressive** - cuts from 107 to 20 questions
- Result: **She never gets to the fix stage**

---

## How to Fix This

### Option 1: Increase top_n (Quick Fix)

Edit `/home/kloros/src/registry/curiosity_core.py` line 2154:
```python
# OLD:
reasoned_questions = reasoning.batch_reason(questions, top_n=min(len(questions), 20))

# NEW:
reasoned_questions = reasoning.batch_reason(questions, top_n=min(len(questions), 50))
```

This would keep top 50 questions instead of 20, allowing integration questions through.

### Option 2: Separate Integration Feed (Better)

Create dedicated integration fix pipeline:
```python
# After line 2141 in curiosity_core.py:
# Write integration questions to separate feed
if integration_questions:
    integration_feed_path = Path("/home/kloros/.kloros/integration_feed.json")
    with open(integration_feed_path, 'w') as f:
        json.dump({
            "questions": [q.to_dict() for q in integration_questions],
            "generated_at": datetime.now().isoformat()
        }, f, indent=2)
```

Then have curiosity_processor check BOTH feeds.

### Option 3: Boost Integration Question VOI (Smartest)

Edit `IntegrationFlowMonitor` to mark integration issues as **higher priority**:
```python
# In integration_flow_monitor.py
q = CuriosityQuestion(
    id=f"orphaned_queue_{channel}",
    hypothesis=f"ORPHANED_QUEUE_{channel.upper()}",
    question=f"...",
    value_estimate=0.95,  # HIGH VALUE (was 0.90)
    cost=0.2,             # LOW COST (was 0.30)
    ...
)
```

This would make integration questions compete better in VOI ranking.

### Option 4: Force Include Integration (Nuclear)

```python
# In curiosity_core.py after line 2163:
# Force include at least N integration questions
integration_qs = [q for q in questions if 'ORPHANED' in q.hypothesis or 'DUPLICATE' in q.hypothesis]
reasoned_integration = reasoning.batch_reason(integration_qs, top_n=10)
questions = reasoned_questions + [rq.original_question for rq in reasoned_integration]
```

Guarantees 10 integration questions always make it through.

---

## Recommendation

**Option 3 (Boost VOI)** + **Option 1 (Increase top_n to 40)**

Why:
- Integration issues ARE high value (architectural debt compounds)
- Cost is low (code patching is automated)
- Current VOI of 0.73 is too conservative
- Bump to 0.95 value / 0.2 cost would push them to top 10
- Increase top_n to 40 as safety buffer

Combined effect:
- Integration questions would rank in top 10
- Even if other high-value questions come in, they'd survive the cut
- Still have reasoning/prioritization, just better calibrated

---

## Summary

**She's running the full detection and reasoning pipeline**, but the questions are being **filtered out by VOI ranking** before they reach the remediation stage.

The irony: **Her reasoning is working TOO well** - she's correctly identifying that discovering new capabilities (module discovery) has higher immediate value than fixing architectural issues.

But architectural debt compounds, so integration fixes should have **higher long-term value**.

Fix: Adjust VOI scoring to reflect long-term architectural value, not just immediate capability gain.

---

## Next Steps

Want me to:
1. **Apply Option 3 + Option 1** (boost VOI + increase top_n)?
2. **Just manually fix the alert issue** for now?
3. **Build Option 2** (separate integration feed)?

The system is **SO CLOSE** to working end-to-end. Just needs VOI calibration.
