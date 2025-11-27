---
doc_type: capability
capability_id: network.http_out
status: enabled
last_updated: '2025-11-22T18:32:26.484730'
drift_status: mismatch
---
# network.http_out

## Purpose

Provides: fetch_docs, post_webhook, api_call

Kind: device
## Scope

Documentation: docs/network.md

Tests:
- network_connectivity_test

## Implementations

No module dependencies.

Preconditions:
- network:internet reachable

## Telemetry

Health check: `http:https://api.github.com`

Cost:
- CPU: 2
- Memory: 64 MB
- Risk: medium

## Drift Status

**Status:** MISMATCH

Inconsistencies detected in preconditions or module references.

Details:
- Unknown precondition format: 'network:internet reachable'

