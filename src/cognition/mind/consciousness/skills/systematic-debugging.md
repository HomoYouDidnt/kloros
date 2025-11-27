---
name: systematic-debugging
description: Four-phase framework for debugging any issue systematically
category: debugging
difficulty: intermediate
---

# Systematic Debugging

A four-phase framework that ensures understanding before attempting solutions.

## When to Use This Skill

Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes.

## The Four Phases

### Phase 1: Root Cause Investigation
1. Reproduce the issue reliably
2. Gather all error messages and stack traces
3. Identify what changed (git diff, recent deployments)
4. Trace execution flow backward from failure point
5. DO NOT propose fixes yet - only gather evidence

### Phase 2: Pattern Analysis
1. Check if this issue has happened before
2. Search logs for similar errors
3. Identify commonalities across failures
4. Document the pattern clearly

### Phase 3: Hypothesis Testing
1. Form specific, testable hypotheses about root cause
2. Design minimal experiments to test each hypothesis
3. Execute experiments one at a time
4. Record results objectively

### Phase 4: Implementation
1. ONLY after confirming root cause
2. Implement minimal fix
3. Verify fix resolves original issue
4. Ensure no regressions introduced
5. Document what was learned

## Red Flags

If you catch yourself thinking:
- "Let me try this fix and see what happens" → STOP. Return to Phase 1.
- "This looks similar to another issue" → Document the pattern in Phase 2.
- "I think I know what's wrong" → Test your hypothesis in Phase 3 first.

## Examples

<example>
Issue: "Swap usage at 99.6% causing system slowdown"

Phase 1 (Investigation):
- Check current swap usage: 12.25GB / 12.3GB
- Identify top memory consumers: `ps aux --sort=-%mem | head -20`
- Review recent process spawns in logs
- Check if memory leak or legitimate usage spike

Phase 2 (Pattern Analysis):
- Check historical swap usage trends
- Correlate with investigation queue depth
- Identify if pattern repeats daily/weekly

Phase 3 (Hypothesis Testing):
- Hypothesis: Investigation consumer spawning too many threads
- Test: Monitor thread count vs swap usage correlation
- Hypothesis: Memory leak in specific component
- Test: Track memory growth over time for each process

Phase 4 (Implementation):
- Once root cause confirmed, implement targeted fix
- If investigation threads: Reduce max_concurrent_investigations
- If memory leak: Fix specific leak site
- Validate swap usage decreases after fix
</example>

## Key Principles

1. Evidence before assertions - always
2. One hypothesis at a time
3. Minimal, targeted fixes
4. Verify success objectively
