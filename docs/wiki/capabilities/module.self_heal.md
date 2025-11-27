---
doc_type: capability
capability_id: module.self_heal
status: enabled
last_updated: '2025-11-22T18:32:26.487336'
drift_status: ok
---
# module.self_heal

## Purpose

Provides: processing_engine

Kind: service
## Scope

Documentation: src/self_heal/README.md

Tests: None

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/src/self_heal/__init__.py readable

## Telemetry

Health check: `bash:test -f /home/kloros/src/self_heal/__init__.py`

Cost:
- CPU: 5
- Memory: 256 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
