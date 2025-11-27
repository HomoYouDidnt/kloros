---
doc_type: capability
capability_id: rag.retrieval
status: enabled
last_updated: '2025-11-22T18:32:26.482507'
drift_status: missing_module
---
# rag.retrieval

## Purpose

Provides: context_retrieval, document_search, semantic_qa

Kind: service
## Scope

Documentation: docs/rag.md

Tests:
- rag_retrieval_test
- rag_embedding_test

## Implementations

Referenced modules:

### sentence_transformers (NOT FOUND)

Preconditions:
- path:/home/kloros/rag_data/rag_store.npz readable
- module:sentence_transformers importable

## Telemetry

Health check: `python:rag_document_count`

Cost:
- CPU: 10
- Memory: 1024 MB
- Risk: low

## Drift Status

**Status:** MISSING_MODULE

One or more required modules are not found in the index.

Details:
- Module 'sentence_transformers' referenced but not found in index

