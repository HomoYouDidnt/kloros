---
doc_type: capability
capability_id: module.common
status: enabled
last_updated: '2025-11-22T18:32:26.485823'
drift_status: ok
---
# module.common

## Purpose

Provides: utility_functions

Kind: service
## Scope

Documentation: src/common/README.md

Tests: None

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/src/common/__init__.py readable

## Telemetry

Health check: `bash:test -f /home/kloros/src/common/__init__.py`

Cost:
- CPU: 5
- Memory: 256 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
