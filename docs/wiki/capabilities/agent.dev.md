---
doc_type: capability
capability_id: agent.dev
status: enabled
last_updated: '2025-11-22T18:32:26.484304'
drift_status: ok
---
# agent.dev

## Purpose

Provides: code_execution, safe_sandbox, diff_generation

Kind: tool
## Scope

Documentation: docs/dev_agent.md

Tests:
- dev_sandbox_test

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/src/dev_agent exists
- path:/home/kloros/src/dev_agent/security/policy.yaml readable

## Telemetry

Health check: `python:dev_agent_check`

Cost:
- CPU: 10
- Memory: 512 MB
- Risk: medium

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
