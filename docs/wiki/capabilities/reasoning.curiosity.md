---
doc_type: capability
capability_id: reasoning.curiosity
status: enabled
last_updated: '2025-11-22T18:32:26.484949'
drift_status: mismatch
---
# reasoning.curiosity

## Purpose

Provides: generate_questions, propose_experiments, self_directed_learning

Kind: reasoning
## Scope

Documentation: docs/curiosity.md

Tests:
- curiosity_question_generation_test

## Implementations

No module dependencies.

Preconditions:
- env:KLR_ENABLE_CURIOSITY=1
- tools.introspection:ok

## Telemetry

Health check: `env:KLR_ENABLE_CURIOSITY`

Cost:
- CPU: 5
- Memory: 256 MB
- Risk: low

## Drift Status

**Status:** MISMATCH

Inconsistencies detected in preconditions or module references.

Details:
- Unknown precondition format: 'env:KLR_ENABLE_CURIOSITY=1'
- Unknown precondition format: 'tools.introspection:ok'

