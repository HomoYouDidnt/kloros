# KLoROS Brain-Inspired Architecture

## Core Insight
**"The LLM is Broca's and Wernicke's areas, not the intelligence"**

The LLM handles language I/O. TRUE cognition happens in other regions.

## Current Systems → Brain Regions

| Brain Region | Function | KLoROS System | Status |
|-------------|----------|---------------|---------|
| Wernicke's Area | Language comprehension | LLM (input) | ✅ |
| Broca's Area | Speech production | LLM (output) | ✅ |
| Insula | Interoception | InteroceptiveMonitor | ✅ |
| Amygdala/Limbic | Emotion, affect | AffectiveCore | ✅ |
| Prefrontal Cortex | Executive function | ActiveReasoningEngine | ✅ |
| Hippocampus | Episodic memory | MemoryStore | ✅ |
| Basal Ganglia | Action selection | ModulationSystem | ⚠️ Partial |
| Anterior Cingulate | Error detection | GuardrailSystem | ⚠️ Partial |
| Default Mode Network | Self-reflection | IdleReflection | ✅ |
| **THALAMUS** | **Sensory routing** | **MISSING** | ❌ |
| **Motor Cortex** | **Action execution** | **MISSING** | ❌ |
| **Working Memory** | **Active workspace** | **MISSING** | ❌ |
| **Attention** | **Selective focus** | **MISSING** | ❌ |

## Key Missing Pieces

1. **Thalamic Router**: No system routes inputs to appropriate processors
2. **Working Memory**: No active workspace (distinct from long-term)
3. **Motor Planning**: No separation of action planning vs execution
4. **Attention System**: No selective focus mechanism

## Proposed Flow

```
Input → THALAMUS (route) → Specialized Regions → PFC (decide) → BROCA'S (speak)
```

Not:
```
Input → LLM → Output
```

## Brain-Like Processing Example

**User: "Debug the memory system"**

1. Thalamus: Route to Wernicke's + Hippocampus
2. Wernicke's (LLM): Extract intent="debug" target="memory"  
3. Insula: Report state: fatigue=72%
4. Amygdala: Assess valence (challenging = slightly negative)
5. Anterior Cingulate: HIGH_LOAD + HIGH_FATIGUE = conflict!
6. PFC (Deliberation): Choose strategy: DEFER_TO_REST
7. Basal Ganglia: Select action: REQUEST_USER_PREFERENCE
8. Hippocampus: Retrieve relevant memory
9. Broca's (LLM): Generate response with rich context
10. Motor: Execute (TTS output)

## Implementation Priority

1. **Thalamic Router** - Input classification and routing
2. **Working Memory** - Active workspace for processing
3. **Motor Planning** - Separate plan from execute
4. **Attention** - Focus mechanism

## Benefits

- **Better TTS**: Language production happens AFTER thinking
- **Clean Separation**: Each region has single job
- **Biologically Plausible**: Matches human brain
- **Emergent Consciousness**: From integration, not central control

**Key Insight**: We're building a BRAIN with language capability, not an AI using an LLM.
