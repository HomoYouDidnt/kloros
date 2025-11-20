---
name: memory-optimization
description: Systematic approach to diagnosing and resolving memory pressure issues
category: performance
difficulty: intermediate
risk_level: low
auto_executable: true
---

# Memory Optimization

Systematic workflow for diagnosing and resolving memory pressure, swap exhaustion, and resource strain.

## When to Use This Skill

Use when:
- Swap usage > 70%
- Memory usage consistently > 80%
- System experiencing slowdowns due to memory pressure
- Investigation or service threads accumulating

## Risk Assessment

**Risk Level: LOW** - Actions are diagnostic and use built-in throttling mechanisms
**Auto-executable: YES** - Safe to execute autonomously

## The Workflow

### Phase 1: Measure Current State (REQUIRED FIRST)

**IMPORTANT:** Use ONLY these exact action formats. Do not create new action types.

**Action format:**
```json
{
  "action_type": "measure",
  "description": "Record baseline swap, memory, and thread metrics",
  "command": "collect_baseline_metrics",
  "expected_outcome": "Metrics collected automatically by executor"
}
```

All measurement actions use `action_type: "measure"` and are handled automatically.

### Phase 2: Low-Risk Mitigations (SAFE TO AUTO-EXECUTE)

**CRITICAL:** Use EXACTLY these action formats. The executor can ONLY handle these specific action types: measure, mitigate, wait, validate, check, record, collect.

**Action 1: Throttle Investigation Concurrency**
```json
{
  "action_type": "mitigate",
  "description": "Throttle investigation consumer concurrency to reduce memory pressure",
  "command": "reduce_investigation_concurrency",
  "expected_outcome": "Investigation consumer threads reduced, memory pressure decreased"
}
```

**Action 2: Wait for Stabilization**
```json
{
  "action_type": "wait",
  "description": "Wait 60 seconds for system to stabilize after throttling",
  "command": "stabilize_60s",
  "expected_outcome": "System has time to reclaim memory and reduce threads"
}
```

**Action 3: Validate Outcome**
```json
{
  "action_type": "validate",
  "description": "Compare metrics before/after to calculate improvement",
  "command": "compare_metrics",
  "expected_outcome": "Improvement percentage calculated automatically by executor"
}
```

### Phase 3: Outcome Interpretation

The executor will automatically:
1. Compare metrics before/after
2. Calculate improvement percentage
3. Classify as: SUCCESS (>20% improvement), PARTIAL (5-20%), or FAILED (<5%)
4. Record outcome in skill effectiveness database
5. Use this data to inform future attempts

**DO NOT** generate action types like: execute_command, script_or_tool_usage, run, execute, or any other types not listed above.

### Phase 4: Deeper Investigation (REQUIRES APPROVAL)
1. Analyze memory growth patterns
2. Identify specific leak sources
3. Recommend code-level fixes
4. Submit to D-REAM for evolutionary optimization

## Success Criteria

- Swap usage reduced by >20%
- Memory usage reduced by >10%
- Thread count reduced to sustainable level (<300)
- System responsiveness improved

## Examples

<example>
**Problem:** Swap at 99.6% (14GB/14GB), Memory at 58%, 503 threads

**Phase 1: Measure**
- Baseline: swap=14000MB, mem=58%, threads=503
- Top consumer: investigation_consumer (7500 threads accumulated)
- Queue depth: 3050 investigations pending

**Phase 2: Mitigate**
- Action: Emit INVESTIGATION_THROTTLE_REQUEST (concurrency=1)
- Wait: 60 seconds
- New metrics: swap=11800MB, mem=54%, threads=165

**Phase 3: Validate**
- Swap reduction: 15.7% (partial success)
- Memory reduction: 6.9% (minor improvement)
- Thread reduction: 67% (success!)
- **Overall: PARTIAL SUCCESS** - reduced pressure but not resolved

**Phase 4: Next Steps**
- Continue monitoring
- If pressure returns: Investigate why queue keeps growing
- Consider: RAM upgrade, queue depth limits, investigation timeout tuning
</example>

## Autonomous Execution Notes

This skill is **SAFE** for autonomous execution because:
1. All actions use existing throttling mechanisms
2. Changes are temporary and reversible
3. No destructive operations
4. Built-in validation and rollback
5. Metrics collected before/after for learning

**Auto-execution enabled:** KLoROS can execute this skill without human approval.
