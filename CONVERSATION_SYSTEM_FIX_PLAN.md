# KLoROS Conversation System - Surgical Fix Plan

**Date:** 2025-11-04
**Status:** Ready for Implementation
**Methodology:** Systematic Debugging (Post-Analysis)
**Foundation:** Complete dataflow analysis + comprehensive system mapping

---

## Executive Summary

Based on **complete system understanding** from two comprehensive analyses:
1. STT_TTS_CONVERSATION_SYSTEMATIC_DEBUGGING.md (architectural issues)
2. KLOROS_CONVERSATION_DATAFLOW_REPORT.md (dataflow mapping)

I'm proposing **5 surgical fixes** that address actual functional issues without disrupting the working autonomy systems.

**Key Decision:** Alert system is **working as designed** with auto-approval enabled. No changes needed.

---

## System Understanding Summary

### What's Working ✅
- **Autonomy**: Auto-approval, self-healing, exception monitoring all operational
- **STT/TTS Pipeline**: Vosk/Whisper hybrid + Piper working correctly
- **Turn Orchestrator**: VAD → STT → Reasoning → TTS pipeline solid
- **Memory Systems**: Both ConversationFlow and MemoryEnhanced functional
- **Consciousness Integration**: Affective state tracking operational
- **Tool Execution**: Synthesis, matching, and execution working
- **LLM Routing**: Model selection and fallback logic sound

### What's Broken ❌
1. **Duplicate State Updates**: ConversationFlow updated TWICE per turn (lines 3603, 3620 + 3909-3912)
2. **Redundant Context Retrieval**: Memory context fetched at TWO layers
3. **Silent Ollama Failures**: No health checks = 60s timeouts
4. **Consciousness Awareness Gap**: Fast-path tools skip consciousness updates
5. **Meta-Cognition Overhead**: Adds 200-500ms latency EVERY turn

---

## Fix Plan (Prioritized)

### Fix #1: Eliminate Duplicate ConversationFlow Updates (HIGH PRIORITY)

**Problem:**
- `_create_reason_function()` calls `ConversationFlow.ingest_user()` at line 3603
- `handle_conversation()` calls it AGAIN at lines 3909-3912
- **Impact:** Duplicate entries in turns deque, incorrect idle detection, state confusion

**Evidence:**
```python
# In _create_reason_function (line 3603):
state, normalized_transcript = self.conversation_flow.ingest_user(transcript)

# In handle_conversation (lines 3909-3912):
if summary.transcript:
    self.conversation_flow.ingest_user(summary.transcript)
self.conversation_flow.ingest_assistant(summary.reply_text)
```

**Root Cause:**
The reason function is called BY the orchestrator, which then redundantly updates conversation flow after the fact.

**Fix:**
Remove the duplicate call in `handle_conversation()`. Keep ONLY the call in `_create_reason_function()` since it needs the normalized transcript.

**Implementation:**
```python
# In kloros_voice.py:handle_conversation (around line 3909-3912)
# REMOVE these lines:
# if summary.transcript:
#     self.conversation_flow.ingest_user(summary.transcript)
# self.conversation_flow.ingest_assistant(summary.reply_text)

# KEEP: Nothing needed here - reason function already handled it
```

**Files Modified:**
- `/home/kloros/src/kloros_voice.py` (remove lines 3909-3912)

**Testing:**
1. Enable debug logging in ConversationFlow.ingest_user()
2. Have 5-turn conversation
3. Verify turns deque has exactly 5 entries, not 10
4. Verify idle detection works correctly

**Risk:** LOW - Only removes duplicate, keeps primary call

---

### Fix #2: Add Ollama Health Checks (HIGH PRIORITY)

**Problem:**
- LLMRouter assumes Ollama services are running
- When service down, user gets 60s timeout with no explanation
- **Impact:** 13 silent failures observed in last 3 days

**Evidence:**
From logs:
```json
{"final_text":"Ollama chat request failed: HTTPConnectionPool(host='127.0.0.1', port=11434): Read timed out. (read timeout=60)"}
```

**Root Cause:**
No health check before HTTP request in `llm_router.py:query_local_llm()`

**Fix:**
Add 2-second health check before each LLM request.

**Implementation:**
```python
# In /home/kloros/src/reasoning/llm_router.py

def check_service_health(self, mode: LLMMode) -> tuple[bool, str]:
    """Check if Ollama service is running and responsive.

    Returns:
        (is_healthy, error_message)
    """
    service = self.get_service(mode)
    try:
        r = requests.get(f"{service.url}/api/tags", timeout=2)
        if r.status_code == 200:
            return (True, "")
        else:
            return (False, f"Ollama {service.name} returned status {r.status_code}")
    except requests.exceptions.Timeout:
        return (False, f"Ollama {service.name} is not responding (timeout)")
    except requests.exceptions.ConnectionError:
        return (False, f"Ollama {service.name} is not running (connection refused)")
    except Exception as e:
        return (False, f"Ollama {service.name} health check failed: {e}")

def query_local_llm(self, prompt, mode, prefer_remote=False, timeout=60, **kwargs):
    """Query local Ollama service with health check."""
    service = self.get_service(mode)

    # NEW: Check health first
    is_healthy, error_msg = self.check_service_health(mode)
    if not is_healthy:
        print(f"[llm_router] {error_msg}")
        return (False, error_msg)

    # Existing request logic...
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        return (True, response.json())
    except requests.exceptions.Timeout:
        return (False, f"LLM request to {service.name} timed out after {timeout}s")
    except requests.exceptions.ConnectionError as e:
        return (False, f"Cannot connect to {service.name}: {e}")
    except Exception as e:
        return (False, f"LLM request failed: {e}")
```

**Files Modified:**
- `/home/kloros/src/reasoning/llm_router.py`

**Testing:**
1. Stop ollama-live: `systemctl stop ollama-live`
2. Ask KLoROS a question
3. **Expected:** Clear error within 2s instead of 60s timeout
4. Start service: `systemctl start ollama-live`
5. Verify recovery works

**Risk:** LOW - Only adds safety check, doesn't change happy path

---

### Fix #3: Consolidate Memory Context Retrieval (MEDIUM PRIORITY)

**Problem:**
- Memory context retrieved at BOTH wrapper layer AND backend layer
- **Impact:** Redundant database queries, inflated prompt tokens

**Evidence:**
```python
# Layer 1: MemoryEnhanced wrapper (integration.py:164-169)
if self.enable_memory:
    context = self.retrieve_context(user_message)

# Layer 2: LocalRagBackend (local_rag_backend.py:1515-1553)
if kloros_instance and hasattr(kloros_instance, 'memory_enhanced'):
    memory_context = kloros_instance.memory_enhanced.retrieve_context(...)
```

**Root Cause:**
Legacy design had context retrieval in wrapper, but backend was enhanced to fetch its own context.

**Fix:**
Remove context retrieval from wrapper layer, keep ONLY in backend where it's actually used.

**Implementation:**
```python
# In /home/kloros/src/kloros_memory/integration.py

# In _memory_enhanced_chat method (around lines 164-169)
# REMOVE this block:
# if self.enable_memory:
#     context = self.retrieve_context(user_message, limit=self.max_context_events)
#     # ... append to prompt

# KEEP: Memory logging, but NOT context retrieval
# Backend will handle context retrieval when it needs it
```

**Files Modified:**
- `/home/kloros/src/kloros_memory/integration.py` (remove context retrieval from wrapper)

**Testing:**
1. Enable memory logging to track retrieval calls
2. Have 10-turn conversation
3. Verify context retrieved ONCE per turn (in backend), not twice
4. Verify response quality unchanged

**Risk:** MEDIUM - Changes memory flow, but backend still has the retrieval logic

---

### Fix #4: Add Consciousness Updates for Fast-Path Tools (LOW PRIORITY)

**Problem:**
- Fast-path tools bypass consciousness updates
- **Impact:** Mood not updated for common queries (status, time, etc.)

**Evidence:**
```python
# In local_rag_backend.py:1254-1342
if matched_key:
    tool_result = tool.func(kloros_instance)
    # ... format with LLM
    return ReasoningResult(reply_text=formatted, ...)
    # RETURNS EARLY - never reaches consciousness updates in _unified_reasoning
```

**Root Cause:**
Fast-path optimization bypasses the full reasoning pipeline.

**Fix:**
Add consciousness updates before early return.

**Implementation:**
```python
# In /home/kloros/src/reasoning/local_rag_backend.py (around line 1330)

# Before returning fast-path result, update consciousness
if kloros_instance:
    try:
        from src.consciousness.integration import process_event, update_consciousness_signals
        process_event(kloros_instance, "tool_execution", metadata={'tool': tool_name, 'fast_path': True})
        update_consciousness_signals(kloros_instance, user_interaction=True, confidence=0.95)
    except Exception as e:
        print(f"[fast-path] Consciousness update failed: {e}")

return ReasoningResult(
    reply_text=formatted,
    sources=[],
    meta={"fast_path": tool_name, "model": fast_path_model}
)
```

**Files Modified:**
- `/home/kloros/src/reasoning/local_rag_backend.py` (add consciousness updates before line 1330)

**Testing:**
1. Query fast-path tools multiple times
2. Check consciousness state reflects tool usage
3. Verify mood updates appropriately

**Risk:** LOW - Only adds missing updates, doesn't change behavior

---

### Fix #5: Make Meta-Cognition Optional or Sampled (LOW PRIORITY)

**Problem:**
- Meta-cognition processes EVERY turn, adding 200-500ms latency
- **Impact:** Noticeable delay for dialogue monitoring that may not be needed every turn

**Evidence:**
```python
# In _unified_reasoning:1705-1711
from src.meta_cognition import process_with_meta_awareness
reply = process_with_meta_awareness(
    kloros_instance=self,
    user_input=transcript,
    response=reply,
    confidence=confidence
)
# Runs on EVERY turn
```

**Root Cause:**
Meta-cognition was designed to run always, but it's heavy.

**Fix Option A (Sampling):**
Process meta-cognition every Nth turn instead of every turn.

**Fix Option B (Config):**
Add environment variable to disable meta-cognition.

**Implementation (Option B - Recommended):**
```python
# In /home/kloros/src/kloros_voice.py:_unified_reasoning (around line 1704)

# Check if meta-cognition is enabled
enable_meta = os.getenv("KLR_ENABLE_META_COGNITION", "1") == "1"

if enable_meta:
    from src.meta_cognition import process_with_meta_awareness
    reply = process_with_meta_awareness(
        kloros_instance=self,
        user_input=transcript,
        response=reply,
        confidence=confidence
    )
```

**Configuration:**
```bash
# In /home/kloros/.kloros_env
# Add this line to disable meta-cognition (saves ~300ms per turn):
# KLR_ENABLE_META_COGNITION=0

# Or keep enabled (default):
KLR_ENABLE_META_COGNITION=1
```

**Files Modified:**
- `/home/kloros/src/kloros_voice.py` (add conditional around line 1705)
- `/home/kloros/.kloros_env` (document new env var)

**Testing:**
1. Benchmark 20 turns with meta-cognition enabled
2. Benchmark 20 turns with meta-cognition disabled
3. Measure latency difference
4. Verify dialogue quality acceptable in both modes

**Risk:** LOW - Purely optional, can be re-enabled if needed

---

## NOT Fixing (Explicitly)

### Alert System Integration
**Reason:** System already has auto-approval enabled. D-REAM improvements deploy autonomously without manual alerts.

**Evidence:**
- `/home/kloros/.kloros/alerts/pending_status.json` shows `pending_count: 0`
- Auto-approval logic operational in `alert_manager.py:116-224`
- Autonomy systems (ExceptionMonitor, CuriosityCore, D-REAM) working correctly

**Decision:** No changes needed. Alert system working as intended for autonomous operation.

### DeepSeek Reformulation
**Reason:** The extra LLM call is intentional to maintain response quality. Regex stripping of `<think>` tags risks removing needed context.

**Decision:** Keep current implementation. Optimize only if latency becomes critical.

### LocalRagBackend Refactoring
**Reason:** While the 2050-line file is complex, it's working correctly. Refactoring is a major architectural change requiring extensive testing.

**Decision:** Defer to future maintenance cycle. Current fixes are surgical, not architectural.

---

## Implementation Order

### Week 1: High Priority Fixes
1. **Day 1:** Fix #1 - Eliminate duplicate ConversationFlow updates
2. **Day 2:** Fix #2 - Add Ollama health checks
3. **Day 3:** Testing and validation of fixes 1-2

### Week 2: Medium Priority Fixes
4. **Day 1-2:** Fix #3 - Consolidate memory context retrieval
5. **Day 3:** Testing and validation of fix 3

### Week 3: Low Priority Enhancements
6. **Day 1:** Fix #4 - Add consciousness updates for fast-path
7. **Day 2:** Fix #5 - Make meta-cognition optional
8. **Day 3:** Final integration testing

---

## Testing Strategy

### Pre-Implementation Baseline
1. Record 20 conversation turns with detailed logging
2. Measure latency at each stage
3. Capture ConversationFlow state snapshots
4. Monitor Ollama service health

### Post-Fix Validation
1. **Fix #1:** Verify turn deque has correct count
2. **Fix #2:** Test Ollama service restart/failure scenarios
3. **Fix #3:** Verify single context retrieval per turn
4. **Fix #4:** Check consciousness state updates
5. **Fix #5:** Benchmark latency with/without meta-cognition

### Regression Testing
1. Multi-turn conversations (5, 10, 20 turns)
2. Tool execution paths
3. Fast-path queries
4. Error handling (STT failures, TTS failures, LLM timeouts)
5. Memory persistence across conversation boundaries

---

## Success Metrics

### Before Fixes
- ❌ Duplicate ConversationFlow updates: 2x per turn
- ❌ Ollama failures: 13 silent timeouts in 3 days
- ❌ Memory context retrievals: 2x per turn
- ❌ Fast-path consciousness: Never updated
- ❌ Meta-cognition: Always enabled (+300ms/turn)

### After Fixes
- ✅ ConversationFlow updates: 1x per turn (50% reduction)
- ✅ Ollama failures: Clear error within 2s (no silent timeouts)
- ✅ Memory context retrievals: 1x per turn (50% reduction)
- ✅ Fast-path consciousness: Always updated
- ✅ Meta-cognition: Optional (0-300ms/turn based on config)

### Expected Performance Improvement
- **Latency:** ~500ms faster per turn (duplicate elimination + optional meta-cognition)
- **Reliability:** 100% clear error messages (no silent failures)
- **Context Quality:** Same or better (no duplicate state confusion)

---

## Risk Assessment

### Low Risk Fixes (1, 2, 4, 5)
- Only remove duplicates or add missing functionality
- Easy rollback: Comment out changes
- No architectural changes

### Medium Risk Fix (3)
- Changes memory context flow
- Requires validation that backend has all needed context
- Rollback: Re-enable wrapper context retrieval

### Mitigation Strategy
1. Implement fixes one at a time
2. Test thoroughly before proceeding to next fix
3. Keep detailed logs of before/after behavior
4. Have rollback plan for each fix

---

## Rollback Plan

### If Fix #1 Breaks Conversation Flow
1. Restore lines 3909-3912 in kloros_voice.py
2. Keep duplicate updates (safe but suboptimal)

### If Fix #2 Causes False Positives
1. Remove health check from llm_router.py
2. Fall back to silent timeout behavior

### If Fix #3 Breaks Context Quality
1. Re-enable context retrieval in integration.py wrapper
2. Accept redundant retrieval

### If Fix #4 Breaks Fast-Path Performance
1. Remove consciousness updates from fast-path
2. Accept mood not updating for common queries

### If Fix #5 Breaks Dialogue Quality
1. Set `KLR_ENABLE_META_COGNITION=1` (re-enable)
2. Accept latency overhead

---

## Post-Implementation Monitoring

### Metrics to Track
1. **Conversation turn latency** (avg, p50, p95, p99)
2. **ConversationFlow deque size** (should match turn count)
3. **Memory context retrieval count** (should be 1x per turn)
4. **Ollama health check failures** (should be logged clearly)
5. **Consciousness update rate** (should be 100% of turns)

### Logging Enhancements
```python
# Add to relevant sections:
print(f"[DEBUG] ConversationFlow turns count: {len(self.conversation_flow.turns)}")
print(f"[DEBUG] Memory context retrieved: {len(context)} events")
print(f"[DEBUG] Ollama health check: {is_healthy}")
print(f"[DEBUG] Consciousness updated: {consciousness_state}")
print(f"[DEBUG] Meta-cognition: {'enabled' if enable_meta else 'disabled'}")
```

---

## Conclusion

This fix plan addresses **actual functional issues** identified through:
1. Systematic debugging framework (4 phases)
2. Complete dataflow analysis (13 integration points)
3. Comprehensive system mapping (529 modules, 122K lines)

**All fixes are surgical** - they target specific issues without disrupting the working autonomy systems. The alert system is explicitly NOT being changed because it's working correctly with auto-approval.

**Implementation can begin immediately** with Fix #1 (duplicate elimination) as it has the lowest risk and highest impact on state consistency.

---

**Status:** ✅ Ready for Implementation
**Next Step:** Begin with Fix #1, test thoroughly, then proceed to Fix #2
