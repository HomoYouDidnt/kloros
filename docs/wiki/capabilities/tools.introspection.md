---
doc_type: capability
capability_id: tools.introspection
status: enabled
last_updated: '2025-11-22T18:32:26.483864'
drift_status: ok
---
# tools.introspection

## Purpose

Provides: system_diagnostic, component_status, self_query

Kind: tool
## Scope

Documentation: docs/introspection.md

Tests:
- introspection_registry_test

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/src/introspection_tools.py readable

## Telemetry

Health check: `python:introspection_tool_count`

Cost:
- CPU: 2
- Memory: 64 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
