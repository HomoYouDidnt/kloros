# LocalRagBackend Elimination Migration

**Date:** 2025-11-26
**Lines Removed:** 1531
**Status:** COMPLETE

## Summary

Eliminated the monolithic `local_rag_backend.py` (1531 lines) by distributing its functionality to appropriate subsystems and leveraging existing voice services.

## Architecture Change

### Before
```
User Input
    ↓
LocalRagBackend.reply() (monolith)
    ├── Query classification
    ├── LLM generation
    ├── RAG retrieval
    ├── Memory context retrieval
    ├── Tool execution (deprecated)
    ├── XAI tracing
    └── Response generation
    ↓
Voice Output
```

### After
```
User Input
    ↓
VoiceGateway (thin router)
    ↓ VOICE.USER.INPUT
MetaAgentKLoROS (orchestrator)
    ├── Query classification (integrated)
    ├── Memory context retrieval (integrated)
    ├── XAI tracing (integrated)
    │
    ├─→ VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST
    │   ↓
    │   KnowledgeService (RAG)
    │   ↓
    │   VOICE.KNOWLEDGE.RESULTS
    │
    └─→ VOICE.ORCHESTRATOR.LLM.REQUEST
        ↓
        LLMService (Ollama/remote)
        ↓
        VOICE.LLM.RESPONSE
    ↓
VOICE.ORCHESTRATOR.SPEAK
    ↓
TTS Output
```

## Files Modified

### New Functionality Added
- `/home/kloros/src/kloros/mind/consciousness/meta_agent_daemon.py` (+500 lines)
  - Added VOICE.USER.INPUT handler
  - Added query classification integration
  - Added LLMService/KnowledgeService UMN wiring
  - Added episodic memory context retrieval
  - Added XAI tracing integration

### Updated References
- `/home/kloros/src/kloros/interfaces/voice/gateway.py`
  - Set `meta_agent_connected = True`
  - Removed stub response logic
  - Updated documentation

- `/home/kloros/src/reasoning/base.py`
  - Deprecated "rag" backend with warning
  - Falls back to OllamaReasoner

- `/home/kloros/src/dream_lab/cli.py`
  - Updated to use OllamaReasoner instead of LocalRagBackend
  - Added deprecation notes

- `/home/kloros/src/real_evolutionary_integration.py`
  - Commented out LocalRagBackend import (file has other issues)

### Deleted
- `/home/kloros/src/reasoning/local_rag_backend.py` (1531 lines)

## Functionality Distribution

| Feature | New Location |
|---------|--------------|
| Query classification | MetaAgentKLoROS._handle_user_input() |
| LLM generation | LLMService via VOICE.ORCHESTRATOR.LLM.REQUEST |
| RAG retrieval | KnowledgeService via VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST |
| Memory context | MetaAgentKLoROS._get_memory_context() |
| XAI tracing | MetaAgentKLoROS._start_xai_trace(), _finalize_xai_trace() |
| Tool execution | REMOVED (tool system deprecated) |

## Dead Code Eliminated

~450 lines of deprecated tool-related code:
- `_handle_validation_failure()`
- `_is_valid_tool_name()`
- `_infer_tool_name_from_query()`
- `_parse_tool_command()`
- `_check_model_tool_support()`
- `FAST_PATHS = {}`
- `validate_llm_claims()`
- Tool imports and cache variables

## Breaking Changes

1. **"rag" backend deprecated**: Callers using `create_reasoning_backend("rag")` will get a deprecation warning and receive an OllamaReasoner instead.

2. **Direct LocalRagBackend import**: Will fail with ImportError. Use voice services via UMN instead.

3. **Chaos lab RAG tests**: May need updates for UMN architecture. Currently fall back to OllamaReasoner.

## Verification

- All modified files pass Python syntax validation
- No remaining `local_rag_backend` imports in Python files
- VoiceGateway now routes to MetaAgentKLoROS
- Factory function warns on deprecated "rag" backend

## Related Migrations

- 2025-11-26: cognitive_actions_subscriber.py elimination
- 2025-11-25: Voice Services Refactor
- 2025-11-24: Tool System Removal
