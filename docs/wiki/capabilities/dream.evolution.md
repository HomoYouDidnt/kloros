---
doc_type: capability
capability_id: dream.evolution
status: enabled
last_updated: '2025-11-22T18:32:26.483426'
drift_status: ok
---
# dream.evolution

## Purpose

Provides: optimize_params, self_improve, experiment

Kind: service
## Scope

Documentation: docs/dream.md

Tests:
- dream_cycle_test

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/src/dream/config/dream.yaml readable
- path:/home/kloros/src/dream/dream_domain_service.py readable

## Telemetry

Health check: `python:dream_availability_check`

Cost:
- CPU: 25
- Memory: 2048 MB
- Risk: medium

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
