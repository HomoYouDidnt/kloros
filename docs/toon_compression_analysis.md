# TOON Compression Analysis - Real-World Results

## Summary of Compression Across KLoROS Data Types

### High Compression (40-60%)
**KOSMOS Query Results**: 59% compression (647 → 264 chars)
- **Why**: Uniform array of shallow objects `[{file, similarity, type}, ...]`
- **TOON format**: `results[N]{file,similarity,type}: path/to/file,0.85,python ...`
- **Use case**: Perfect for structured search results, logs, metrics

**TTS Backend Registry**: 40% compression (560 → 338 bytes)
- **Why**: Repeated schema across backend array
- **TOON format**: `backends[4]{name,module,enabled,description}: ...`
- **Use case**: Capability lists, configuration arrays

### Moderate Compression (20-30%)
**Capability Registry (YAML)**: 23% compression (15,408 → 11,746 bytes)
- **Why**: Mixed structure - some uniform arrays, some nested objects
- **TOON format**: Compresses arrays well, preserves nested structure
- **Use case**: Static configuration snapshots

**Capability Graph (Runtime)**: 23% compression (2,371 → 1,811 bytes)
- **Why**: Structured nodes with consistent schema
- **TOON format**: Dependency chains visible, health status clear
- **Use case**: System state snapshots for analysis

### Low Compression (5-10%)
**Investigation Logs**: 7% compression (60MB → 55.96MB)
- **Why**: Deep nesting + long text fields (summaries, evidence)
- **TOON format**: Minimal compression on free-form text
- **Use case**: Historical analysis (still valuable for streaming)

## Key Insights

### TOON Sweet Spot Identified
✓ **Uniform arrays of shallow objects with repeated keys**
✓ **Structured data with consistent schemas**
✓ **Configuration files with array sections**

### Not Ideal For
✗ Deep nesting (3+ levels)
✗ Long text fields (summaries, descriptions)
✗ Variable structure (free-form JSON)

## Architectural Benefits (Beyond Compression)

Even at 7-23% compression, TOON provides:

1. **System Boundaries Explicit**
   - Can see module dependencies at a glance
   - Coupling points visible in message schemas
   - Interface contracts become documentation

2. **Analysis Scalability**
   - Stream 60MB logs without loading into memory
   - Load full capability registry in context (no truncation)
   - Examine system state snapshots completely

3. **Uniform Format**
   - Every component speaks TOON
   - UMN signals standardized
   - Investigation results traceable

## Revised TOON Conversion Strategy

### High Priority (Best ROI)
1. ✓ UMN signals (Tier 1) - COMPLETED
2. ✓ KOSMOS results (Tier 2) - COMPLETED (59% compression)
3. ✓ Investigation findings (Tier 2) - COMPLETED
4. ✓ State export utilities (Tier 3) - COMPLETED
5. **Next**: Monitoring metrics, time-series data (expected 40-50%)

### Medium Priority (Architectural Clarity)
6. Capability registry snapshots (23% compression, high analysis value)
7. Question queues (uniform structure, expected 35-45%)
8. UMN history logs (expected 15-25%)

### Lower Priority (Streaming Only)
9. Investigation history (7% compression, but enables streaming)
10. Exception traces (free-form text)
11. Conversation logs (variable structure)

## Token Efficiency Calculations

### Capability Registry Example
- **JSON**: 15,408 bytes ≈ 4,622 tokens
- **TOON**: 11,746 bytes ≈ 3,523 tokens
- **Savings**: 1,099 tokens (24% of context window freed)
- **Multiplier**: 1.30x more capability data in same context

### KOSMOS Results Example
- **JSON**: 647 chars ≈ 194 tokens
- **TOON**: 264 chars ≈ 79 tokens
- **Savings**: 115 tokens (59% reduction)
- **Multiplier**: 2.45x more search results in same context

### Investigation Logs Example
- **JSON**: 60MB ≈ 240 investigations in 200k tokens
- **TOON**: 55.96MB ≈ 258 investigations in 200k tokens
- **Savings**: 18 more investigations (7% gain)
- **Multiplier**: 1.1x (but enables streaming without memory load)

## Conclusion

TOON standardization delivers value on **two dimensions**:

1. **Compression** (20-60% on structured data)
   - Enables 1.3-2.5x more data in same context
   - Particularly effective on uniform arrays

2. **Architectural Clarity** (regardless of compression)
   - System boundaries explicit
   - Coupling points traceable
   - Uniform wire format across components

**Recommendation**: Continue TOON rollout focusing on structured data (metrics, queues, snapshots) while using JSON fallback for free-form text.

---
*Analysis Date: 2025-11-23*
*Data Sources: capabilities.yaml, capability_graph.py, curiosity_investigations.jsonl, KOSMOS results*
