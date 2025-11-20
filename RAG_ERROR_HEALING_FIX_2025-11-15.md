# RAG Error Healing Fix - November 15, 2025

## Problem Reported

User reported that KLoROS didn't react to a failure during STT<>TTS testing. Investigation revealed a RAG processing error:

```
RAG processing failed: matmul: Input operand 1 has a mismatch in its core dimension 0,
with gufunc signature (n?,k),(k,m?)->(n?,m?) (size 768 is different from 384)
```

**Issue**: RAG error occurred but no heal event was emitted, preventing KLoROS from self-healing.

## Root Cause

In `src/reasoning/local_rag_backend.py` lines 2174-2194, there was an exception handler that:
1. ✅ Caught RAG exceptions
2. ✅ Returned user-friendly error message
3. ❌ **Did NOT emit a heal event**

This meant KLoROS would encounter the error, tell the user about it, but not trigger any self-healing investigation or curiosity question generation.

## Fix Implemented

### 1. Added `emit_rag_error()` Function
**File**: `src/self_heal/adapters/kloros_rag.py`

Added new function following the same pattern as `emit_synth_timeout()` and `emit_quota_exceeded()`:

```python
def emit_rag_error(heal_bus, query: str, error: Exception):
    """Emit event when RAG processing fails with an error.

    Args:
        heal_bus: HealBus instance (or None if not initialized)
        query: Query that triggered RAG processing
        error: Exception that occurred during RAG processing
    """
    error_type = type(error).__name__
    error_msg = str(error)

    if not heal_bus:
        return

    event = mk_event(
        source="rag",
        kind="processing_error",
        severity="error",
        query=query,
        error_type=error_type,
        error_message=error_msg
    )

    heal_bus.emit(event)
```

### 2. Imported Function in RAG Backend
**File**: `src/reasoning/local_rag_backend.py`

Updated import statement:
```python
try:
    from src.self_heal.adapters.kloros_rag import emit_synth_timeout, emit_rag_error
except ImportError:
    emit_synth_timeout = None
    emit_rag_error = None
```

### 3. Wired Into Exception Handler
**File**: `src/reasoning/local_rag_backend.py` (lines 2174-2194)

Added heal event emission in exception handler:
```python
except Exception as e:
    # Finalize XAI trace with error
    if xai_enabled:
        xai_record = xai.finalize(...)
        self._log_xai_trace(xai_record)

    # Emit heal event for self-healing  ← NEW
    if emit_rag_error and self.heal_bus:  ← NEW
        emit_rag_error(self.heal_bus, transcript, e)  ← NEW

    # Fallback for any errors
    return ReasoningResult(
        reply_text=f"RAG processing failed: {str(e)}",
        sources=[],
        meta={"backend": "local_rag", "error": str(e)},
    )
```

## Expected Behavior After Fix

When RAG processing fails:

1. **User Experience**: No change - still gets error message "RAG processing failed: ..."
2. **Self-Healing**: NEW - Heal event emitted with:
   - source: "rag"
   - kind: "processing_error"
   - error_type: Exception class name (e.g., "ValueError", "AttributeError")
   - error_message: Full error details
   - query: User's query that triggered the error

3. **Investigation**: NEW - investigation-consumer service will:
   - Receive `Q_INCIDENT` signal
   - Launch code analysis investigation
   - Generate curiosity question about the RAG error
   - Potentially propose fixes autonomously

## Testing

### Verification Steps

1. Trigger the same RAG error (e.g., embedding dimension mismatch)
2. Check journalctl for heal event emission:
   ```bash
   sudo journalctl -u kloros.service | grep "emit_rag_error"
   ```
3. Verify investigation-consumer receives event:
   ```bash
   sudo journalctl -u klr-investigation-consumer.service | grep "Q_INCIDENT\|processing_error"
   ```
4. Check curiosity feed for generated question:
   ```bash
   cat /home/kloros/.kloros/curiosity_feed.json | jq '.questions[] | select(.capability_key | contains("rag"))'
   ```

### Specific Error Being Fixed

The user encountered an embedding dimension mismatch:
- **Error**: `matmul: Input operand 1 has a mismatch in its core dimension 0 (size 768 is different from 384)`
- **Likely Cause**: Model configuration mismatch - one component using 384-dim embeddings, another using 768-dim
- **Investigation Path**: KLoROS should now autonomously investigate which models/components are using mismatched embedding dimensions

## Files Modified

1. **src/self_heal/adapters/kloros_rag.py** - Added emit_rag_error() function
2. **src/reasoning/local_rag_backend.py** - Imported and wired emit_rag_error() into exception handler

All files: kloros:kloros ownership, 660 permissions

## Impact

**Before Fix**:
- RAG errors: Silent failures (no self-healing)
- User sees error message but KLoROS doesn't investigate
- Same errors could recur without any learning

**After Fix**:
- RAG errors: Self-healing enabled
- Heal events emitted → Investigations triggered → Questions generated → Fixes proposed
- System learns from errors and can prevent recurrence

## Related Work

This fix follows the same pattern as other heal event emitters:
- `emit_synth_timeout()` - For tool synthesis timeouts (src/self_heal/adapters/kloros_rag.py:7-31)
- `emit_quota_exceeded()` - For quota/rate limit errors (src/self_heal/adapters/kloros_rag.py:34-56)

All three use the same architecture:
1. Adapter function in self_heal/adapters/
2. Import in relevant backend
3. Emit on error condition
4. HealBus propagates to investigation-consumer
5. Curiosity system generates questions

## Deployment

Applied: November 15, 2025, 22:13 EST
Service restarted: kloros.service
Status: Active (running)

## Next Steps

1. Monitor for RAG errors in production
2. Verify heal events are emitted correctly
3. Review generated curiosity questions for quality
4. Potentially add specific RAG error types:
   - `rag.embedding_mismatch` for dimension errors
   - `rag.model_unavailable` for missing models
   - `rag.retrieval_timeout` for slow searches
