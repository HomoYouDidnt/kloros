---
doc_type: capability
capability_id: tools.synthesis
status: enabled
last_updated: '2025-11-22T18:32:26.483645'
drift_status: mismatch
---
# tools.synthesis

## Purpose

Provides: create_tool, evolve_tool, validate_tool

Kind: service
## Scope

Documentation: docs/tool_synthesis.md

Tests:
- tool_synthesis_test

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/.kloros/synthesized_tools/tools.db rw
- llm.ollama:ok

## Telemetry

Health check: `python:tool_synthesis_quota_check`

Cost:
- CPU: 30
- Memory: 1024 MB
- Risk: medium

## Drift Status

**Status:** MISMATCH

Inconsistencies detected in preconditions or module references.

Details:
- Unknown precondition format: 'llm.ollama:ok'

