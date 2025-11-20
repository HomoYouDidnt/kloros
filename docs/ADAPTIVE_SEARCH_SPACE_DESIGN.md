# Adaptive Search Space Design

**Date:** October 21, 2025
**Status:** Design Document
**Priority:** Phase 2 Enhancement

## Problem Statement

Current D-REAM experiments use **static search spaces** defined in YAML. This has limitations:

1. **Exploration vs Exploitation Trade-off**: Large search spaces take many evaluations to explore, but small spaces may miss optimal configurations
2. **Resource Waste**: Testing extreme parameter values when moderate values work well
3. **No Progressive Refinement**: Can't zoom into promising regions automatically
4. **Manual Tuning Required**: Human must expand/contract search space based on results

## Proposed Solution: Variable Search Space with Incremental Limits

### Core Concept

Search space **expands dynamically** based on:
- Fitness convergence patterns
- Exploration progress (coverage metrics)
- Resource budgets remaining
- Safety constraint violations

### Architecture Example

```yaml
experiments:
  - name: tool_evolution
    search_space:
      adaptive: true

      threshold:
        initial: [0.01, 0.02, 0.05]           # Start narrow
        expansion_rules:
          - trigger: plateau                   # No improvement for N gens
            action: expand_bounds
            new_range: [0.001, 0.15]
          - trigger: high_fitness_at_edge      # Best at boundary
            action: extend_edge
            factor: 1.5
          - trigger: convergence
            action: refine_granularity
            subdivide: 2

        safety_limits:
          absolute_min: 0.0001
          absolute_max: 1.0
          max_values: 20
```

### Progressive Refinement Strategies

#### Strategy 1: Coarse-to-Fine
- Generation 1-2: Wide sampling [0.01, 0.05, 0.1]
- Generation 3-4: Add midpoints [0.015, 0.02, 0.03, ...]
- Generation 5-6: Fine-tune around best [0.018, 0.019, 0.021, ...]

#### Strategy 2: Multi-Resolution Grid
- Phase 1 (Exploration): Logarithmic spacing
- Phase 2 (Refinement): Linear spacing around best
- Phase 3 (Exploitation): Dense sampling in top 10% fitness region

## Implementation Plan

### Phase 1: Infrastructure (Week 1-2)
- Add `AdaptiveSearchSpaceManager` class
- Implement trigger detection logic
- Add search space mutation operators
- Create safety constraint validators

### Phase 2: Basic Triggers (Week 3)
- Plateau detection
- Boundary extension
- Coverage metrics

### Phase 3: Advanced Strategies (Week 4-5)
- Multi-resolution grids
- Fitness landscape analysis
- Region abandonment logic

## Safety Considerations

1. **Absolute Bounds**: Never allow parameters outside safe ranges
2. **Explosion Prevention**: Cap total search space size
3. **Regression Testing**: Periodically re-test baseline
4. **Human Approval**: Flag major expansions for review

## Example: Tool Evolution Progression

```
Epoch 1-5:   Static space, 1,152 combinations
  → Plateau detected, expand thresholds

Epoch 6-10:  Expanded space, 2,304 combinations
  → Best at threshold=0.015, window=50
  → Refine around this region

Epoch 11-15: Focused space, 576 combinations
  → High fitness (0.85+) in threshold=[0.01, 0.02]
  → Switch to exploitation mode

Epoch 16-20: Dense sampling, 1,024 combinations
  → Converged to threshold=0.0165, window=45
  → Trigger LLM mutation engine for code evolution
```

## Future Extensions

1. **Meta-Learning**: Learn expansion strategies from past experiments
2. **Transfer Learning**: Apply patterns to new experiments
3. **Multi-Objective Regions**: Different granularity per fitness dimension
4. **Bayesian Optimization**: Use GP models to suggest regions

---

**Status:** Design phase
**Next Steps:** Prototype `AdaptiveSearchSpaceManager`
**Estimated Effort:** 3-4 weeks
