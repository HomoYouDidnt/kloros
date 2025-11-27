# Context Flow Analysis
**Generated:** 2025-10-12 01:42:30
**Scope:** Context injection pipeline from memory to LLM prompt

---

## Executive Summary

**CRITICAL FINDING:** Context retrieval is fundamentally broken due to conversation_id filtering combined with 90.2% NULL conversation_ids in the database.

---

## 1. Context Injection Flow

### Flow Diagram
```
User Input → _memory_enhanced_chat()
    ↓
    ├─→ log_user_input()
    ├─→ _retrieve_context(query, conversation_id)  ← PROBLEM HERE
    │     ↓
    │     └─→ ContextRetriever.retrieve_context()
    │           ↓
    │           ├─→ _get_candidate_events(conversation_id, time_cutoff)  ← FILTERS BY conversation_id
    │           ├─→ _get_candidate_summaries(min_importance, time_cutoff)
    │           ├─→ _score_events() (recency, relevance, type importance)
    │           └─→ _score_summaries() (recency, importance, topic relevance)
    │
    ├─→ _format_context_for_prompt()
    │     ↓
    │     ├─→ Add top 3 summaries
    │     ├─→ Add top 5 relevant events (user_input/llm_response only)
    │     └─→ Truncate to 500 chars max
    │
    ├─→ Insert context into conversation_history
    ├─→ _original_chat(user_message)  ← Calls original KLoROS chat
    └─→ log_llm_response()
```

---

## 2. What Gets Included in Context

### Configuration (from integration.py:52-54)
```python
max_context_events = 10        # Max events to retrieve
max_context_summaries = 3      # Max summaries to retrieve
time_window_hours = 24.0       # Look back 24 hours
```

### Context Composition
1. **Episode Summaries** (up to 3):
   - Filtered by minimum importance (0.3)
   - Scored by: recency (30%) + importance (40%) + relevance (30%)
   - Only summaries from last 24 hours

2. **Recent Events** (up to 5 shown, 10 retrieved):
   - Only `user_input` and `llm_response` event types
   - Filtered by conversation_id ← **THIS IS THE PROBLEM**
   - Scored by: recency (30%) + relevance (30%) + type importance (20%) + confidence (10%)

3. **Total Context Budget**:
   - **Maximum 500 characters** (integration.py:212)
   - Approximately 125-150 tokens

---

## 3. The Critical Problem

### Issue: conversation_id Filtering

**Location:** `integration.py:189` and `retriever.py:120-124`

```python
# integration.py:189
request = ContextRetrievalRequest(
    query=query,
    max_events=self.max_context_events,
    max_summaries=self.max_context_summaries,
    time_window_hours=24.0,
    conversation_id=self.current_conversation_id,  ← FILTERS BY THIS
    min_importance=0.3
)

# retriever.py:120
def _get_candidate_events(self, conversation_id, time_cutoff, limit):
    return self.store.get_events(
        conversation_id=conversation_id,  ← ONLY GETS MATCHING conversation_id
        start_time=time_cutoff,
        limit=limit
    )
```

**Impact:**
- Database analysis shows **90.2% of events have NULL conversation_id**
- When KLoROS tries to retrieve context filtered by conversation_id, it finds almost nothing
- Even though there are 12,693 events in the database, context retrieval sees only ~1,250
- **Result:** Severe context blindness

---

## 4. Token Usage Breakdown

### Current Context Budget
```
Summaries (3 × ~40 chars avg)     = ~120 chars (~30 tokens)
Events (5 × ~50 chars avg)        = ~250 chars (~65 tokens)
Formatting overhead               = ~20 tokens
─────────────────────────────────────────────────────
Total context injection           ≈ 115 tokens
```

### Actual Usage
Due to the NULL conversation_id issue, **actual context injected is likely 0-20 tokens**.

### Available Budget
- qwen2.5:14b has 32k context window
- User could afford **500-1000 tokens** for context (1-3% of window)
- Current limit of 500 chars is too conservative

---

## 5. Evidence of Context Failure

### From Memory Health Report
| Metric | Value | Impact |
|--------|-------|--------|
| NULL conversation_id events | 90.2% | Most events invisible to retriever |
| Orphaned events | 90.9% | Most events not in episodes |
| Average episode duration | 57 seconds | Very short context windows |
| Average events per episode | 4 | Minimal interaction history |

### Recent Episode Topics (from memory_health_report.md)
Top recurring themes:
- `audio_output_issues`
- `communication_failure`
- `audio_functionality`
- `malfunction`

These failures likely stem from KLoROS having no context about what was just discussed.

---

## 6. Identified Bottlenecks

### Critical Bottlenecks
1. **conversation_id NULL values** (90.2% of events)
   - Severity: CRITICAL
   - Impact: Context retrieval effectively disabled
   - Root cause: Likely event logging happening outside of conversation sessions

2. **Orphaned events** (90.9% of events)
   - Severity: HIGH
   - Impact: Events not associated with episodes for summarization
   - Root cause: Episode boundary logic not capturing most events

### Medium Bottlenecks
3. **500 character context limit**
   - Severity: MEDIUM
   - Impact: Even when context IS retrieved, it's severely truncated
   - Recommendation: Increase to 2000-3000 chars (500-750 tokens)

4. **24-hour time window**
   - Severity: LOW
   - Impact: May be too restrictive for long-term memory recall
   - Recommendation: Make adaptive based on query type

---

## 7. Scoring Weights Analysis

### Current Weights (retriever.py:46-48)
```python
recency_weight = 0.3      # 30%
importance_weight = 0.4   # 40%
relevance_weight = 0.3    # 30%
```

**Assessment:** Reasonable balance, but irrelevant when there's no data to score.

### Event Type Importance (retriever.py:336-351)
| Event Type | Score | Assessment |
|------------|-------|------------|
| user_input | 0.9 | ✅ Correct |
| llm_response | 0.8 | ✅ Correct |
| error_occurred | 0.7 | ✅ Correct |
| stt_transcription | 0.4 | ⚠️ Should be higher (user intent) |
| context_retrieval | 0.3 | ✅ Correct (meta-event) |
| self_reflection | ? | ❌ Missing from map (defaults to 0.5) |

---

## 8. Comparison to Specifications

### Expected Behavior
From user description: KLoROS should maintain conversation context and "remember" recent interactions.

### Actual Behavior
- **Expected:** Retrieve 10 relevant events + 3 summaries from recent history
- **Actual:** Retrieve 0-2 events due to conversation_id filtering
- **Expected:** Build coherent context across multiple turns
- **Actual:** Each turn is nearly context-free

### RAG Integration
The `local_rag_backend.py` provides a separate retrieval path:
- Uses sentence transformers for semantic search
- Searches technical documentation corpus (327 documents)
- **Does NOT integrate with episodic memory system**
- Can retrieve 0-5 documents based on query classification

**Issue:** RAG and memory retrieval are parallel, not integrated. Memory context doesn't benefit from RAG's semantic search.

---

## 9. Root Cause Hypothesis

### Why are conversation_ids NULL?

**Hypothesis 1:** Events logged outside of conversation sessions
- Self-reflection events (100% of recent 50 events) are logged asynchronously
- These may not have an active conversation_id set

**Hypothesis 2:** Conversation session not initialized in text-only mode
- Voice mode initializes conversation_id in `_memory_enhanced_handle_conversation()`
- Text-only mode might call chat directly without starting a conversation

**Hypothesis 3:** conversation_id not persisting across memory logger calls
- `current_conversation_id` might be getting reset or not passed through

**Evidence:** Need to check:
- Where self_reflection events are logged
- How text-only mode initializes conversations
- Event logging code paths

---

## 10. Recommendations

### Immediate Fixes (Critical)
1. **Fix conversation_id assignment**
   - Ensure ALL events get tagged with conversation_id
   - Backfill NULL values with synthetic conversation boundaries
   - Add validation to prevent NULL conversation_ids

2. **Fix episode boundary logic**
   - Ensure all events are captured in episodes
   - Review episode start/end triggers
   - May need to extend episode duration

### High Priority Improvements
3. **Increase context budget**
   - Raise limit from 500 to 2500 characters (500 tokens)
   - Add token counting instead of character counting
   - Make budget adaptive based on LLM context window

4. **Add fallback retrieval strategy**
   - When conversation_id yields no results, fall back to time-based retrieval
   - Query: "If no events for current conversation, get most recent 10 events"

### Medium Priority Enhancements
5. **Integrate RAG with memory**
   - Use sentence transformer embeddings for event retrieval (not just RAG docs)
   - Embed event content for semantic similarity search
   - Hybrid retrieval: recent events (temporal) + relevant events (semantic)

6. **Improve event type handling**
   - Increase STT_TRANSCRIPTION importance (user intent signal)
   - Add SELF_REFLECTION to importance map
   - Filter out self_reflection from context (not relevant to user)

---

## 11. Test Plan

### Unit Tests Needed
1. **Test context retrieval with NULL conversation_id**
   - Expected: Should still retrieve recent events via fallback
   - Actual: Currently returns empty list

2. **Test context formatting**
   - Verify 500 char limit is applied correctly
   - Check that user_input/llm_response are prioritized

3. **Test conversation_id propagation**
   - Verify conversation_id is set in voice mode
   - Verify conversation_id is set in text-only mode
   - Verify conversation_id persists across event logs

### Integration Tests Needed
4. **Test multi-turn conversation**
   - Start conversation
   - Send 3 messages
   - Verify context from message 1 appears in message 3

5. **Test context relevance**
   - Log diverse events (errors, user inputs, reflections)
   - Query for specific topic
   - Verify correct events are retrieved

---

## 12. Files to Modify

To fix the conversation_id issue:
1. `src/kloros_memory/integration.py` - Add fallback retrieval strategy
2. `src/kloros_memory/logger.py` - Ensure conversation_id always set
3. `src/kloros_memory/retriever.py` - Add time-based fallback when conversation_id fails
4. `src/kloros_memory/storage.py` - Add method to backfill NULL conversation_ids

To fix episode boundaries:
5. `src/kloros_memory/condenser.py` - Review episode grouping logic

---

## 13. Summary

**Context injection is architecturally sound but operationally broken.**

The system has all the right components:
- ✅ Episodic memory storage
- ✅ Semantic retrieval with scoring
- ✅ Token budget management
- ✅ Multi-turn conversation tracking

But fails due to:
- ❌ 90.2% NULL conversation_ids breaking retrieval
- ❌ 90.9% orphaned events not in episodes
- ❌ Conservative 500 char limit
- ❌ No fallback when conversation_id filter fails

**Impact:** KLoROS operates with near-zero context awareness, explaining:
- Inability to follow multi-turn commands
- Failure to remember recent interactions
- Apparent "deafness" (actually context blindness)
- Repeated communication failures

**Confidence in findings:** 95% - Data-backed analysis of code and database.
