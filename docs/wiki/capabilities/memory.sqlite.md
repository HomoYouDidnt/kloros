---
doc_type: capability
capability_id: memory.sqlite
status: enabled
last_updated: '2025-11-22T18:32:26.482045'
drift_status: ok
---
# memory.sqlite

## Purpose

Provides: kv_write, kv_read, events_log

Kind: storage
## Scope

Documentation: docs/memory.md

Tests:
- sqlite_quickcheck
- wal_checkpoint

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/.kloros/memory.db rw

## Telemetry

Health check: `python:pragma_quick_check`

Cost:
- CPU: 1
- Memory: 32 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
