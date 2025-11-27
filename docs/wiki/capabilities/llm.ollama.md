---
doc_type: capability
capability_id: llm.ollama
status: enabled
last_updated: '2025-11-22T18:32:26.483209'
drift_status: ok
---
# llm.ollama

## Purpose

Provides: generate_response, reasoning, planning

Kind: service
## Scope

Documentation: docs/llm.md

Tests:
- ollama_generate_test

## Implementations

No module dependencies.

Preconditions:
- http:http://127.0.0.1:11434/api/tags reachable

## Telemetry

Health check: `http:http://127.0.0.1:11434/api/tags`

Cost:
- CPU: 50
- Memory: 8192 MB
- Risk: medium

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
