# KLoROS Memory System - Operational Guide

## Overview
KLoROS employs a hybrid memory architecture combining episodic memory (SQLite) and semantic memory (Qdrant) for conversation recall, context retrieval, and self-reflection.

## Architecture Components

### 1. Episodic Memory (SQLite)
Location: /home/kloros/.kloros/memory.db

Schema:
- events: Individual interactions (wake detection, user input, responses, TTS output)
- episodes: Grouped conversations with time-based segmentation
- episode_summaries: LLM-generated abstracts with importance scoring

Capabilities:
- Event logging with timestamps and categorization
- Episode grouping (time-gap and token-based segmentation)
- Importance scoring (0.0-1.0 scale for prioritization)
- Retention management (30-day default with configurable cleanup)

Current Stats (as of 2025-10-12):
- Events: ~12,693
- Episodes: 283
- Summaries: 280

### 2. Semantic Memory (Qdrant)
Deployment: Docker container (localhost:6333)
Container: kloros-qdrant
Storage: Persistent volume mapped to /qdrant/storage

Collections:
- kloros_memory: Main collection for episodic and semantic embeddings
- Additional collections for specialized use cases

Embedder: nomic-ai/nomic-embed-text-v1.5 (768-dimensional, truncated to 384)
Distance Metric: Cosine similarity
Index: HNSW (Hierarchical Navigable Small World)

Architecture:
- Server mode for concurrent access (no file locking issues)
- Docker-based deployment for isolation and reliability
- Persistent volume for data durability
- Configuration via /home/kloros/config/models.toml

## Memory Retrieval

### Retrieval Fusion Strategy

KLoROS uses multi-factor scoring for context retrieval:

final_score = alpha × semantic_similarity + beta × recency_boost(timestamp) + gamma × importance

Where:
- semantic_similarity: normalized cosine similarity (0..1)
- recency_boost(ts) = exp(-(now - ts) / tau)
  - tau ≈ 3-7 days for conversations
  - tau ≈ 14-45 days for documentation
- importance: user/system-assigned (0.0-1.0)

Default weights: alpha=0.5, beta=0.3, gamma=0.2

### Retrieving Context

To retrieve relevant memories:
1. Recent turns (last 6) for immediate continuity
2. Semantic matches (top 3-5) for broader context
3. Time-windowed retrieval (24-72 hours default)

## Memory Maintenance

### Housekeeping Operations

The housekeeping service performs:
1. Clean old events: Beyond 30-day retention
2. Condense episodes: Compress uncondensed memory episodes
3. Vacuum database: Reclaim space in memory.db
4. Generate stats: Memory system health metrics
5. Validate integrity: Check for orphaned/broken data

Execute via tool: run_housekeeping

### Health Monitoring

Key metrics to monitor:
- Orphaned events (not in episodes): Should be <20%
- NULL conversation_ids: Normal for system events
- Episodes without summaries: Run condensation if >5%

## Integration Points

### RAG System
Memory context is injected into RAG queries with recent turns and semantic matches.

### D-REAM Evolution
Self-reflection events feed evolution:
- Performance metrics guide optimization
- Conversation patterns inform improvements
- Error analyses trigger adaptations

### Tool Execution
Tool results are logged with metadata for future retrieval.

## Troubleshooting

Issue: High orphaned event count
Fix: Adjust time-gap threshold in episode consolidation

Issue: Qdrant query slow
Fix: Batch upserts, prune old entries, use time-window filters

Issue: Memory.db locked errors
Fix: Ensure WAL mode enabled

Issue: Irrelevant semantic retrievals
Fix: Verify embedder consistency, add importance scoring, tighten distance threshold

Issue: Qdrant server not responding
Fix: Check Docker container status (docker ps | grep qdrant), restart if needed (docker restart kloros-qdrant)

Issue: Connection refused to localhost:6333
Fix: Verify Qdrant server is running, check Docker network configuration

## Best Practices

1. Always retrieve recent + semantic: Combine temporal and semantic context
2. Log with rich metadata: Include tool names, durations, query types
3. Set importance scores: Pin critical interactions (1.0 for major decisions)
4. Regular housekeeping: Run cleanup weekly or when DB exceeds 50k events
5. Monitor orphaned events: High percentage (>80%) indicates consolidation issues

## Configuration

Environment variables:
- KLR_MEMORY_RETENTION_DAYS=30
- KLR_EPISODE_GAP_SECONDS=300
- KLR_QDRANT_URL=http://localhost:6333 (or configured in models.toml)
- KLR_VECTOR_BACKEND=qdrant
- KLR_VECTOR_COLLECTION=kloros_memory

Configuration file: /home/kloros/config/models.toml
```toml
[vector_store]
backend = "qdrant"
server_url = "http://localhost:6333"
collection_name = "kloros_memory"
distance_metric = "cosine"
```

## Migration from ChromaDB

ChromaDB was fully migrated to Qdrant on 2025-11-17. The migration included:
- All vector embeddings transferred to Qdrant server
- Docker-based deployment for improved reliability
- Server mode for concurrent access without file locking
- Better memory usage and performance
- HNSW indexing for faster similarity search

Benefits of Qdrant over ChromaDB:
- No dimension locking issues
- Lower memory usage with mmap and quantization
- Better stability (no corruption issues)
- Concurrent access support via server mode
- Production-grade deployment with Docker

Last updated: 2025-11-17 by Claude (claude-sonnet-4-5-20250929)
