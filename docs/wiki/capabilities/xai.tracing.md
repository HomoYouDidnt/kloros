---
doc_type: capability
capability_id: xai.tracing
status: enabled
last_updated: '2025-11-22T18:32:26.484515'
drift_status: ok
---
# xai.tracing

## Purpose

Provides: explain_decision, log_reasoning, trace_causality

Kind: service
## Scope

Documentation: docs/xai.md

Tests:
- xai_trace_test

## Implementations

No module dependencies.

Preconditions:
- path:/var/log/kloros/structured.jsonl writable

## Telemetry

Health check: `bash:test -w /var/log/kloros/structured.jsonl`

Cost:
- CPU: 3
- Memory: 128 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
