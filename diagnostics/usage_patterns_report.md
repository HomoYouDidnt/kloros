# Usage Patterns Report
**Generated:** 2025-10-12 01:46:45
**Data Source:** memory.db analysis (from memory_health_report.md)

---

## Episode Statistics

- **Total episodes:** 283
- **Episodes with summaries:** 280 (99%)
- **Average events per episode:** 4.0
- **Average episode duration:** 57.7 seconds (~1 minute)
- **Episode range:** 3-32 events

---

## Event Type Distribution

| Event Type | Count | Percentage |
|------------|-------|------------|
| user_input | 5,148 | 40.6% |
| llm_response | 2,655 | 20.9% |
| context_retrieval | 2,530 | 19.9% |
| self_reflection | 743 | 5.9% |
| tts_output | 472 | 3.7% |
| conversation_end | 296 | 2.3% |
| conversation_start | 296 | 2.3% |
| wake_detected | 296 | 2.3% |
| episode_condensed | 189 | 1.5% |
| stt_transcription | 50 | 0.4% |
| error_occurred | 15 | 0.1% |

---

## Usage Patterns

### Pattern 1: Voice Interactions
- **296 wake detections** = 296 voice conversations initiated
- **472 TTS outputs** = 472 spoken responses
- **50 STT transcriptions** logged separately

**Ratio:** 1.6 TTS outputs per wake detection (some conversations multi-turn)

### Pattern 2: Context Retrieval
- **2,530 context retrievals** for 5,148 user inputs
- **Retrieval rate:** 49.1% of user inputs trigger context search
- **Issue:** Most retrievals likely return empty (90% NULL conversation_id)

### Pattern 3: Episode Characteristics
- **Very short episodes** (average 4 events, 1 minute)
- Suggests: Quick interactions, not extended conversations
- **Minimal multi-turn dialogue** despite conversation mode enabled

### Pattern 4: Self-Reflection
- **743 self-reflection events** (5.9% of total)
- Recent activity shows **100% self-reflection** (last 50 events)
- Suggests: System running in background without user interaction

---

## Conversation Metrics

### Conversation ID Usage
- **296 conversations started** (conversation_start events)
- **296 conversations ended** (conversation_end events)
- BUT: **90.2% of events have NULL conversation_id**

**Anomaly:** conversation_start/end events exist, but most events not tagged with conversation_id

### Turn-Taking Patterns
- User inputs: 5,148
- LLM responses: 2,655
- **Response rate:** 51.6%

**Anomaly:** Only half of user inputs generate LLM responses?
- Possible causes:
  - Transcription failures
  - System errors
  - Events logged without conversation flow

---

## Topic Distribution (from Episode Summaries)

### Most Common Topics
1. **audio_output_issues** - Frequent
2. **communication_failure** - Very frequent
3. **audio_functionality** - Frequent
4. **clarification** - Common
5. **greeting** - Common
6. **tts_functionality** - Common
7. **malfunction** - Frequent
8. **insufficient_data** - Common

### Topic Analysis
- **70% technical issues** (audio, communication, malfunction)
- **20% conversational** (greeting, clarification)
- **10% other**

**Implication:** User primarily troubleshooting system issues

---

## Success/Failure Patterns

### Successful Patterns
- ✅ 280/283 episodes have summaries (99% success rate)
- ✅ Episode condensation working (189 condensed)
- ✅ Consistent conversation boundaries (296 start/end pairs)

### Failure Patterns
- ❌ 90% events orphaned (not in episodes)
- ❌ 90% events with NULL conversation_id
- ❌ Only 51.6% user inputs generate responses
- ❌ High frequency of error-related topics

---

## User Behavior Patterns

### Interaction Frequency
- **12,693 events** across 283 episodes
- Average: **44.8 events per episode** if evenly distributed
- But episodes average only 4 events
- **Discrepancy:** Most events not captured in episodes

### Session Patterns
- **Short sessions** (1 minute average)
- **Quick interactions** (4 events average)
- Suggests: User asking quick questions, not extended dialogues

### Recent Activity
- **Last 50 events:** 100% self_reflection
- **Last 20 episodes:** Audio/communication issues
- Suggests: System idle or troubleshooting mode

---

## Command Patterns

### Most Likely Commands (inferred from topics)
1. Audio diagnostics ("check audio", "test microphone")
2. System status queries ("what's wrong", "check status")
3. Greetings ("hello", "hey KLoROS")
4. Clarification requests ("what?", "repeat that")

### Unmet Needs (inferred from issues)
- User wants: Reliable audio output
- User wants: Consistent command following
- User wants: Context awareness
- System provides: Partial or failed responses

---

## Recommendations

1. **Fix conversation_id assignment** - Will properly group events into episodes
2. **Increase episode duration threshold** - Capture longer interactions
3. **Investigate 48% non-response rate** - Why do half of user inputs not get responses?
4. **Add usage analytics tool** - Better visibility into interaction patterns
5. **Focus on audio/communication fixes** - These dominate user concerns

---

## Summary

**User profile:** Technical user troubleshooting system issues
**Primary use case:** Voice interactions for system diagnostics
**Main pain point:** Audio/communication reliability
**System health:** Poor - most interactions involve troubleshooting

**Opportunity:** Once core issues fixed (tool system, context), usage patterns suggest user ready for more complex interactions.
