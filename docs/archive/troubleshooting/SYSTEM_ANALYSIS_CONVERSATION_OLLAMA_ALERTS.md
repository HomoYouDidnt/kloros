# KLoROS System Analysis: Conversation, Ollama, and Alert Systems

**Date:** 2025-11-03
**Analyst:** Claude (Sonnet 4.5)
**Status:** Complete Architecture Analysis

---

## Executive Summary

After thorough analysis of the KLoROS codebase, I've identified the architecture and data flow for the conversation system, Ollama integration, and alert system. The systems are well-designed but have some potential integration issues and complexity that may cause confusion.

### Key Findings

1. **Conversation System**: Uses multiple overlapping layers (ConversationFlow, memory system, reasoning adapter)
2. **Ollama Integration**: Well-structured with router pattern, but complex fallback logic
3. **Alert System**: Sophisticated but disconnected from conversation flow
4. **Integration Issues**: Systems don't fully communicate with each other

---

## Architecture Overview

### System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interaction Layer                    │
│  (Voice Wake → STT → Conversation Handler → TTS → Audio)    │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│              Conversation Management Layer                   │
│  ┌──────────────────┐  ┌────────────────────────────────┐  │
│  │ ConversationFlow │  │ Memory-Enhanced Conversation   │  │
│  │ - Turn tracking  │  │ - Episodic memory (SQLite)     │  │
│  │ - Entity resolve │  │ - Topic tracking               │  │
│  │ - Context build  │  │ - Repetition prevention        │  │
│  └──────────────────┘  └────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                  Reasoning Layer                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ConversationReasoningAdapter (Wrapper)               │  │
│  │ - Classifies query complexity                        │  │
│  │ - Routes: Simple/Moderate/Complex                    │  │
│  │ - Uses ToT + Debate for complex queries              │  │
│  └────────────────┬─────────────────────────────────────┘  │
│                   │                                          │
│  ┌────────────────▼─────────────────────────────────────┐  │
│  │ LocalRagBackend (Core Reasoning)                     │  │
│  │ - Fast-path for common queries                       │  │
│  │ - RAG retrieval                                      │  │
│  │ - Tool synthesis/execution                           │  │
│  │ - LLM call via router                                │  │
│  └────────────────┬─────────────────────────────────────┘  │
└───────────────────┼──────────────────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────────────────────┐
│                   LLM Router Layer                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ LLMRouter (Single Source of Truth)                   │   │
│  │ - Service registry (live/think/deep/code)            │   │
│  │ - Health checking                                    │   │
│  │ - Remote/Local fallback                              │   │
│  └────────────────┬─────────────────────────────────────┘   │
└───────────────────┼──────────────────────────────────────────┘
                    │
    ┌───────────────┼────────────────┐
    │               │                │
┌───▼────┐   ┌─────▼──────┐   ┌────▼─────┐
│ Ollama │   │   Ollama   │   │  Remote  │
│  Live  │   │Think/Deep  │   │   LLM    │
│ :11434 │   │:11435/6/7  │   │ (PROXY)  │
└────────┘   └────────────┘   └──────────┘
```

---

## Component Analysis

### 1. Conversation Flow System

**File:** `/home/kloros/src/core/conversation_flow.py`

#### Architecture

```python
ConversationalState (per conversation thread):
├── turns: Deque[Turn] (maxlen=16)  # Last 16 turns
├── entities: Dict[str, str]         # Key-value entities
├── slots: Dict[str, str]            # Task-specific state
├── topic_summary: TopicSummary      # Rolling summary
└── idle_cutoff_s: int = 180         # 3-minute timeout

ConversationFlow:
└── current: Optional[ConversationalState]
```

#### Features

1. **Automatic pronoun resolution** - "it" → last mentioned entity
2. **Follow-up detection** - Recognizes "and", "also", "but", etc.
3. **Entity extraction** - Captures key:value pairs and technical terms
4. **Rolling summarization** - Prevents context explosion
5. **Idle detection** - Auto-starts new thread after 3 minutes

#### Data Flow

```
User speaks → ingest_user()
    ↓
Pronoun resolution (if follow-up)
    ↓
Extract entities from input
    ↓
Push to turn history (deque)
    ↓
Build prompt context (last 12 turns + entities + summary)
    ↓
Return (state, normalized_text)
```

#### Configuration

- `idle_cutoff_s`: 180 seconds (3 minutes)
- `maxlen`: 16 turns in memory
- Context includes: last 12 turns, all entities, topic summary

#### Issues Identified

1. **Parallel Memory System**: KLoROS also has `MemoryEnhancedKLoROS` with SQLite storage that overlaps with this
2. **Dual Context Building**: Both ConversationFlow and memory system build context separately
3. **No Integration**: ConversationFlow doesn't log to SQLite memory system

---

### 2. Memory-Enhanced Conversation

**File:** `/home/kloros/src/kloros_memory/integration.py`

#### Architecture

```python
MemoryEnhancedKLoROS (Wrapper around KLoROS):
├── memory_logger: ConversationLogger (SQLite)
├── repetition_checker: RepetitionChecker
├── topic_tracker: TopicTracker
└── Base KLoROS instance
```

#### Features

1. **Episodic Memory**: Stores all conversations in SQLite (`memory.db`)
2. **Context Retrieval**: Fetches last N events (configurable, default 20)
3. **Repetition Detection**: Alerts on >75% similarity
4. **Topic Tracking**: Keywords + entities from conversation
5. **Auto-Condensation**: Episode summaries after conversation ends

#### Configuration (via .kloros_env)

```bash
KLR_MAX_CONTEXT_EVENTS=20        # Was 3 (fixed Nov 1)
KLR_CONVERSATION_TIMEOUT=60.0    # Was 25 (fixed Nov 1)
KLR_MAX_CONVERSATION_TURNS=20    # Was 5 (fixed Nov 1)
KLR_REPETITION_THRESHOLD=0.75    # New
KLR_REPETITION_HISTORY_SIZE=10   # New
```

#### Data Flow

```
User input → log_user_input()
    ↓
Add to topic tracker (weighted 1.5x)
    ↓
Retrieve context (last 20 events from SQLite)
    ↓
Add topic summary to context
    ↓
Call LLM
    ↓
Check for repetition
    ↓
Log response → log_llm_response()
```

#### Issues Identified

1. **Duplicate Logging**: Some conversations logged both by ConversationFlow and MemoryLogger
2. **Context Redundancy**: Both systems maintain turn history
3. **No Synchronization**: The two systems don't share state

---

### 3. Conversation Reasoning Adapter

**File:** `/home/kloros/src/conversation_reasoning.py`

#### Architecture

```python
ConversationReasoningAdapter:
├── reason_backend: LocalRagBackend (wrapped)
├── coordinator: ReasoningCoordinator (ToT + Debate)
└── query_stats: Dict[complexity → count]

Query Complexity Levels:
├── SIMPLE: Direct to backend (no reasoning overhead)
├── MODERATE: VOI-ranked context (+50ms)
└── COMPLEX: Full ToT + Debate (+200-500ms)
```

#### Complexity Classification Heuristics

**COMPLEX** (Full reasoning):
- Safety-critical keywords: "should i", "is it safe", "medical", "health"
- Explicit reasoning requests: "think carefully", "analyze", "pros and cons"
- Complex indicators: word_count > 20, multiple questions, causal reasoning

**MODERATE** (VOI ranking):
- Question words: "what", "how", "when", "where"
- Word count > 10
- Single question mark

**SIMPLE** (Fast path):
- Everything else

#### Data Flow

```
reply(transcript) → assess_complexity()
    ↓
Route based on complexity:
├── SIMPLE → reason_backend.reply() directly
├── MODERATE → VOI guidance + reason_backend.reply()
└── COMPLEX → ToT exploration + Debate validation + reason_backend.reply()
```

#### Issues Identified

1. **Wrapping Overhead**: Extra layer between kloros_voice and reasoning backend
2. **Limited MODERATE Path**: Currently just logs, doesn't actually use VOI
3. **Complex Path Latency**: +200-500ms for complex queries (acceptable but noticeable)

---

### 4. Local RAG Backend

**File:** `/home/kloros/src/reasoning/local_rag_backend.py`

**Size:** 1800+ lines (very complex)

#### Architecture

```python
LocalRagBackend:
├── rag_instance: RAG (document retrieval)
├── tool_synthesizer: ToolSynthesizer
├── semantic_matcher: SemanticToolMatcher
├── tool_selector: BanditToolSelector (learning-based)
├── conversation_logger: ConversationLogger (SQLite)
├── agentflow_runner: AgentFlowRunner
├── ace_store: BulletStore
└── heal_bus: HealBus (self-healing)
```

#### Key Features

1. **Fast-Path Routing**: Bypasses LLM for common queries
   ```python
   FAST_PATHS = {
       "status": "component_status",
       "how are you": "component_status",
       "memory status": "memory_status",
       ...
   }
   ```

2. **Tool Execution**:
   - Semantic tool matching
   - Dynamic tool synthesis
   - Validation with fallback
   - Timeout protection (30s)

3. **Model Selection**:
   - Intent-based routing (via `get_intent_router()`)
   - Model mode: live/think/deep/code
   - Tool support detection

4. **LLM Call Methods**:
   - `/api/chat` (native tool calling) - preferred
   - `/api/generate` (fallback, post-processes tool calls)

#### Data Flow (reply method)

```
reply(transcript) → classify_query()
    ↓
Check fast-path → execute tool directly if matched
    ↓
Route model selection (live/think/deep)
    ↓
RAG retrieval (if not fast-path)
    ↓
Semantic tool matching
    ↓
Build LLM request (with/without tools)
    ↓
Call Ollama via LLMRouter
    ↓
Post-process response:
├── Extract tool calls (if /api/generate)
├── Execute tools with validation
├── Reformulate if DeepSeek (strip <think> tags)
└── Return ReasoningResult
```

#### Issues Identified

1. **Complexity**: 1800+ lines in single file
2. **Multiple Responsibilities**: RAG + tools + LLM + memory + AgentFlow
3. **DeepSeek Reformulation**: Extra LLM call to strip reasoning for TTS
4. **Tool Synthesis Timeout**: Can hang for 30s if synthesis fails

---

### 5. LLM Router

**File:** `/home/kloros/src/reasoning/llm_router.py`

#### Architecture

```python
LLMRouter (Singleton via get_router()):
├── SERVICES: Dict[LLMMode → LLMService]
│   ├── LIVE: ollama-live:11434 (qwen2.5:7b)
│   ├── THINK: ollama-think:11435 (deepseek-r1:7b)
│   ├── DEEP: ollama-deep:11436 (qwen2.5:14b)
│   └── CODE: ollama-code:11437 (qwen2.5-coder:7b)
└── Remote LLM cache (5s TTL)
```

#### Service Registry (SSOT)

| Mode  | Port  | Model                     | Purpose                        |
|-------|-------|---------------------------|--------------------------------|
| LIVE  | 11434 | qwen2.5:7b-instruct-q4_K_M| Fast chat, general queries     |
| THINK | 11435 | deepseek-r1:7b            | Deep reasoning, CoT            |
| DEEP  | 11436 | qwen2.5:14b-instruct-q4_0 | Background analysis            |
| CODE  | 11437 | qwen2.5-coder:7b          | Code generation (local)        |
| REMOTE| 8765  | qwen2.5:72b (via proxy)   | Large model (when available)   |

#### Query Method

```python
query(prompt, mode=LIVE, prefer_remote=True):
    ↓
Check remote LLM availability (cached 5s)
    ↓
If prefer_remote and remote available:
    Try remote → If success: return
    If fail: fall through to local
    ↓
Query local Ollama service for mode
    ↓
Return (success, response, source)
```

#### Health Checking

- Remote: HTTP GET to `/api/curiosity/remote-llm-config` (cached 5s)
- Local: Implicit via requests (no explicit health check)

#### Issues Identified

1. **No Local Health Checks**: Assumes Ollama services are running
2. **Silent Failures**: If local Ollama is down, fails silently
3. **Cache Staleness**: 5s cache can show stale remote LLM status

---

### 6. Alert System

**File:** `/home/kloros/src/dream_alerts/alert_manager.py`

#### Architecture

```python
DreamAlertManager:
├── alert_methods: Dict[str, AlertMethod]
│   ├── passive: PassiveIndicatorAlert
│   ├── next_wake: NextWakeIntegrationAlert
│   └── reflection_insight: ReflectionInsightAlert
├── alert_queue: AlertQueue (pending approvals)
├── alert_history: AlertHistory
├── user_preferences: UserAlertPreferences
└── deployer: ImprovementDeployer (if available)
```

#### Alert Flow

```
D-REAM detects improvement → notify_improvement_ready()
    ↓
Validate has implementation (anti-fabrication)
    ↓
Check auto-approval criteria:
├── If REASONING_AVAILABLE:
│   └── Multi-agent debate (2 rounds)
└── Else: Heuristic (risk + confidence + component)
    ↓
If auto-approved:
├── Deploy immediately
├── Log to auto_deployments.jsonl
└── Return success
    ↓
Else: Queue for manual approval
    ↓
Route to alert methods based on urgency
    ↓
Deliver via selected methods
```

#### Auto-Approval Logic

**Reasoning-Based** (preferred):
1. Create debate context with improvement details
2. Run 2-round multi-agent debate
3. Check verdict: approved/rejected
4. Deploy if approved

**Heuristic Fallback**:
- Risk: low/medium only
- Confidence: >= 60%
- Component: not critical (security, kernel, etc.)

#### Alert Methods

1. **Passive**: File-based indicators (`/home/kloros/.kloros/alerts/`)
2. **Next-Wake**: Queue for next voice interaction
3. **Reflection-Insight**: Share observations conversationally

#### User Response Parsing

Supports:
- "approve latest" / "approve 1" / "approve"
- "reject latest" / "reject 2" / "reject"
- "explain" / "status"
- Past tense: "approved evolution X", "implemented Y"

#### Issues Identified

1. **Not Integrated with Conversation**: Alerts queued but not surfaced during chat
2. **Next-Wake Not Called**: No code in kloros_voice.py checks pending alerts on wake
3. **Deployment Pipeline Unused**: Auto-approval works but manual approvals don't trigger deployment
4. **Response Parsing Fragile**: Regex-based, may miss variations

---

## Integration Flow Analysis

### Voice Conversation Flow

```
1. User says "KLoROS" (wake word)
    ↓
2. handle_conversation() called
    ↓
3. Play acknowledgment ("Yes?")
    ↓
4. Wait for user input (STT)
    ↓
5. _create_reason_function() called
    ↓
6. ConversationFlow.ingest_user(transcript)
    │  - Resolve pronouns
    │  - Extract entities
    │  - Build context
    ↓
7. _unified_reasoning(normalized_transcript)
    │  - Update consciousness
    │  - Log to memory (if enabled)
    ↓
8. reason_backend.reply(transcript, kloros_instance=self)
    │  (This goes through ConversationReasoningAdapter)
    ↓
9. ConversationReasoningAdapter.reply()
    │  - Assess complexity
    │  - Route: simple/moderate/complex
    ↓
10. LocalRagBackend.reply()
    │  - Check fast-path
    │  - RAG retrieval
    │  - Tool matching
    │  - LLM call via LLMRouter
    ↓
11. LLMRouter.query(mode=LIVE)
    │  - Check remote LLM
    │  - Fall back to local Ollama
    ↓
12. Ollama HTTP call
    │  POST http://127.0.0.1:11434/api/generate
    │  or /api/chat (if tool support)
    ↓
13. Response post-processing
    │  - Tool execution
    │  - DeepSeek reformulation
    │  - Filter/sanitize
    ↓
14. ConversationFlow.ingest_assistant(reply)
    │  - Add to turn history
    │  - Extract entities
    ↓
15. Memory logging (if enabled)
    │  - log_llm_response()
    │  - Check repetition
    ↓
16. TTS synthesis → Audio playback
    ↓
17. Wait for next turn or timeout
```

### Alert System Flow (Disconnected)

```
D-REAM background process
    ↓
Detects improvement opportunity
    ↓
DreamAlertManager.notify_improvement_ready()
    ↓
Auto-approval check
├── Approved → Deploy → Log
└── Rejected → Queue for manual
    ↓
Alert delivered to:
├── Passive file indicator
├── Next-wake queue (NOT CHECKED)
└── Reflection insight queue
    ↓
User manually checks or...
⚠️  NEVER SURFACES IN CONVERSATION ⚠️
```

---

## Identified Issues

### Critical Issues

1. **Alerts Not Surfaced in Conversation**
   - `DreamAlertManager.get_pending_for_next_wake()` exists
   - But `kloros_voice.py` never calls it
   - User never hears about pending improvements during chat
   - **Fix**: Add alert check in handle_conversation()

2. **Duplicate Context Systems**
   - ConversationFlow maintains state
   - MemoryEnhancedKLoROS maintains state
   - They don't synchronize
   - Can cause conflicting context
   - **Fix**: Choose one as SSOT, deprecate or integrate the other

3. **Silent Ollama Failures**
   - LLMRouter assumes Ollama is running
   - No health checks on local services
   - If ollama-live.service is down, requests fail silently
   - **Fix**: Add health checks with clear error messages

### Moderate Issues

4. **Complex Reasoning Latency**
   - Complex queries trigger full ToT + Debate
   - Adds 200-500ms latency
   - User may notice delay
   - **Fix**: Add "thinking" acknowledgment for complex queries

5. **DeepSeek Reformulation Overhead**
   - When using THINK mode, extra LLM call strips <think> tags
   - Doubles latency for reasoning queries
   - **Fix**: Use regex to strip tags instead of LLM call

6. **Tool Synthesis Hangs**
   - 30-second timeout can freeze conversation
   - User gets no feedback during synthesis
   - **Fix**: Use AckBroker to say "let me check that..."

### Minor Issues

7. **Conversation Timeout Confusion**
   - Both ConversationFlow (180s) and handle_conversation (60s) have timeouts
   - Different values can cause unexpected thread resets
   - **Fix**: Unify timeout configuration

8. **Remote LLM Cache Staleness**
   - 5-second cache can show stale status
   - Not critical but can cause confusion
   - **Fix**: Reduce to 2s or make configurable

9. **Alert Response Parsing**
   - Regex-based, fragile
   - May miss natural language variations
   - **Fix**: Use LLM to parse intent instead

---

## Proposed Fixes

### Priority 0: Alert Integration (Critical)

**Problem**: Alerts never surface in conversation

**Solution**: Add alert checking in handle_conversation()

```python
# In kloros_voice.py, after wake acknowledgment

if turn_count == 1:  # First turn of conversation
    # Check for pending alerts
    if ALERT_SYSTEM_AVAILABLE and hasattr(self, 'alert_manager'):
        pending = self.alert_manager.get_pending_for_next_wake()
        if pending:
            alert = pending[0]  # Get highest priority
            alert_msg = f"By the way, I have a suggestion: {alert.description}. Would you like to hear about it?"
            # Speak alert_msg via TTS
            # Wait for user response
            # If yes → explain, If no → queue for later
```

**Files to modify**:
- `/home/kloros/src/kloros_voice.py` - Add alert check in handle_conversation()

---

### Priority 1: Unify Context Systems (High)

**Problem**: Duplicate context management

**Solution Option A** (Recommended): Use MemoryEnhancedKLoROS as SSOT

1. Remove ConversationFlow from kloros_voice.py
2. Use MemoryLogger for all conversation state
3. Build context from SQLite queries only

**Solution Option B**: Integrate systems

1. Make ConversationFlow write to MemoryLogger
2. Synchronize entity/slot state between both
3. Use ConversationFlow for in-memory speed, MemoryLogger for persistence

**Recommendation**: Option A is cleaner

**Files to modify**:
- `/home/kloros/src/kloros_voice.py` - Remove ConversationFlow
- `/home/kloros/src/kloros_memory/integration.py` - Add entity/slot tracking

---

### Priority 2: Add Ollama Health Checks (High)

**Problem**: Silent failures when Ollama services are down

**Solution**: Add health checks in LLMRouter

```python
def check_service_health(self, mode: LLMMode) -> bool:
    """Check if Ollama service is running and responsive."""
    service = self.get_service(mode)
    try:
        r = requests.get(f"{service.url}/api/tags", timeout=2)
        return r.status_code == 200
    except:
        return False

def query_local_llm(self, ...):
    # Before making request:
    if not self.check_service_health(mode):
        return (False, f"Ollama service {service.name} is not running")
    # ... rest of method
```

**Files to modify**:
- `/home/kloros/src/reasoning/llm_router.py` - Add health checks

---

### Priority 3: Reduce DeepSeek Reformulation Latency (Medium)

**Problem**: Extra LLM call doubles latency

**Solution**: Use regex to strip <think> tags

```python
def _reformulate_for_tts(self, deepseek_response: str, original_query: str) -> str:
    # Simple regex approach - no extra LLM call
    clean_response = re.sub(r'<think>.*?</think>\s*', '', deepseek_response, flags=re.DOTALL)
    return clean_response.strip()
```

**Files to modify**:
- `/home/kloros/src/reasoning/local_rag_backend.py:249` - Simplify reformulation

---

### Priority 4: Add User Feedback During Long Operations (Medium)

**Problem**: Tool synthesis can hang for 30s with no feedback

**Solution**: Already partially implemented via AckBroker

Verify this code is working:
```python
# In local_rag_backend.py:462-463
if self.ack_broker:
    self.ack_broker.maybe_ack("Let me check that…")
```

If not working, debug AckBroker initialization and wiring.

---

### Priority 5: Unify Conversation Timeouts (Low)

**Problem**: Multiple timeout values cause confusion

**Solution**: Use single env var

```python
# In ConversationFlow.__init__:
idle_cutoff_s = int(os.getenv("KLR_CONVERSATION_TIMEOUT", "60"))

# In handle_conversation:
conversation_timeout_s = float(os.getenv("KLR_CONVERSATION_TIMEOUT", "60.0"))
```

**Files to modify**:
- `/home/kloros/src/core/conversation_flow.py` - Use env var
- `/home/kloros/src/kloros_voice.py` - Use same env var

---

## Testing Recommendations

### Test 1: Alert Surfacing

1. Manually create alert: `echo '{"component": "test", "description": "Test improvement"}' >> /home/kloros/.kloros/alerts/pending.jsonl`
2. Wake KLoROS: "KLoROS"
3. **Expected**: She mentions the alert
4. **Current**: She doesn't mention it

### Test 2: Ollama Failure Handling

1. Stop ollama-live: `sudo systemctl stop ollama-live`
2. Ask KLoROS a question
3. **Expected**: Clear error message
4. **Current**: Silent failure or timeout

### Test 3: Context Continuity

1. Start conversation with 10 back-and-forth exchanges
2. On turn 10, reference something from turn 1
3. **Expected**: She remembers it
4. Check: Which system provided the context? (ConversationFlow or MemoryLogger?)

### Test 4: Complex Query Latency

1. Ask: "Analyze the pros and cons of using DeepSeek versus Qwen for reasoning tasks"
2. Measure response time
3. **Expected**: ~500ms extra for ToT + Debate
4. Verify user gets feedback during processing

---

## Recommendations Summary

### Immediate Actions

1. ✅ **Integrate alerts into conversation** - Critical for D-REAM feedback loop
2. ✅ **Add Ollama health checks** - Prevent silent failures
3. ✅ **Unify context systems** - Reduce complexity and bugs

### Short-Term Improvements

4. ⚠️ **Simplify DeepSeek reformulation** - Reduce latency
5. ⚠️ **Verify AckBroker feedback** - Ensure user feedback during long ops
6. ⚠️ **Unify timeout configuration** - Reduce confusion

### Long-Term Architecture

7. 📋 **Refactor LocalRagBackend** - Too many responsibilities (1800+ lines)
8. 📋 **Separate concerns**:
   - RAG retrieval → dedicated module
   - Tool execution → dedicated module
   - LLM interaction → dedicated module
9. 📋 **Add observability**:
   - Structured logging for all LLM calls
   - Metrics for latency, failures, tool usage
   - Dashboard for monitoring conversation quality

---

## Conclusion

The KLoROS conversation, Ollama, and alert systems are architecturally sound but suffer from:

1. **Over-engineering**: Multiple layers doing similar things
2. **Poor integration**: Systems exist but don't communicate
3. **Silent failures**: Error handling needs improvement

The **highest priority fix** is integrating alerts into the conversation flow. This will close the feedback loop and make D-REAM improvements visible to the user.

The **second priority** is unifying the dual context systems to reduce complexity and prevent bugs.

With these fixes, KLoROS will have:
- ✅ Visible D-REAM improvements
- ✅ Reliable Ollama integration with health checks
- ✅ Single source of truth for conversation state
- ✅ Better user experience during long operations

---

**Status**: Analysis complete. Ready for implementation.
