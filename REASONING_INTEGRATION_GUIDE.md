# Reasoning Coordinator Integration Guide

Making KLoROS a true **Knowledge & Logic-based Reasoning Operating System**

## Overview

Wire `ReasoningCoordinator` into ALL decision-making subsystems to replace heuristics with actual reasoning (ToT, Debate, VOI).

## Quick Integration Pattern

```python
from src.reasoning_coordinator import get_reasoning_coordinator, ReasoningMode

# At module level
coordinator = get_reasoning_coordinator()

# In decision-making functions
def make_decision(context, options):
    # OLD WAY (heuristic):
    # best = max(options, key=lambda x: x.value - x.cost)

    # NEW WAY (reasoning):
    result = coordinator.reason_about_alternatives(
        context="What decision am I making?",
        alternatives=[
            {'name': opt.name, 'value': opt.value, 'cost': opt.cost, 'risk': opt.risk}
            for opt in options
        ],
        mode=ReasoningMode.STANDARD  # or DEEP/CRITICAL for important decisions
    )

    logger.info(f"[reasoning] {result.decision} (confidence: {result.confidence:.2f})")
    for trace in result.reasoning_trace:
        logger.info(f"[reasoning]   {trace}")

    return result.decision, result.confidence
```

## Integration Points

### 1. **Introspection & Self-Reflection** (`kloros_idle_reflection.py`)

**Where**: `_analyze_*` methods that generate insights

**Pattern**:
```python
def _analyze_speech_pipeline(self) -> Dict[str, Any]:
    """Analyze speech system with reasoning."""
    from src.reasoning_coordinator import get_reasoning_coordinator, ReasoningMode

    coordinator = get_reasoning_coordinator()

    # Gather data
    issues = self._detect_speech_issues()

    if issues:
        # OLD: Pick highest priority issue
        # NEW: Reason about which to address first
        alternatives = [
            {
                'name': issue['name'],
                'value': issue.get('impact', 0.5),
                'cost': issue.get('effort', 0.3),
                'risk': issue.get('risk', 0.1)
            }
            for issue in issues
        ]

        result = coordinator.reason_about_alternatives(
            context="Which speech pipeline issue to address first?",
            alternatives=alternatives,
            mode=ReasoningMode.STANDARD
        )

        return {
            'status': 'issues_found',
            'priority_issue': result.decision,
            'confidence': result.confidence,
            'reasoning_trace': result.reasoning_trace
        }
```

### 2. **Alert Prioritization** (`kloros_idle_reflection.py:_surface_insights_to_user`)

**Where**: Deciding which insights to surface to user

**Pattern**:
```python
def _surface_insights_to_user(self, summary):
    """Surface insights with reasoning-based prioritization."""
    from src.reasoning_coordinator import get_reasoning_coordinator

    coordinator = get_reasoning_coordinator()

    # OLD: Filter by confidence threshold
    # NEW: Reason about which insights are most valuable to user

    alternatives = [
        {
            'name': insight.title,
            'value': insight.confidence * insight.get('user_relevance', 0.7),
            'cost': 0.1,  # Cost of user attention
            'risk': 0.05 if insight.confidence > 0.7 else 0.2
        }
        for insight in summary.all_insights
    ]

    result = coordinator.reason_about_alternatives(
        context="Which insights to surface to user?",
        alternatives=alternatives[:10],  # Top 10 candidates
        mode=ReasoningMode.STANDARD
    )

    # Surface top-ranked insights
    logger.info(f"[reflection][reasoning] Surfacing: {result.decision} "
                f"(VOI: {result.voi_score:.3f}, confidence: {result.confidence:.3f})")
```

### 3. **Auto-Approval Safety** (`kloros_idle_reflection.py:_check_auto_approval`)

**Where**: Evaluating if improvement is safe to auto-deploy

**Pattern**:
```python
def _check_auto_approval(self, improvement):
    """Evaluate auto-approval with multi-agent debate."""
    from src.reasoning_coordinator import get_reasoning_coordinator

    coordinator = get_reasoning_coordinator()

    # OLD: Simple if risk < threshold and confidence > threshold
    # NEW: Multi-agent debate on safety

    proposed_decision = {
        'action': f"Auto-deploy {improvement.get('component')} improvement",
        'rationale': improvement.get('description'),
        'confidence': improvement.get('confidence', 0.5),
        'risk': improvement.get('risk_level_numeric', 0.3),
        'risks': [
            'Potential for unintended side effects',
            'No human review',
            'Auto-rollback may not catch all issues'
        ]
    }

    debate_result = coordinator.debate_decision(
        context=f"Should we auto-deploy {improvement.get('component')} fix?",
        proposed_decision=proposed_decision,
        rounds=2  # Two rounds for safety-critical
    )

    verdict = debate_result.get('verdict', {}).get('verdict')
    confidence = debate_result.get('verdict', {}).get('confidence', 0)

    approved = verdict in ['approved', 'conditionally_approved'] and confidence > 0.6

    logger.info(f"[auto_approval][reasoning] {verdict}, confidence: {confidence:.3f}")

    return approved, debate_result
```

### 4. **D-REAM Candidate Selection** (`dream/` module)

**Where**: Choosing which experiment to run next

**Pattern**:
```python
def select_next_candidate(candidates):
    """Select D-REAM candidate with reasoning."""
    from src.reasoning_coordinator import get_reasoning_coordinator, ReasoningMode

    coordinator = get_reasoning_coordinator()

    alternatives = [
        {
            'name': cand['id'],
            'value': cand.get('score', 0.5),
            'cost': cand.get('cost_estimate', 0.3),
            'risk': cand.get('risk', 0.2)
        }
        for cand in candidates
    ]

    result = coordinator.reason_about_alternatives(
        context="Which D-REAM experiment to run next?",
        alternatives=alternatives,
        mode=ReasoningMode.DEEP  # Complex decision
    )

    return result.decision, result.reasoning_trace
```

### 5. **Tool Synthesis Validation** (`tool_synthesis/validator.py`)

**Where**: Deciding if synthesized tool is safe/valid

**Pattern**:
```python
def validate_tool(tool_spec):
    """Validate synthesized tool with reasoning."""
    from src.reasoning_coordinator import get_reasoning_coordinator, ReasoningMode

    coordinator = get_reasoning_coordinator()

    # Propose: Accept tool
    proposed_decision = {
        'action': f"Accept synthesized tool: {tool_spec.name}",
        'rationale': f"Tool meets {len(tool_spec.tests)} test criteria",
        'confidence': tool_spec.validation_score,
        'risk': 0.1 if tool_spec.sandboxed else 0.4,
        'risks': [
            'Untested edge cases',
            'Potential for resource leaks',
            'May conflict with existing tools'
        ] if not tool_spec.comprehensive_tests else []
    }

    debate_result = coordinator.debate_decision(
        context=f"Should we accept tool {tool_spec.name}?",
        proposed_decision=proposed_decision,
        rounds=1
    )

    verdict = debate_result.get('verdict', {}).get('verdict')
    return verdict == 'approved'
```

### 6. **Improvement Proposal Analysis** (`dream/improvement_proposer.py`)

**Where**: Analyzing if detected issue warrants a proposal

**Pattern**:
```python
def should_create_proposal(issue_data):
    """Decide if issue warrants improvement proposal."""
    from src.reasoning_coordinator import get_reasoning_coordinator

    coordinator = get_reasoning_coordinator()

    alternatives = [
        {
            'name': 'create_proposal',
            'value': issue_data.get('severity', 0.5) * issue_data.get('frequency', 0.5),
            'cost': 0.2,  # Cost of proposal processing
            'risk': 0.1
        },
        {
            'name': 'monitor_further',
            'value': 0.3,
            'cost': 0.05,
            'risk': 0.3  # Risk of ignoring real issue
        },
        {
            'name': 'ignore',
            'value': 0.1,
            'cost': 0.0,
            'risk': 0.5  # High risk if actually important
        }
    ]

    result = coordinator.reason_about_alternatives(
        context=f"Should we create proposal for {issue_data.get('component')} issue?",
        alternatives=alternatives,
        mode=ReasoningMode.STANDARD
    )

    return result.decision == 'create_proposal', result
```

## Benefits

### Before (Heuristic-Based):
```python
# Simple threshold checks
if confidence > 0.6 and risk < 0.3:
    return True
```

### After (Reasoning-Based):
```python
# Multi-path exploration, debate, VOI calculation
result = coordinator.reason_about_alternatives(...)

# Get:
# - All alternatives explored
# - VOI-based ranking
# - Confidence from debate
# - Step-by-step trace
# - Recommended action
```

## Testing Integration

```bash
python3 <<'EOF'
from src.reasoning_coordinator import get_reasoning_coordinator, ReasoningMode

coordinator = get_reasoning_coordinator()

# Test decision
result = coordinator.reason_about_alternatives(
    context="Test decision",
    alternatives=[
        {'name': 'option_a', 'value': 0.8, 'cost': 0.3, 'risk': 0.1},
        {'name': 'option_b', 'value': 0.6, 'cost': 0.2, 'risk': 0.05}
    ],
    mode=ReasoningMode.STANDARD
)

print(f"Decision: {result.decision}")
print(f"Confidence: {result.confidence:.3f}")
print("\nReasoning trace:")
for step in result.reasoning_trace:
    print(f"  {step}")
EOF
```

## Rollout Strategy

1. ✅ **Phase 1**: Created ReasoningCoordinator
2. ⏳ **Phase 2**: Wire into Introspection (high-value, low-risk)
3. ⏳ **Phase 3**: Wire into Auto-Approval (safety-critical)
4. ⏳ **Phase 4**: Wire into D-REAM & Tool Synthesis
5. ⏳ **Phase 5**: Wire into Alert System
6. ⏳ **Phase 6**: Replace ALL remaining heuristics

## Key Principle

**Every `if confidence > threshold` should become `coordinator.reason_about_alternatives()`**

This makes KLoROS truly reason with logic, not just check thresholds.

---

## Making the Name Real

**KLoROS = Knowledge & Logic-based Reasoning Operating System**

Now it actually:
- Uses **Knowledge** (evidence, patterns, history)
- Applies **Logic** (ToT, Debate, VOI)
- **Reasons** (explores alternatives, debates, calculates value)
- Is an **Operating System** (reasoning wired throughout)

Not just a clever acronym - a description of the architecture! 🧠
