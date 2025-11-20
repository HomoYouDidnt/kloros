# KLoROS Conversation System: Complete Data Flow Analysis

**Report Generated:** 2025-11-04  
**Purpose:** Systematic debugging and integration mapping  
**Scope:** STT Input → TTS Output conversation pipeline

---

## Executive Summary

The KLoROS conversation system is a highly layered architecture with **13 major integration points** between user speech and synthesized response. The system uses a "turn orchestrator" pattern that coordinates VAD, STT, reasoning, and TTS stages while multiple middleware systems observe and modify data in-flight.

**Critical Finding:** The conversation flow has **3 distinct entry points** (`handle_conversation()`, `chat()`, `_unified_reasoning()`) that converge on shared infrastructure, creating potential for state confusion and duplicate processing.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER SPEAKS "KLoROS..."                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1: WAKE WORD DETECTION (kloros_voice.py:listen_for_wake)│
│  - VOSK grammar-based detection                                 │
│  - Fuzzy matching against wake_phrases                          │
│  - Energy gates (RMS/confidence thresholds)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2: HANDLE_CONVERSATION (kloros_voice.py:3644)           │
│  - Multi-turn conversation loop                                 │
│  - Generates wake acknowledgment ("Yes?")                       │
│  - TTS with hardware mic mute to prevent echo                   │
│  - Flushes audio buffers after acknowledgment                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3: AUDIO CAPTURE (kloros_voice.py:3795)                 │
│  - record_until_silence() via VAD                               │
│  - Background queue filler thread (audio_backend.chunks())      │
│  - Echo suppression during TTS playback                         │
│  - Returns raw audio bytes                                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 4: SPEAKER IDENTIFICATION (optional, kloros_voice.py:3812│
│  - speaker_backend.identify_speaker()                           │
│  - Updates operator_id if known speaker                         │
│  - Logs speaker_identified or speaker_unknown events            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 5: TURN ORCHESTRATOR (core/turn.py:run_turn)            │
│  │                                                               │
│  ├─► 5a. VAD STAGE (turn.py:119)                               │
│  │    - detect_voiced_segments() or detect_segments_two_stage()│
│  │    - Extracts primary voice segment                          │
│  │    - Returns empty if no voice detected                      │
│  │                                                               │
│  ├─► 5b. STT STAGE (turn.py:228)                               │
│  │    - stt_backend.transcribe(audio, sample_rate, lang="en")  │
│  │    - Returns SttResult(transcript, confidence, lang)         │
│  │    - Logs stt_done event                                     │
│  │                                                               │
│  ├─► 5c. REASONING STAGE (turn.py:272)                         │
│  │    - Calls reason_fn(transcript)                             │
│  │    - reason_fn = _create_reason_function() wrapper           │
│  │    - XAI tracing start_trace() / complete_trace()            │
│  │                                                               │
│  └─► 5d. TTS STAGE (turn.py:331)                               │
│       - tts_backend.synthesize(reply_text)                      │
│       - Returns TtsResult(audio_path, duration_s, ...)          │
│       - Audio NOT played yet (orchestrator just synthesizes)    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 6: REASON FUNCTION (_create_reason_function:3567)       │
│  - Alert response handling (if active)                          │
│  - Enrollment command checking                                  │
│  - Identity query handling                                      │
│  - Conversation exit detection                                  │
│  - ConversationFlow.ingest_user() for state tracking            │
│  - Routes to _unified_reasoning()                               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 7: UNIFIED REASONING (_unified_reasoning:1642)          │
│  │                                                               │
│  ├─► 7a. CONSCIOUSNESS UPDATE                                  │
│  │    - process_event(self, "user_input", ...)                 │
│  │    - update_consciousness_signals(user_interaction=True)     │
│  │                                                               │
│  ├─► 7b. MEMORY LOGGING (if memory_enhanced)                   │
│  │    - memory_logger.log_user_input(transcript, confidence)   │
│  │                                                               │
│  ├─► 7c. REASONING BACKEND CALL                                │
│  │    - reason_backend.reply(transcript, kloros_instance=self) │
│  │    - Stores sources in _last_reasoning_sources              │
│  │                                                               │
│  ├─► 7d. MIDDLEWARE PIPELINE                                   │
│  │    - filter_response() - tool filtering                     │
│  │    - sanitize_output() - Portal sanitization                │
│  │                                                               │
│  ├─► 7e. CONSCIOUSNESS EXPRESSION                              │
│  │    - process_consciousness_and_express() - adds affect      │
│  │                                                               │
│  ├─► 7f. META-COGNITION                                        │
│  │    - process_with_meta_awareness() - dialogue monitoring    │
│  │    - May emit [META-STREAM] interventions                   │
│  │                                                               │
│  └─► 7g. RESPONSE MEMORY LOGGING                               │
│       - memory_logger.log_llm_response(reply, model)           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 8: REASONING BACKEND (reasoning/local_rag_backend.py)   │
│  │                                                               │
│  ├─► 8a. QUERY CLASSIFICATION (reply:1192)                     │
│  │    - classify_query() - determines RAG strategy             │
│  │    - Types: factual, conversational, nonsense, ambiguous    │
│  │                                                               │
│  ├─► 8b. MODEL ROUTING                                         │
│  │    - get_intent_router().route()                            │
│  │    - Modes: "live", "think", "deep"                         │
│  │    - Selects model + URL based on query complexity          │
│  │                                                               │
│  ├─► 8c. FAST-PATH TOOL CHECK (reply:1231)                     │
│  │    - Matches against FAST_PATHS dict                        │
│  │    - Executes tool immediately                              │
│  │    - Formats via LIVE model + PERSONA_PROMPT                │
│  │    - Returns early (bypasses full RAG pipeline)             │
│  │                                                               │
│  ├─► 8d. CONVERSATION HISTORY RETRIEVAL                        │
│  │    - conversation_logger.get_recent_turns(n=4)              │
│  │    - Used for context-aware classification                  │
│  │                                                               │
│  ├─► 8e. NONSENSE/CONVERSATIONAL HANDLING (reply:1363-1503)   │
│  │    - Minimal prompt with PERSONA_PROMPT                     │
│  │    - Remote LLM first, local Ollama fallback                │
│  │    - No tools/RAG for conversational queries                │
│  │                                                               │
│  ├─► 8f. EPISODIC MEMORY RETRIEVAL (reply:1515-1553)          │
│  │    - conversation_logger.get_recent_turns(n=6) - immediate  │
│  │    - conversation_logger.retrieve_context() - semantic      │
│  │    - Combines recent + relevant memories                    │
│  │    - Injects into prompt as memory_context                  │
│  │                                                               │
│  ├─► 8g. TOOL REGISTRY (reply:1554-1563)                       │
│  │    - IntrospectionToolRegistry()                            │
│  │    - get_tools_description() - text format                  │
│  │    - get_tools_for_ollama_chat() - structured format        │
│  │                                                               │
│  ├─► 8h. RAG RETRIEVAL (reply:1586-1626)                       │
│  │    - embedder(transcript) for query embedding               │
│  │    - rag_instance.retrieve_by_embedding(embedding, top_k)   │
│  │    - Adaptive top_k based on query type                     │
│  │    - Builds prompt with retrieved docs + tools + memory     │
│  │                                                               │
│  ├─► 8i. LLM GENERATION                                        │
│  │    - /api/chat with structured tools (if model supports)    │
│  │    - /api/generate with text tools (fallback)               │
│  │    - Streaming optional (disabled in turn orchestrator)     │
│  │                                                               │
│  ├─► 8j. DEEPSEEK REFORMULATION (if think mode, reply:1633)   │
│  │    - _reformulate_for_tts() strips <think> tags            │
│  │    - Passes reasoning to LIVE model for concise TTS         │
│  │                                                               │
│  ├─► 8k. TOOL EXECUTION (reply:1684-1887)                      │
│  │    - _parse_tool_command() - extracts TOOL: or JSON        │
│  │    - _preprocess_tool_request() - name correction          │
│  │    - PreExecutionValidator.validate_tool_request()          │
│  │    - _handle_validation_failure() if invalid               │
│  │    - _execute_tool_with_params() - actual execution        │
│  │    - Logs to episodic memory                                │
│  │    - Naturalizes structured outputs via style pipeline      │
│  │                                                               │
│  ├─► 8l. STYLE PIPELINE (reply:1936-2013)                      │
│  │    - classify_context() - determines situation              │
│  │    - choose_technique() - selects style method              │
│  │    - apply_technique() - applies transformation             │
│  │    - parrot_guard() - prevents copyright infringement       │
│  │    - Only applies if parrot_guard approves                  │
│  │                                                               │
│  └─► 8m. EPISODIC MEMORY LOGGING (reply:1919-1932)            │
│       - conversation_logger.log_turn(query, response, metadata)│
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 9: CONVERSATION FLOW TRACKING (kloros_voice.py:3909)    │
│  - conversation_flow.ingest_user(transcript)                    │
│  - conversation_flow.ingest_assistant(reply_text)               │
│  - Tracks entities, pronouns, follow-ups                        │
│  - Builds context for next turn                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 10: TTS PLAYBACK (kloros_voice.py:3918-3963)            │
│  - Audio already synthesized by orchestrator                    │
│  - Checks KLR_TTS_MUTE flag for hardware mute                   │
│  - mute_during_playback() context manager (500ms buffer)        │
│  - subprocess.run(self._playback_cmd(audio_path))               │
│  - _post_tts_cooldown_and_flush() after playback               │
│  - _clear_tts_suppress() to re-enable mic                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 11: CONVERSATION CONTINUATION (kloros_voice.py:3968)    │
│  - Check _conversation_exit_requested flag                      │
│  - Check consecutive_no_voice counter                           │
│  - Loop back to STAGE 3 for next turn OR exit                   │
└───────────────────────────┴─────────────────────────────────────┘
```

---

## Integration Point Catalog

### 1. **ConversationFlow** (src/core/conversation_flow.py)
- **What it does:** Multi-turn context tracking with pronoun resolution
- **Data in:** Raw user transcript
- **Data out:** Normalized transcript, conversation state
- **State modified:** 
  - `turns` deque (last 16 turns)
  - `entities` dict (key: value extraction)
  - `slots` dict (task-specific state)
  - `topic_summary` (rolling summary with bullet points)
- **Dependencies:** None (standalone)
- **Initialized:** `kloros_voice.py:570` (main `__init__`)
- **Called from:**
  - `_create_reason_function:3603` - ingest_user()
  - `_create_reason_function:3620` - ingest_assistant()
  - `handle_conversation:3909-3912` - ingest_user/assistant() again
- **Conditional:** Always active

### 2. **MemoryEnhanced** (kloros_memory/integration.py)
- **What it does:** Episodic-semantic memory wrapper around KLoROS
- **Data in:** User transcript, LLM response, confidence
- **Data out:** Context retrieval results, formatted prompts
- **State modified:**
  - MemoryStore (SQLite events + ChromaDB embeddings)
  - RepetitionChecker history
  - TopicTracker keywords
  - Current conversation ID
- **Dependencies:** 
  - MemoryStore, MemoryLogger, EpisodeCondenser, ContextRetriever
  - ChromaDB client, embedder
- **Initialized:** `kloros_voice.py:1002` (`_init_memory_enhancement()`)
- **Called from:**
  - `_unified_reasoning:1670-1677` - log_user_input()
  - `_unified_reasoning:1714-1721` - log_llm_response()
  - Wraps `handle_conversation()` via method injection
- **Conditional:** `if hasattr(self, "memory_enhanced") and self.memory_enhanced.enable_memory`

### 3. **Consciousness** (consciousness/integration.py)
- **What it does:** Affective core + interoception + appraisal
- **Data in:** Event type, metadata, signals (confidence, success, retries)
- **Data out:** Affective state, mood description
- **State modified:**
  - AffectiveCore signals (RAGE, FEAR, etc.)
  - Interoceptor buffer
  - Appraisal weights
- **Dependencies:** IntegratedConsciousness, AffectiveCore
- **Initialized:** `kloros_voice.py:585` (`integrate_consciousness()`)
- **Called from:**
  - `_unified_reasoning:1666-1667` - process_event(), update_consciousness_signals()
  - `_unified_reasoning:1695-1701` - process_consciousness_and_express()
- **Conditional:** `if self.consciousness is not None`

### 4. **Reasoning Backend** (reasoning/local_rag_backend.py)
- **What it does:** RAG + tool synthesis + LLM routing
- **Data in:** Transcript, kloros_instance
- **Data out:** ReasoningResult(reply_text, sources, meta)
- **State modified:**
  - Conversation logger (ChromaDB)
  - Tool registry (synthesized tools)
  - Bandit selector (learning weights)
  - XAI trace
- **Dependencies:**
  - RAG instance, embedder, semantic matcher, tool synthesizer
  - ConversationLogger, AgentFlow, ACE store
- **Initialized:** `kloros_voice.py:1131` (`_init_reasoning_backend()`)
- **Called from:**
  - `_unified_reasoning:1682` - reason_backend.reply()
- **Conditional:** `if self.reason_backend is not None`
- **Wrapped by:** ConversationReasoningAdapter (adaptive reasoning)

### 5. **ConversationReasoningAdapter** (conversation_reasoning.py)
- **What it does:** Wraps reasoning backend with conversation awareness
- **Data in:** Same as wrapped backend
- **Data out:** Same as wrapped backend
- **State modified:** None (delegating wrapper)
- **Dependencies:** Wrapped reasoning backend
- **Initialized:** `kloros_voice.py:1139` (wraps reason_backend)
- **Called from:** Same call sites as reason_backend
- **Conditional:** Always wraps if available

### 6. **LLM Router** (reasoning/llm_router.py)
- **What it does:** Routes queries to live/think/deep models
- **Data in:** Query text, explicit mode
- **Data out:** (model_mode, selected_model, selected_url)
- **State modified:** None (stateless)
- **Dependencies:** models_config
- **Initialized:** Lazily in LocalRagBackend.reply()
- **Called from:**
  - `local_rag_backend.py:1223` - router.route()
- **Conditional:** Always called

### 7. **Tool Registry** (introspection_tools.py)
- **What it does:** Registers and executes system introspection tools
- **Data in:** Tool name, parameters, kloros_instance
- **Data out:** Tool execution result (string)
- **State modified:** None (tools may modify system state)
- **Dependencies:** Individual tool implementations
- **Initialized:** `kloros_voice.py:641`
- **Called from:**
  - `local_rag_backend.py:1560` - get_tools_description()
  - `local_rag_backend.py:1684-1887` - tool execution pipeline
- **Conditional:** Always available

### 8. **Meta-Cognition** (meta_cognition/__init__.py)
- **What it does:** Dialogue quality monitoring + meta-interventions
- **Data in:** User input, response, confidence
- **Data out:** Processed response (same), meta insights (separate stream)
- **State modified:**
  - DialogueMonitor metrics (coherence, repetition, engagement)
  - MetaCognitiveBridge state (turn count, health)
  - ReflectiveSystem (long-term patterns)
- **Dependencies:** DialogueMonitor, MetaCognitiveBridge, embedding_engine
- **Initialized:** `kloros_voice.py:591` (`init_meta_cognition()`)
- **Called from:**
  - `_unified_reasoning:1705-1711` - process_with_meta_awareness()
  - `_simple_chat_fallback:1833-1839` - same function
- **Conditional:** `if hasattr(self, 'meta_bridge') and self.meta_bridge is not None`

### 9. **Turn Orchestrator** (core/turn.py)
- **What it does:** Coordinates VAD → STT → Reason → TTS pipeline
- **Data in:** Audio array, sample_rate, backends, reason_fn
- **Data out:** TurnSummary(transcript, reply_text, tts, vad, timings)
- **State modified:** XAI reasoning trace
- **Dependencies:** SttBackend, TtsBackend, VAD functions, logger
- **Initialized:** N/A (function, not class)
- **Called from:**
  - `handle_conversation:3876` - run_turn()
- **Conditional:** `if run_turn is not None and self.stt_backend is not None`

### 10. **XAI Middleware** (xai/middleware.py)
- **What it does:** Explainability tracing for decision audit
- **Data in:** Query, user_id, mode, uncertainty
- **Data out:** DecisionRecord with evidence, tools, rationale
- **State modified:** Thread-local trace storage
- **Dependencies:** None (standalone)
- **Initialized:** Lazily in LocalRagBackend.reply()
- **Called from:**
  - `local_rag_backend.py:1199` - xai.start_turn()
  - `local_rag_backend.py:1654` - xai.log_tool_call()
  - `local_rag_backend.py:1829` - xai.finalize()
  - `turn.py:278-307` - XAI reasoning trace
- **Conditional:** `if xai_enabled` (exception handling)

### 11. **Middleware Pipeline** (middleware.py)
- **What it does:** Response filtering + Portal sanitization
- **Data in:** Raw LLM response, kloros_instance
- **Data out:** Filtered, sanitized response
- **State modified:** None (stateless)
- **Dependencies:** None
- **Initialized:** N/A (pure functions)
- **Called from:**
  - `_unified_reasoning:1691-1692` - filter_response(), sanitize_output()
- **Conditional:** Always called

### 12. **Style Pipeline** (style/*)
- **What it does:** GLaDOS-style transformations with copyright guard
- **Data in:** Response text, context
- **Data out:** Styled response (if approved by parrot_guard)
- **State modified:** 
  - kloros_instance._style_turn_idx
  - kloros_instance._style_last_styled_turn
  - kloros_instance._style_session_seeded
- **Dependencies:** Corpus index, embedder, technique library
- **Initialized:** Lazily in LocalRagBackend.reply()
- **Called from:**
  - `local_rag_backend.py:1936-2013` - full style pipeline
- **Conditional:** `if response.strip() and not response.startswith("❌")`

### 13. **Audio Backend** (audio/capture.py)
- **What it does:** Audio capture with ring buffer
- **Data in:** N/A (captures from hardware)
- **Data out:** Audio chunks (float32)
- **State modified:** Ring buffer
- **Dependencies:** Hardware audio interface (PulseAudio/ALSA)
- **Initialized:** `kloros_voice.py:614` (`_init_audio_backend()`)
- **Called from:**
  - `handle_conversation:3747` - audio_backend.chunks()
  - Multiple TTS playback points
- **Conditional:** Always active in production

---

## State Mutation Points

### Global State (kloros_voice.py instance attributes)
1. **conversation_history** (list) - Appended in _simple_chat_fallback:1830
2. **operator_id** (str) - Updated in handle_conversation:3822 (speaker ID)
3. **_last_reasoning_sources** (list) - Set in _unified_reasoning:1685
4. **_conversation_exit_requested** (bool) - Set in _detect_conversation_exit()
5. **_style_turn_idx** (int) - Incremented in style pipeline
6. **_style_last_styled_turn** (int) - Updated when style applied
7. **_style_session_seeded** (bool) - Set once per session
8. **last_ollama_context** (list) - Captured from Ollama response for C2C

### ConversationFlow State
1. **turns** (deque) - Appended on every user/assistant message
2. **entities** (dict) - Updated via extract_entities()
3. **slots** (dict) - Updated via set_slot()
4. **topic_summary.bullet_points** (list) - Appended via add_fact()

### Memory System State
1. **MemoryStore (SQLite)** - New events inserted on every turn
2. **ChromaDB collections** - New embeddings added for semantic search
3. **RepetitionChecker.history** (deque) - Appended with each response
4. **TopicTracker.keywords** (dict) - Updated with user/assistant text
5. **current_conversation_id** (str) - Set in _memory_enhanced_handle_conversation

### Consciousness State
1. **AffectiveCore signals** (dict) - Updated via update_consciousness_signals()
2. **Interoceptor buffer** (deque) - Appended with new observations
3. **Appraisal weights** (dict) - Loaded from YAML, modified at runtime

### Meta-Cognition State
1. **DialogueMonitor.turn_history** (deque) - Appended with (user, assistant) pairs
2. **MetaCognitiveBridge.current_state.turn_count** (int) - Incremented
3. **ReflectiveSystem (SQLite)** - New reflections inserted every 5 turns

### Tool Registry State
1. **registry.tools** (dict) - New synthesized tools registered
2. **BanditToolSelector.arm_stats** (dict) - Learning weights updated
3. **SynthesizedToolStorage (disk)** - Persisted tool code

### XAI Trace State (thread-local)
1. **active_traces** (dict) - New trace per turn
2. **DecisionRecord** - Populated with evidence, tools, rationale

---

## Dependency Tree

```
kloros_voice.py
  ├─── ConversationFlow (conversation_flow.py)
  │
  ├─── MemoryEnhanced (kloros_memory/integration.py)
  │    ├─── MemoryStore (storage.py)
  │    ├─── MemoryLogger (logger.py)
  │    ├─── EpisodeCondenser (condenser.py)
  │    ├─── ContextRetriever (retriever.py)
  │    ├─── RepetitionChecker (repetition_prevention.py)
  │    ├─── TopicTracker (topic_tracker.py)
  │    └─── ChromaDB client + embedder
  │
  ├─── Consciousness (consciousness/integration.py)
  │    ├─── IntegratedConsciousness (integrated.py)
  │    ├─── AffectiveCore (phase1_core.py)
  │    ├─── Interoceptor (phase2_interoception.py)
  │    ├─── AppraisalEngine (phase2_appraisal.py)
  │    └─── AffectiveExpressionFilter (expression.py)
  │
  ├─── ReasoningBackend (reasoning/local_rag_backend.py)
  │    ├─── ConversationReasoningAdapter (conversation_reasoning.py)
  │    ├─── RAG instance (simple_rag.py)
  │    ├─── Embedder (sentence_transformers)
  │    ├─── ToolSynthesizer (tool_synthesis/synthesizer.py)
  │    ├─── SemanticToolMatcher (tool_synthesis/semantic_tool_matcher.py)
  │    ├─── BanditToolSelector (kloros/learning/tool_selector.py)
  │    ├─── PreExecutionValidator (tool_synthesis/pre_execution_validator.py)
  │    ├─── ConversationLogger (memory/conversation_logger.py)
  │    ├─── AgentFlowRunner (agentflow/runner.py)
  │    ├─── LLM Router (reasoning/llm_router.py)
  │    ├─── Style Pipeline (style/*)
  │    └─── XAI Middleware (xai/middleware.py)
  │
  ├─── Meta-Cognition (meta_cognition/__init__.py)
  │    ├─── DialogueMonitor (dialogue_monitor.py)
  │    ├─── MetaCognitiveBridge (meta_bridge.py)
  │    └─── ReflectiveSystem (kloros_memory/reflective.py)
  │
  ├─── TurnOrchestrator (core/turn.py)
  │    ├─── VAD functions (audio/vad.py)
  │    ├─── SttBackend (stt/base.py)
  │    ├─── TtsBackend (tts/base.py)
  │    └─── XAI reasoning trace
  │
  ├─── ToolRegistry (introspection_tools.py)
  │    └─── Individual tools (*.py)
  │
  └─── AudioBackend (audio/capture.py)
       └─── PulseAudio/ALSA interface
```

---

## Configuration Control Points

### Environment Variables
1. **KLR_ENABLE_MEMORY** - Enables/disables MemoryEnhanced (default: 1)
2. **KLR_ENABLE_AFFECT** - Enables/disables Consciousness (default: 1)
3. **KLR_ENABLE_STT** - Enables/disables STT backend (default: 0)
4. **KLR_ENABLE_TTS** - Enables/disables TTS backend (default: 1)
5. **KLR_ENABLE_WAKEWORD** - Enables/disables wake word (default: 1)
6. **KLR_ENABLE_SPEAKER_ID** - Enables/disables speaker recognition (default: 0)
7. **KLR_REASON_BACKEND** - Reasoning backend name (default: "mock")
8. **KLR_STT_BACKEND** - STT backend name (default: "mock")
9. **KLR_TTS_BACKEND** - TTS backend name (default: "piper")
10. **KLR_AUDIO_BACKEND** - Audio capture backend (default: "pulseaudio")
11. **KLR_VAD_TYPE** - VAD type: "silero", "two_stage", "dbfs" (default: "silero")
12. **KLR_MAX_CONVERSATION_TURNS** - Turn limit (default: 5)
13. **KLR_CONVERSATION_TIMEOUT** - Turn timeout seconds (default: 15.0)
14. **KLR_TTS_MUTE** - Hardware mic mute during TTS (default: 0)
15. **KLR_HALFDUPLEX_ENABLED** - Echo suppression (default: 1)
16. **KLR_ENABLE_AGENTFLOW** - AgentFlow for structured reasoning (default: 1)
17. **KLR_ENABLE_STREAMING_TTS** - Streaming TTS (default: 0, disabled in turn orchestrator)
18. **KLR_C2C_ENABLED** - Cache-to-cache semantic communication (default: 1)

### Instance Attributes
1. **self.memory_enhanced.enable_memory** - Runtime memory toggle
2. **self.consciousness** - Runtime consciousness toggle (None = disabled)
3. **self.reason_backend** - Runtime reasoning backend (None = fallback)
4. **self.enable_stt** - Runtime STT toggle
5. **self.enable_tts** - Runtime TTS toggle
6. **self.enable_speaker_id** - Runtime speaker ID toggle
7. **self.tts_suppression_enabled** - Runtime echo suppression toggle

---

## Error Propagation Paths

### Critical Paths (Errors Bubble Up)
1. **VAD no voice → TurnSummary(ok=False, reason="no_voice")** 
   - Handle in handle_conversation:3975 - speak("I'm listening..."), continue
2. **STT timeout → TurnSummary(ok=False, reason="timeout")**
   - Handle in handle_conversation:3988 - speak("...took too long..."), exit
3. **Reasoning backend failure → fallback to _simple_chat_fallback()**
   - Logged but graceful in _unified_reasoning:1726-1728
4. **TTS synthesis failure → No audio played, continue**
   - Logged but non-fatal in turn.py:344-346
5. **Tool execution failure → Natural error response**
   - Logged and naturalized in local_rag_backend.py:1871-1873

### Non-Critical Paths (Errors Logged, Execution Continues)
1. **Memory logging failure** - Logged, response proceeds (_unified_reasoning:1676-1677)
2. **Consciousness update failure** - Logged, response proceeds (update_consciousness_signals)
3. **Meta-cognition processing failure** - Logged, original response returned (process_with_meta_awareness:168-173)
4. **Style pipeline failure** - Logged, unstyled response returned (local_rag_backend.py:2011-2013)
5. **XAI tracing failure** - Logged, reasoning continues (local_rag_backend.py:1201-1203)
6. **Speaker ID failure** - Logged, keeps default operator_id (handle_conversation:3833-3835)

---

## Circular Dependencies

### Potential Cycles
1. **kloros_voice ↔ reasoning_backend**
   - Resolved: reason_backend holds weak reference (kloros_instance parameter)
   
2. **reasoning_backend ↔ tool_registry ↔ kloros_voice**
   - Resolved: Tools receive kloros_instance as parameter, not stored

3. **memory_enhanced wraps kloros_voice methods**
   - Resolved: Wrapper pattern with _original_* method storage

4. **conversation_flow ↔ reasoning_backend**
   - Resolved: conversation_flow is standalone, reasoning_backend reads it

### No Circular Dependencies Detected
All integrations use **delegation** or **weak references** (instance parameters).

---

## Conditional Execution Branches

### Memory System
```python
if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
    # Memory operations
```
- **Occurs:** _unified_reasoning:1670, 1714
- **Effect:** Memory logging skipped if disabled
- **State:** No memory events logged, no ChromaDB updates

### Consciousness System
```python
if self.consciousness is not None:
    # Consciousness operations
```
- **Occurs:** _unified_reasoning:1666-1667, 1695-1701
- **Effect:** No affective updates if disabled
- **State:** No mood changes, no expression modulation

### Reasoning Backend
```python
if self.reason_backend is not None:
    # Reasoning pipeline
else:
    # Fallback to simple chat
```
- **Occurs:** _unified_reasoning:1680-1728
- **Effect:** Falls back to direct Ollama call
- **State:** No RAG retrieval, no tool synthesis

### Turn Orchestrator
```python
if run_turn is not None and self.stt_backend is not None and self.enable_stt:
    # Orchestrated turn
else:
    # Legacy VOSK-only path
```
- **Occurs:** handle_conversation:3850-3856
- **Effect:** Different VAD + STT handling
- **State:** No turn tracing, different audio segmentation

### Fast-Path Tools
```python
if normalized_query in FAST_PATHS:
    # Execute tool immediately, bypass RAG
```
- **Occurs:** local_rag_backend.py:1254-1342
- **Effect:** No LLM reasoning for common queries
- **State:** No RAG retrieval, no consciousness updates

### Conversational Queries
```python
if query_type == "conversational":
    # Minimal prompt, no tools/RAG
```
- **Occurs:** local_rag_backend.py:1437-1503
- **Effect:** Simple LLM call with PERSONA_PROMPT only
- **State:** No tool hallucination, no RAG overhead

### Tool Execution Path
```python
if tool_name:
    # Tool validation → execution → naturalization
else:
    # Return RAG response
```
- **Occurs:** local_rag_backend.py:1687-1887
- **Effect:** Different response format
- **State:** Tool result vs. LLM response

---

## Actual vs. Intended Flow

### Intended Design
1. User speaks → Wake word → STT → Reasoning → TTS → Playback
2. Single reasoning path (_unified_reasoning)
3. Linear consciousness → reasoning → expression pipeline

### Actual Implementation
1. **3 Entry Points:**
   - `handle_conversation()` (voice)
   - `chat()` (text)
   - `_unified_reasoning()` (unified)
   
2. **Double Tracking:**
   - ConversationFlow.ingest_user/assistant() called in both:
     - `_create_reason_function:3603, 3620`
     - `handle_conversation:3909-3912`
   - Potential for duplicate state mutations

3. **Memory Wrapping:**
   - MemoryEnhanced wraps `handle_conversation()` AND `chat()`
   - Adds memory logging at different layers
   - Memory context injected multiple times (RAG backend + wrapper)

4. **Consciousness Updates:**
   - Called in `_unified_reasoning()` (high-level)
   - NOT called in orchestrator (low-level)
   - Inconsistent awareness of VA vs. voice input

5. **Tool Execution:**
   - RAG backend handles tool detection + execution
   - Turn orchestrator unaware of tools
   - Acknowledgment ("Let me check...") in RAG, not orchestrator

---

## Key Findings for Debugging

### 1. State Duplication
- **Issue:** ConversationFlow updated twice per turn
- **Location:** `_create_reason_function:3603,3620` + `handle_conversation:3909-3912`
- **Impact:** Duplicate entries in turns deque, incorrect idle detection
- **Fix:** Remove one of the duplicate calls (likely in handle_conversation)

### 2. Memory Context Injection
- **Issue:** Memory context added at multiple layers
- **Locations:**
  - `MemoryEnhanced._memory_enhanced_chat:164-169` (wrapper layer)
  - `local_rag_backend.py:1515-1553` (backend layer)
- **Impact:** Redundant retrieval, inflated prompt tokens
- **Fix:** Consolidate to single retrieval point (backend layer preferred)

### 3. Consciousness Awareness Gap
- **Issue:** Consciousness not updated for fast-path tools
- **Location:** `local_rag_backend.py:1254-1342` returns early
- **Impact:** Mood not updated for common queries
- **Fix:** Add consciousness updates before early return

### 4. Tool Acknowledgment Timing
- **Issue:** Acknowledgment in RAG backend, not orchestrator
- **Location:** `local_rag_backend.py:1779-1796`
- **Impact:** Acknowledgment plays DURING reasoning, not before
- **Fix:** Move acknowledgment to orchestrator or provide callback

### 5. Meta-Cognition Overhead
- **Issue:** Meta-processing on EVERY turn
- **Location:** `_unified_reasoning:1705-1711`
- **Impact:** 200-500ms latency per turn for dialogue monitoring
- **Fix:** Sample meta-processing (e.g., every 3rd turn) or async

### 6. Style Pipeline Conditional
- **Issue:** Style only applied to non-error, English, natural language responses
- **Location:** `local_rag_backend.py:1960`
- **Impact:** Many responses skip style (tools, errors, structured data)
- **Fix:** Broaden style eligibility or document constraints

### 7. XAI Trace Thread-Local
- **Issue:** XAI traces stored in thread-local storage
- **Location:** `xai/middleware.py` (start_trace, get_trace)
- **Impact:** Traces lost if threads change mid-turn
- **Fix:** Pass trace_id through call stack instead of thread-local

### 8. Turn Orchestrator vs. Reasoning Backend Split
- **Issue:** Orchestrator handles VAD/STT/TTS, backend handles reasoning/tools
- **Impact:** No unified view of turn latency breakdown
- **Fix:** Emit detailed timing events at each stage for telemetry

### 9. Optional System Cascade
- **Issue:** If memory disabled, context retrieval skipped, but RAG still tries
- **Location:** Multiple conditional checks (memory, consciousness, etc.)
- **Impact:** Inconsistent behavior based on config
- **Fix:** Consolidate optional system checks in single init validation

### 10. Error Response Naturalization
- **Issue:** Tool errors naturalized in RAG backend, but orchestrator errors are not
- **Location:** `local_rag_backend.py:1871-1873` vs. `handle_conversation:3980-3991`
- **Impact:** Inconsistent error message style (some technical, some natural)
- **Fix:** Centralize error naturalization in middleware

---

## Recommendations for Systematic Debugging

### Phase 1: Eliminate Duplication
1. Remove duplicate ConversationFlow updates in handle_conversation
2. Consolidate memory context retrieval to single layer
3. Add assertion guards to detect double-updates

### Phase 2: Add Tracing
1. Add trace_id to ALL function calls (not just thread-local)
2. Emit timing events at EVERY integration point
3. Create flamegraph-compatible output for latency analysis

### Phase 3: Validate State Consistency
1. Add pre/post assertions in ConversationFlow.ingest_*()
2. Check for idle state changes during active conversation
3. Verify memory logger conversation_id matches flow state

### Phase 4: Simplify Conditional Branches
1. Create single `is_system_enabled()` check per integration
2. Document expected behavior when systems disabled
3. Add integration tests for all disable combinations

### Phase 5: Centralize Error Handling
1. Create unified error naturalization function
2. Route ALL errors through middleware before returning
3. Add error classification (transient vs. fatal)

---

## Appendix: Line Number References

### kloros_voice.py
- `__init__: 177-700` - Main initialization
- `_init_defaults: 701-776` - Safe defaults
- `_init_memory_enhancement: 994-1009` - Memory system init
- `_init_reasoning_backend: 1123-1170` - Reasoning backend init
- `_unified_reasoning: 1642-1730` - Core reasoning method
- `chat: 1732-1758` - Text interface
- `_simple_chat_fallback: 1760-1874` - Fallback reasoning
- `_integrated_chat: 1876-2015` - Memory-integrated chat (unused?)
- `_create_reason_function: 3567-3625` - Reason function wrapper
- `handle_conversation: 3644-4050` - Voice conversation loop

### reasoning/local_rag_backend.py
- `__init__: 40-218` - Backend initialization
- `reply: 1181-2051` - Main reasoning method
- Fast-path: `1231-1342`
- Conversational: `1437-1503`
- Memory retrieval: `1515-1553`
- Tool execution: `1684-1887`
- Style pipeline: `1936-2013`

### core/turn.py
- `run_turn: 54-361` - Turn orchestrator
- VAD stage: `119-180`
- STT stage: `228-269`
- Reasoning stage: `272-328`
- TTS stage: `331-346`

### consciousness/integration.py
- `init_consciousness: 37-95` - Consciousness init
- `update_consciousness_signals: 138-200` - Signal updates
- `process_consciousness_and_express: 203-308` - Expression generation

### meta_cognition/__init__.py
- `init_meta_cognition: 28-82` - Meta-cognition init
- `process_with_meta_awareness: 85-173` - Meta-processing

### kloros_memory/integration.py
- `__init__: 33-82` - Memory wrapper init
- `_wrap_kloros_methods: 84-101` - Method injection
- `_memory_enhanced_handle_conversation: 119-147` - Conversation wrapping
- `_memory_enhanced_chat: 148-233` - Chat wrapping

---

## End of Report

This document provides a complete map of the KLoROS conversation system's data flow from STT input to TTS output, including all integration points, state mutations, dependencies, and conditional execution paths. Use this as a reference for systematic debugging and to understand exactly how data flows through the system before making any changes.
