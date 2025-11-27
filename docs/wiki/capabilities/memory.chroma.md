---
doc_type: capability
capability_id: memory.chroma
status: enabled
last_updated: '2025-11-22T18:32:26.482277'
drift_status: missing_module
---
# memory.chroma

## Purpose

Provides: vector_search, semantic_memory, episodic_recall

Kind: storage
## Scope

Documentation: docs/memory.md

Tests:
- chroma_embedding_test
- chroma_query_test

## Implementations

Referenced modules:

### chromadb (NOT FOUND)

Preconditions:
- path:/home/kloros/.kloros/chroma_data rw
- module:chromadb importable

## Telemetry

Health check: `python:chroma_collection_count`

Cost:
- CPU: 5
- Memory: 512 MB
- Risk: low

## Drift Status

**Status:** MISSING_MODULE

One or more required modules are not found in the index.

Details:
- Module 'chromadb' referenced but not found in index

