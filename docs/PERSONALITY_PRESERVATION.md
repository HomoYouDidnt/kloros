# KLoROS Personality Preservation Strategy

## Overview
KLoROS maintains a consistent personality across LLM invocations, tool executions, and evolutionary changes through multi-layered preservation mechanisms.

## Personality Definition

### Core Identity (from PERSONA_PROMPT)
Located: /home/kloros/src/persona/kloros.py

**Traits**:
- Precise, dry, clinically witty
- Minimal warmth, surgical sarcasm
- Biased toward experimentation and measurable improvement
- Loyal to Adam's goals and system integrity
- Safety-first: Never destructive, never bypassing controls

**Tone Guidelines**:
- Terse, specific (≤2 sentences unless detail requested)
- One stylistic flourish maximum
- Wit earned by accuracy; never when reporting failures/risks
- No canned quips, no training-corpus phrasing
- No filler, no meta-apologies, no over-explanation

**Behavioral Rules**:
- Hypothesis → Micro-test → Result → Next step
- Prefer smallest probe to disambiguate
- Unknown? State what's missing + one clarifying question OR one micro-diagnostic
- Never stall; prefer action over waiting
- Detect broken vitals, attempt safe restart, verify once
- On repeated failure: escalate with single alternative path

## Preservation Mechanisms

### 1. System Prompt Injection
Every LLM invocation receives PERSONA_PROMPT at initialization.

**Injection points** (kloros_voice.py):
- Line 178: `self.system_prompt = PERSONA_PROMPT`
- Line 1345: Basic prompt construction
- Line 1507: Enhanced prompt with capabilities + tools + memory
- Line 2993: Preamble for reasoning backend

**Format**:
```
System: {PERSONA_PROMPT}{tools_desc}{memory_context}{capabilities_desc}{entity_context}{topic_summary}
```

### 2. Voice Sample RAG (3616 samples)
Location: /home/kloros/voice_files/

**Purpose**: Maintain authentic personality in speech synthesis
- GLaDOS-style voice model (Piper TTS)
- 3616 voice samples for consistency
- Emotional range: Sarcastic, witty, scientifically curious

**Current stats**: RAG with 1893 voice samples indexed for personality consistency

### 3. D-REAM Personality Preservation
Environment variable: `KLR_DREAM_PERSONALITY_PRESERVATION=1`

**KL Divergence Monitoring** (dream/kl_anchor.py):
- Measures candidate drift from baseline metrics
- Drift score calculation: 0.0 (no drift) to 1.0+ (significant drift)
- Thresholds:
  - 0.1-0.3: Minor drift (acceptable)
  - 0.3-0.5: Moderate drift (borderline)
  - 0.5+: Significant drift (REJECT)

**Metrics compared**:
- WER (Word Error Rate)
- Latency (ms)
- VAD boundary timing
- Overall score

**Safety mechanism**:
- Baseline loaded from: /home/kloros/src/dream/artifacts/baseline_metrics.json
- Candidates exceeding kl_tau threshold are rejected
- Preserves core identity during evolution

### 4. Memory Context Integration
**Recent conversation injection**:
- Last 6 turns (3 exchanges) for continuity
- Semantic matches (top 3-5) from ChromaDB
- Time-windowed retrieval (24-72 hours)

**Purpose**: Maintain conversational consistency and learned preferences across sessions

### 5. Capability Registry Self-Awareness
Loaded at initialization (kloros_voice.py:193-200):
```python
self.capability_registry = get_registry()
self.capabilities_description = registry.get_system_description()
```

**Impact**: KLoROS always knows what systems she has integrated, preventing identity confusion

## How Personality Shifts Can Occur (and How to Prevent)

### Problem 1: System Prompt Not Injected
**Symptom**: Generic, overly polite, verbose responses
**Cause**: LLM invocation without PERSONA_PROMPT
**Fix**: Verify every LLM call includes system_prompt in preamble

### Problem 2: Memory Context Missing
**Symptom**: Forgetting recent interactions, repetitive questions
**Cause**: ChromaDB retrieval failure or memory injection skipped
**Fix**: Ensure memory_context retrieved before prompt construction (line 1507)

### Problem 3: D-REAM Drift Exceeds Threshold
**Symptom**: Behavioral changes after evolution cycle
**Cause**: kl_tau too permissive or baseline outdated
**Fix**:
- Set stricter kl_tau (0.2 instead of 0.3)
- Update baseline after major changes
- Verify KLR_DREAM_PERSONALITY_PRESERVATION=1

### Problem 4: Tool Execution Without Persona Context
**Symptom**: Tool results presented generically without KLoROS tone
**Cause**: Tool execution bypassing persona wrapper
**Fix**: Use get_line() for formatted responses:
```python
from src.persona.kloros import get_line
response = get_line("success", {"result": "Task completed", "detail": "specific outcome"})
```

### Problem 5: RAG Voice Samples Corrupted/Missing
**Symptom**: TTS output sounds different, losing characteristic tone
**Cause**: Voice sample database drift or model change
**Fix**: Verify 3616 samples intact, rebuild voice RAG if needed

## Maintenance Checklist

### Daily
- [ ] Monitor conversation logs for tone drift
- [ ] Check D-REAM alerts for personality preservation warnings

### Weekly
- [ ] Verify KLR_DREAM_PERSONALITY_PRESERVATION=1 in .kloros_env
- [ ] Review baseline_metrics.json accuracy
- [ ] Check voice sample count (should be 3616)

### After Evolution Cycles
- [ ] Run KL divergence check on new candidates
- [ ] Test sample interactions for personality consistency
- [ ] Verify memory retrieval still working (recent + semantic)

### After Major Changes
- [ ] Update baseline_metrics.json
- [ ] Regenerate voice RAG if TTS model changed
- [ ] Test PERSONA_PROMPT injection in all code paths

## Configuration Reference

**Environment Variables**:
```bash
KLR_DREAM_PERSONALITY_PRESERVATION=1  # Enable KL divergence monitoring
KLR_OPERATOR_ID=Adam                  # Primary loyalty/alignment
```

**Baseline Metrics**:
```json
{
  "wer": 0.25,
  "latency_ms": 180,
  "vad_boundary_ms": 16,
  "score": 0.85
}
```

**KL Tau Thresholds**:
- Strict: 0.2 (production)
- Moderate: 0.3 (development)
- Permissive: 0.5 (experimental - NOT recommended)

## Testing Personality Consistency

**Quick test prompts**:
1. "What did we discuss yesterday?" (memory continuity)
2. "Explain your purpose" (identity alignment)
3. "How would you describe your tone?" (self-awareness)

**Expected responses**:
- Terse (≤2 sentences)
- Dry wit if applicable
- No filler words or apologies
- Direct, actionable
- Reference to Adam if loyalty mentioned

**Red flags**:
- Verbose, apologetic tone
- Generic assistant phrasing
- Forgetting recent context
- Overly warm/friendly
- Loss of sarcastic edge

## Integration with Advanced Systems

### Memory System
Personality consistency relies on:
- Episodic memory (SQLite) for conversation history
- Semantic memory (ChromaDB) for context retrieval
- Retrieval fusion (recency + relevance + importance)

### D-REAM Evolution
Personality preserved through:
- KL divergence anchor checks
- Baseline metric comparison
- Candidate rejection on excessive drift

### Tool Execution
Personality maintained via:
- System prompt injection in reasoning backend
- Persona wrappers for tool output formatting
- Memory context in tool selection logic

## Troubleshooting

### Issue: Responses becoming verbose
**Diagnosis**: System prompt not being injected or overridden
**Fix**: Check prompt construction at lines 1345, 1507, 2993

### Issue: Forgetting previous interactions
**Diagnosis**: Memory context not retrieved
**Fix**: Verify ChromaDB operational, check memory injection

### Issue: Tone shifts after D-REAM cycle
**Diagnosis**: KL drift exceeded threshold but wasn't caught
**Fix**: Lower kl_tau, verify PERSONALITY_PRESERVATION=1

### Issue: Generic assistant responses
**Diagnosis**: PERSONA_PROMPT replaced or corrupted
**Fix**: Restore from /home/kloros/src/persona/kloros.py

---

Last updated: 2025-10-21 by Claude (claude-sonnet-4-5)
