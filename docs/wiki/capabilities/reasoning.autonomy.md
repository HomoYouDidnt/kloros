---
doc_type: capability
capability_id: reasoning.autonomy
status: enabled
last_updated: '2025-11-22T18:32:26.485169'
drift_status: mismatch
---
# reasoning.autonomy

## Purpose

Provides: propose_improvement, safe_action, self_heal

Kind: reasoning
## Scope

Documentation: docs/autonomy.md

Tests:
- autonomy_level_test

## Implementations

No module dependencies.

Preconditions:
- env:KLR_AUTONOMY_LEVEL>=2
- reasoning.curiosity:ok

## Telemetry

Health check: `env:KLR_AUTONOMY_LEVEL`

Cost:
- CPU: 10
- Memory: 512 MB
- Risk: medium

## Drift Status

**Status:** MISMATCH

Inconsistencies detected in preconditions or module references.

Details:
- Unknown precondition format: 'env:KLR_AUTONOMY_LEVEL>=2'
- Unknown precondition format: 'reasoning.curiosity:ok'

