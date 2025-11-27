# Conversation Mode Reasoning Integration - Analysis

## Current State

KLoROS conversation flow:
1. User speaks → STT transcription
2. `reason_backend.reply(transcript, kloros_instance=self)` at **kloros_voice.py:1572, 1785, 3360**
3. RAG retrieval + tool execution
4. LLM response generation
5. TTS playback

The reasoning backend handles RAG, tool selection, and response generation.

---

## Potential Integration Points

### 1. **Pre-Response Strategy Selection** (ToT)
**Location**: Before `reason_backend.reply()`
**Purpose**: Explore multiple response strategies before committing

```python
# BEFORE calling reason_backend
strategies = coordinator.explore_solutions(
    problem=f"How should I respond to: {transcript}",
    max_depth=2
)
best_strategy = coordinator.reason_about_alternatives(
    context="Which response strategy?",
    alternatives=strategies,
    mode=ReasoningMode.LIGHT
)
```

**Pros**:
- More thoughtful responses
- Can consider multiple approaches
- Better for complex/ambiguous questions

**Cons**:
- +100-200ms latency per message
- Overkill for simple queries like "what time is it?"
- User expects conversational speed

### 2. **Response Validation** (Debate)
**Location**: After LLM generates response, before TTS
**Purpose**: Multi-agent debate validates response quality

```python
# AFTER getting response from reason_backend
debate_result = coordinator.debate_decision(
    context="Is this response appropriate?",
    proposed_decision={
        'response': response_text,
        'user_query': transcript,
        'confidence': 0.8
    },
    rounds=1  # Fast single-round check
)
if debate_result['verdict']['verdict'] != 'approved':
    # Regenerate or add disclaimer
```

**Pros**:
- Catches problematic responses before TTS
- Quality control for sensitive topics
- Adds transparency

**Cons**:
- +100-500ms latency
- Interrupts conversational flow
- May be overly cautious

### 3. **Context Prioritization** (VOI)
**Location**: Inside `reason_backend.reply()` during RAG retrieval
**Purpose**: Calculate VOI for retrieved documents/memories

```python
# INSIDE RAG retrieval
for doc in retrieved_documents:
    doc['voi'] = coordinator.calculate_voi({
        'action': 'Use this context',
        'relevance': doc['similarity'],
        'recency': doc['timestamp'],
        'completeness': doc['metadata']
    })
ranked_docs = sorted(retrieved_documents, key=lambda d: d['voi'], reverse=True)
```

**Pros**:
- Better context selection
- More relevant responses
- Minimal latency (+10-50ms)

**Cons**:
- RAG already has good ranking
- Small improvement for added complexity

### 4. **Tool Selection Reasoning** (ToT + VOI)
**Location**: When reason_backend decides which tools to call
**Purpose**: Reason about which tools are most valuable

```python
# DURING tool selection
available_tools = get_tools_for_query(transcript)
tool_vois = []
for tool in available_tools:
    voi = coordinator.calculate_voi({
        'action': f'Call {tool.name}',
        'expected_info': tool.description,
        'cost': tool.estimated_latency
    })
    tool_vois.append((tool, voi))
best_tools = sorted(tool_vois, key=lambda x: x[1], reverse=True)[:3]
```

**Pros**:
- Smarter tool selection
- Reduces unnecessary calls
- Moderate latency (+50ms)

**Cons**:
- Tool selection heuristics already work
- May overthink simple queries

---

## Recommendations

### ✅ **Recommended: Selective Reasoning**

**Integrate reasoning only when:**
1. **Complex queries** detected (multi-part questions, ambiguity)
2. **Safety-critical responses** (medical, legal, financial advice)
3. **Tool selection** when multiple tools available
4. **User explicitly requests** ("think carefully about...")

**Implementation**:
```python
def should_use_reasoning(transcript: str) -> bool:
    """Decide if query warrants reasoning overhead."""
    complexity_indicators = [
        len(transcript.split()) > 20,  # Long query
        '?' in transcript and transcript.count('?') > 1,  # Multiple questions
        any(word in transcript.lower() for word in ['compare', 'analyze', 'explain why', 'how does']),
        # Safety keywords
        any(word in transcript.lower() for word in ['should i', 'medical', 'legal', 'financial'])
    ]
    return any(complexity_indicators)

# In conversation handler:
if should_use_reasoning(transcript):
    # Use ToT/Debate/VOI
    result = reason_with_coordinator(transcript)
else:
    # Fast path - direct to reason_backend
    result = self.reason_backend.reply(transcript)
```

### ⚠️ **Not Recommended: Always-On Reasoning**

Applying ToT/Debate to every user message would:
- Add 160-750ms latency to every response
- Break conversational flow
- Frustrate users with slow responses
- Waste computation on trivial queries

Example:
- User: "What time is it?"
- System: *runs Tree of Thought, Multi-Agent Debate, VOI calculation*
- System: "It's 2:30 PM" (3 seconds later)
- User: 😐

---

## Latency Impact

Current conversation latency budget:
- STT: ~200-500ms
- RAG retrieval: ~100-300ms
- LLM generation: ~500-1500ms
- TTS: ~300-800ms
- **Total**: ~1.1-3.1 seconds

With always-on reasoning:
- +ToT: +100-200ms
- +Debate: +100-500ms
- +VOI: +10-50ms
- **New Total**: ~1.3-3.9 seconds

**User tolerance**: Most users expect responses within 2 seconds for conversational AI.

---

## Proposed Architecture

```python
class ConversationReasoningAdapter:
    """Adaptive reasoning for conversation mode."""

    def __init__(self, coordinator, reason_backend):
        self.coordinator = coordinator
        self.reason_backend = reason_backend

    def reply(self, transcript: str, kloros_instance=None) -> str:
        """Adaptively apply reasoning based on query complexity."""

        # Phase 1: Quick complexity assessment
        complexity = self._assess_complexity(transcript)

        # Phase 2: Route based on complexity
        if complexity == 'simple':
            # Fast path - no reasoning overhead
            return self.reason_backend.reply(transcript, kloros_instance)

        elif complexity == 'moderate':
            # Light reasoning - VOI for context selection
            contexts = self.reason_backend.retrieve_contexts(transcript)
            ranked_contexts = self._rank_by_voi(contexts)
            return self.reason_backend.reply_with_contexts(transcript, ranked_contexts)

        elif complexity == 'complex':
            # Full reasoning - ToT + Debate
            strategies = self.coordinator.explore_solutions(
                problem=f"How to respond to: {transcript}",
                max_depth=2
            )
            best_strategy = self.coordinator.reason_about_alternatives(
                context="Best response strategy",
                alternatives=strategies,
                mode=ReasoningMode.STANDARD
            )
            response = self.reason_backend.generate_from_strategy(best_strategy)

            # Validate before speaking
            validation = self.coordinator.debate_decision(
                context="Is this response appropriate?",
                proposed_decision={'response': response},
                rounds=1
            )

            return response if validation['verdict']['verdict'] == 'approved' else self._safe_fallback(transcript)

    def _assess_complexity(self, transcript: str) -> str:
        """Quick heuristic complexity assessment."""
        word_count = len(transcript.split())
        has_multiple_questions = transcript.count('?') > 1
        has_reasoning_words = any(word in transcript.lower() for word in
            ['why', 'how does', 'explain', 'compare', 'analyze', 'evaluate'])
        is_safety_critical = any(word in transcript.lower() for word in
            ['should i', 'medical', 'legal', 'financial', 'dangerous'])

        if is_safety_critical or (has_reasoning_words and word_count > 15):
            return 'complex'
        elif word_count > 10 or has_multiple_questions:
            return 'moderate'
        else:
            return 'simple'
```

---

## Conclusion

**Answer**: Yes, reasoning can be integrated into conversation mode, but it should be **selective and adaptive** rather than always-on.

**Implementation Strategy**:
1. ✅ Add complexity detection heuristic
2. ✅ Route simple queries to fast path (no reasoning)
3. ✅ Apply VOI for moderate complexity (context ranking)
4. ✅ Use full ToT/Debate for complex or safety-critical queries
5. ✅ Allow user to force reasoning mode ("think carefully...")

**Next Steps**:
1. Implement `ConversationReasoningAdapter` class
2. Add complexity detection to conversation handler
3. Wire into existing `reason_backend.reply()` calls
4. Add user override: "Claude, think carefully about..." triggers full reasoning
5. Monitor latency metrics and user satisfaction

**Expected Impact**:
- 90% of queries: No added latency (simple queries)
- 8% of queries: +50ms latency (moderate - VOI only)
- 2% of queries: +200-500ms latency (complex - full reasoning)
- **Average latency increase**: ~15-25ms across all queries
