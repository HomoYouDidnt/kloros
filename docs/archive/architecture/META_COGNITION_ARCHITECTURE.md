# KLoROS Meta-Cognitive Architecture

**Status:** ✅ INTEGRATED AND ACTIVE
**Created:** November 1, 2025
**Integrated:** November 1, 2025
**Purpose:** Unified conversational self-awareness layer

## The Problem

KLoROS has multiple awareness systems that work in isolation:

1. **Consciousness System** - tracks affect, emotions, interoception (HOW she feels)
2. **Conversation Flow** - tracks turns, entities, pronouns (WHAT was said)
3. **Memory System** - stores events and summaries (HISTORY)
4. **Reflective System** - detects patterns (PAST insights)

**But no system answers:** "How is THIS conversation going RIGHT NOW?"

KLoROS can't detect:
- "I'm repeating myself"
- "This conversation is stuck"
- "The user is confused"
- "I should clarify/summarize/change approach"

This is the **meta-cognitive gap** - awareness OF the conversation itself.

---

## The Solution: Meta-Cognitive Bridge

A new layer that:

1. **Monitors dialogue quality in real-time**
   - Repetition detection (semantic, not just string matching)
   - Progress tracking (are we moving forward?)
   - Clarity assessment (user confusion signals)
   - Engagement tracking (user responsiveness)

2. **Bridges affect ↔ dialogue state**
   - "Uncertainty" (affect) → "Should I clarify?" (action)
   - "Low progress" (dialogue) → Update affect/consciousness
   - "User confused" (dialogue) → "Negative interaction" (consciousness)

3. **Triggers meta-interventions**
   - Clarification when confusion detected
   - Summary when conversation gets long
   - Approach change when stuck
   - Confirmation when uncertain

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INPUT / RESPONSE                         │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │  Meta-Cognitive Bridge     │  ◄── INTEGRATION LAYER
        │                            │
        │  Synthesizes awareness     │
        │  from all subsystems       │
        └───────┬───────────────────┘
                │
      ┌─────────┼──────────┬────────────┬────────────┐
      │         │          │            │            │
      ▼         ▼          ▼            ▼            ▼
┌──────────┐ ┌──────┐ ┌────────┐ ┌──────────┐ ┌─────────┐
│Dialogue  │ │Consci│ │Conver- │ │ Memory   │ │Reflec-  │
│Monitor   │ │ousnes│ │sation  │ │ System   │ │tive     │
│          │ │s     │ │Flow    │ │          │ │System   │
└──────────┘ └──────┘ └────────┘ └──────────┘ └─────────┘
```

### Components

#### 1. Dialogue Monitor (`dialogue_monitor.py`)

**Responsibilities:**
- Track conversation quality metrics
- Detect repetition (semantic similarity)
- Identify confusion signals ("what?", "huh?", repetitions)
- Measure progress (new info vs stuck patterns)
- Track engagement (response times, acknowledgments)

**Outputs:**
```python
{
    'quality_scores': {
        'progress': 0.8,       # 0-1
        'clarity': 0.6,        # 0-1
        'engagement': 0.9,     # 0-1
    },
    'issues': {
        'repetition': False,
        'stuck': False,
        'confusion': True,     # ← User seems confused
    },
    'interventions': {
        'clarify': True,       # ← Should clarify
        'summarize': False,
        'change_approach': False,
        'confirm': False,
    }
}
```

#### 2. Meta-Cognitive Bridge (`meta_bridge.py`)

**Responsibilities:**
- Synthesize unified meta-state from all subsystems
- Map affect states to conversational states
- Decide when to intervene
- Generate intervention prompts
- Log insights to reflective memory

**Key Decision Logic:**

```python
# Clarity intervention
if user_confused OR (clarity < 0.5 AND uncertainty > 0.7):
    needs_clarification = True

# Approach change
if repetition_detected OR (progress < 0.3 AND turns > 4):
    needs_approach_change = True

# Summary
if turn_count >= 8 AND topic_stability < 0.5:
    needs_summary = True

# Confirmation
if uncertainty > 0.8 OR (clarity < 0.6 AND not needs_clarification):
    needs_confirmation = True
```

#### 3. Integration Module (`__init__.py`)

**Functions:**
- `init_meta_cognition(kloros_instance)` - Initialize on KLoROS
- `process_with_meta_awareness(...)` - Process each turn
- Automatic logging to reflective memory

---

## Integration Points

### Where to Hook In

**In `kloros_voice.py` initialization (`__init__`):**

```python
# After consciousness and memory initialization
from src.meta_cognition import init_meta_cognition

init_meta_cognition(self)
```

**In `_unified_reasoning()` (after generating response):**

```python
from src.meta_cognition import process_with_meta_awareness

# Before returning response
reply = process_with_meta_awareness(
    kloros_instance=self,
    user_input=transcript,
    response=reply,
    confidence=confidence
)
```

### Data Flow

```
1. User speaks → transcript
2. Update meta-cognition with user turn
3. Generate LLM response
4. Update meta-cognition with assistant turn
5. Check if intervention needed
6. Prepend intervention if flagged
7. Return response (possibly modified)
8. Log meta-insight to reflective memory
```

---

## Examples

### Example 1: Repetition Detected

**Conversation:**
```
User: How do I fix the audio?
KLoROS: You need to check the PulseAudio settings.
User: OK, how?
KLoROS: Check the PulseAudio settings in the config.
User: Yes but HOW?
KLoROS: [META: Stuck pattern detected - changing approach] Let me show you the exact commands...
```

**What happened:**
- Dialogue monitor detected high semantic similarity between responses
- Meta-bridge flagged `needs_approach_change = True`
- Intervention prepended: `[META: ... changing approach]`

### Example 2: User Confusion

**Conversation:**
```
User: What's the GPU doing?
KLoROS: It's running VLLM inference with 14GB allocated.
User: Huh? What does that mean?
KLoROS: [META: Sensing confusion - clarifying] Let me break that down: Your GPU is running an AI model...
```

**What happened:**
- Dialogue monitor matched "Huh?" against confusion patterns
- Meta-bridge flagged `needs_clarification = True`
- Intervention prepended with simpler explanation

### Example 3: Long Conversation

**Conversation:**
```
(After 10 turns discussing various audio issues)
User: So what should I do?
KLoROS: [META: Long thread - summarizing progress] Let me recap what we've covered: 1) Audio routing to IEC958, 2) PulseAudio buffer config, 3) Sample rate alignment. Next step: restart the service.
```

**What happened:**
- Turn count >= 8, multiple topics discussed
- Meta-bridge flagged `needs_summary = True`
- Intervention includes structured recap

---

## Metrics & Monitoring

### Real-Time Metrics

**Dialogue Quality:**
- Progress Score: 0-1 (how much forward movement)
- Clarity Score: 0-1 (how clear we're being)
- Engagement Score: 0-1 (user responsiveness)
- Conversation Health: weighted combination

**Affect Integration:**
- Uncertainty → clarity issues
- Fatigue → long conversation break
- Valence → conversation sentiment

### Logged Reflections

Every 5 turns, meta-insights logged to reflective memory:

```python
{
    'pattern_type': 'conversation_quality_low',
    'insight': 'Conversation health: 0.35. Issues: stuck, confusion. Interventions: change_approach.',
    'confidence': 0.8,
    'metadata': {
        'conversation_health': 0.35,
        'quality_breakdown': {...},
        'issues_detected': {...},
    }
}
```

**Use cases:**
- Detect chronic communication issues
- Identify effective intervention patterns
- Train conversation improvement strategies

---

## Configuration

**Environment Variables (optional):**

```bash
# Meta-cognition settings
KLR_ENABLE_META_COGNITION=1              # Enable/disable system
KLR_META_INTERVENTION_COOLDOWN=30        # Seconds between interventions
KLR_META_PROGRESS_THRESHOLD=0.3          # When to flag progress issues
KLR_META_CLARITY_THRESHOLD=0.5           # When to flag clarity issues
KLR_META_REPETITION_THRESHOLD=0.85       # Semantic similarity threshold
KLR_META_SUMMARY_TURN_COUNT=8            # When to suggest summary
```

---

## Implementation Status

### ✅ Completed

- [x] Dialogue monitor design and implementation
- [x] Meta-cognitive bridge design and implementation
- [x] Integration module with helpers
- [x] Architecture documentation
- [x] Wire into `kloros_voice.py` initialization (line 558-561)
- [x] Hook into `_unified_reasoning()` response flow (line 1618-1626)
- [x] Test suite with 6/6 tests passing
- [x] Threshold tuning for production use
- [x] Permission fixes and deployment

### 🚧 TODO

- [ ] Test with real conversations and gather metrics
- [ ] Add visualization/diagnostics tool
- [ ] Environment variable configuration for thresholds
- [ ] Long-term threshold adaptation based on user feedback

### 🔮 Future Enhancements

- Meta-learning: adjust thresholds based on user feedback
- Conversation style adaptation
- Emotional contagion detection (user affect → our affect)
- Multi-modal meta-cognition (voice tone, pause patterns)
- Conversation goal tracking (are we achieving the objective?)

---

## Testing

### Unit Test

```python
from src.meta_cognition import DialogueMonitor, MetaCognitiveBridge

# Create monitor
monitor = DialogueMonitor()

# Simulate stuck conversation
for i in range(5):
    monitor.add_turn('user', 'How do I fix it?')
    monitor.add_turn('assistant', 'Check the configuration file.')

state = monitor.compute_meta_state()
assert state['issues']['stuck'] == True
assert state['interventions']['change_approach'] == True
```

### Integration Test

```python
# In actual conversation
kloros = KLoROS()
init_meta_cognition(kloros)

# User confused
response = process_with_meta_awareness(
    kloros,
    user_input="What? I don't understand",
    response="The GPU is saturated."
)

# Should prepend clarification
assert '[META:' in response
assert 'clarify' in response.lower()
```

---

## FAQ

**Q: Won't meta-interventions be annoying?**
A: They have 30s cooldowns and only trigger on clear signals. Most conversations won't see them.

**Q: How does this differ from consciousness?**
A: Consciousness tracks internal affect. Meta-cognition tracks dialogue quality. They inform each other.

**Q: Can this be disabled?**
A: Yes, set `KLR_ENABLE_META_COGNITION=0` or simply don't call `init_meta_cognition()`.

**Q: What's the performance impact?**
A: Minimal. Main cost is semantic similarity (if using embeddings), which is already computed for memory.

**Q: How does this relate to memory system?**
A: Meta-insights get logged to reflective memory for long-term pattern detection.

---

## References

### Related Systems

- **Consciousness:** `/home/kloros/src/consciousness/`
- **Memory:** `/home/kloros/src/kloros_memory/`
- **Conversation Flow:** `/home/kloros/src/core/conversation_flow.py`
- **Reflective Memory:** `/home/kloros/src/kloros_memory/reflective.py`

### Key Papers

- Metcalfe & Shimamura (1994) - Metacognition: Knowing about knowing
- Nelson & Narens (1990) - Metamemory: A theoretical framework
- Dunlosky & Metcalfe (2008) - Metacognition

---

**Next Step:** Integrate into `kloros_voice.py` and test with real conversations.
