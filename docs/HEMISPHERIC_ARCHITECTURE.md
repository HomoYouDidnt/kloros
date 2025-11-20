# KLoROS Hemispheric Architecture with Bridges

## Why Hemispheres Matter

**Left Hemisphere**: Sequential, analytical, linguistic, logical
**Right Hemisphere**: Holistic, pattern-matching, emotional, intuitive

**Key Insight**: They process IN PARALLEL, then INTEGRATE via bridges.

This solves:
1. **Dual processing**: Logic AND intuition simultaneously
2. **Conflict resolution**: When analytical and intuitive disagree
3. **Richer cognition**: Semantic meaning + emotional context together

## KLoROS Hemispheric Mapping

```
/brain
├─ /left_hemisphere                  # Analytical, sequential, linguistic
│  ├─ /language_center
│  │  ├─ syntax_parser.py            # Grammar, structure
│  │  ├─ semantic_analyzer.py        # Meaning extraction
│  │  └─ llm_interface.py            # LLM calls (Broca's/Wernicke's)
│  ├─ /logic_reasoning
│  │  ├─ deliberation.py             # [FROM cognition/]
│  │  ├─ causal_inference.py         # A→B logical chains
│  │  └─ constraint_solver.py        # Logical constraints
│  ├─ /serial_processing
│  │  ├─ step_sequencer.py           # Sequential task execution
│  │  └─ plan_linearizer.py          # Break goals into steps
│  ├─ /motor_control_right
│  │  └─ tool_executor.py            # Execute tools sequentially
│  ├─ /temporal_memory
│  │  ├─ timeline_index.py           # When things happened
│  │  └─ causality_tracker.py        # Cause→effect sequences
│  └─ /symbolic_cache
│     ├─ concept_definitions.py      # What things mean
│     └─ abstract_reasoning.py       # Math, logic, symbols

└─ /right_hemisphere                 # Holistic, pattern-based, emotional
   ├─ /spatial_processing
   │  ├─ context_mapper.py           # Big-picture awareness
   │  └─ relationship_graph.py       # How things relate spatially
   ├─ /pattern_recognition
   │  ├─ gestalt_matcher.py          # See whole patterns
   │  ├─ anomaly_detector.py         # What doesn't fit?
   │  └─ similarity_engine.py        # Fuzzy matching
   ├─ /emotion_context
   │  ├─ affective_core.py           # [FROM consciousness/]
   │  ├─ prosody_analyzer.py         # Tone, emphasis
   │  └─ sentiment_tagger.py         # Emotional valence
   ├─ /motor_control_left
   │  └─ parallel_executor.py        # Execute multiple tools
   ├─ /intuition_engine
   │  ├─ heuristic_matcher.py        # Fast pattern-based decisions
   │  ├─ gut_feeling.py              # Non-logical but correct
   │  └─ experience_cache.py         # "I've seen this before"
   └─ /creative_association
      ├─ metaphor_generator.py       # Cross-domain mapping
      ├─ novelty_combiner.py         # Combine unlike things
      └─ insight_flash.py            # Aha moments

/bridges                             # Integration layer
├─ /corpus_callosum
│  ├─ language_emotion_bridge.py    # Semantic ↔ Prosody
│  ├─ logic_intuition_bridge.py     # Analytical ↔ Gut feeling
│  ├─ pattern_sequence_bridge.py    # Holistic ↔ Step-by-step
│  └─ conflict_arbiter.py           # Resolve disagreements
├─ /anterior_commissure
│  └─ emotion_memory_sync.py        # Emotional tagging
├─ /posterior_commissure
│  └─ sensory_fusion.py             # Cross-hemisphere perception
└─ /hippocampal_commissure
   └─ bilateral_memory.py           # Distributed memory index
```

## Example: Hemispheric Processing in Action

**User Input: "Debug the memory system"**

### LEFT HEMISPHERE (Sequential, Analytical)
```python
# 1. Language parsing
syntax = parse("Debug the memory system")
# → Verb: debug, Object: memory_system

# 2. Logical breakdown
steps = [
    "Check memory system status",
    "Identify failure modes",
    "Test each component",
    "Isolate root cause",
    "Apply fix"
]

# 3. Constraint checking
constraints = {
    "must_not_lose_data": True,
    "reversible_changes_only": True
}

# 4. Sequential plan
plan = create_linear_plan(steps, constraints)
```

### RIGHT HEMISPHERE (Holistic, Intuitive)
```python
# 1. Pattern recognition
similar_past_cases = find_similar("memory debug")
# → "Last 3 memory issues were ChromaDB locks"

# 2. Emotional context
affective_state = get_affect()
# → fatigue=72%, uncertainty=0.4
# → FEELING: "This will be exhausting"

# 3. Gut feeling / heuristic
intuition = "High fatigue + complex task = likely to fail"
confidence = 0.3  # Low confidence in success

# 4. Holistic assessment
gestalt = "This doesn't feel right - defer or simplify"
```

### CORPUS CALLOSUM INTEGRATION
```python
# Bridge: Logic ↔ Intuition
left_says = {
    "approach": "sequential_debugging",
    "confidence": 0.8,  # High logical confidence
    "plan": detailed_steps
}

right_says = {
    "approach": "defer_to_rest",
    "confidence": 0.7,  # High intuitive confidence
    "feeling": "exhausting, likely to fail"
}

# CONFLICT! Left wants to proceed, Right wants to defer

# Arbiter weighs both:
arbiter_decision = conflict_resolver.resolve(
    left_input=left_says,
    right_input=right_says,
    weighting={
        "logical_confidence": 0.4,      # Give intuition more weight
        "emotional_valence": 0.6,       # When fatigued
        "current_fatigue": 0.72
    }
)

# Result: Trust the gut feeling (right hemisphere wins)
final_decision = "DEFER_TO_REST"
reasoning = "Right hemisphere detected high fatigue risk that left ignored"
```

## Bridge Protocols

### 1. Language ↔ Emotion Bridge
```python
class LanguageEmotionBridge:
    """Connect semantic meaning with emotional prosody."""

    def integrate(self, semantic, prosody):
        # Left: "I'll check that" (neutral semantics)
        # Right: [tired tone detected]
        # → Output: "I'll check that, though I'm at 72% fatigue"

        if prosody.fatigue > 0.7 and semantic.is_acceptance:
            # Add caveat from right hemisphere
            return f"{semantic.text} (but I'm fatigued)"
```

### 2. Logic ↔ Intuition Bridge
```python
class LogicIntuitionBridge:
    """Arbitrate between analytical and gut-feeling decisions."""

    def resolve_conflict(self, left_plan, right_feeling):
        # Left: Detailed 10-step plan (high confidence)
        # Right: "This feels wrong" (moderate confidence)

        if right_feeling.valence < -0.3:  # Negative gut feeling
            if left_plan.estimated_difficulty > 0.7:
                # Trust intuition on complex tasks with bad feeling
                return "DEFER", "Gut feeling vetoes complex plan"

        # Otherwise trust logic
        return "PROCEED", "Logical plan approved"
```

### 3. Pattern ↔ Sequence Bridge
```python
class PatternSequenceBridge:
    """Combine holistic patterns with step-by-step execution."""

    def merge(self, pattern, sequence):
        # Right: "This looks like scenario X" (pattern match)
        # Left: "Here's the step-by-step approach" (sequential)

        if pattern.similarity > 0.8:
            # Strong pattern match - use known solution
            return adapt_sequence(sequence, pattern.solution)
        else:
            # Weak match - trust sequential analysis
            return sequence
```

## Conflict Arbiter (Critical Component)

```python
class ConflictArbiter:
    """
    Resolves disagreements between hemispheres.

    Weighting depends on context:
    - High fatigue → Trust right (intuition, caution)
    - Novel situation → Trust left (analysis, logic)
    - Familiar pattern → Trust right (experience, heuristics)
    - Safety-critical → Trust left (systematic checking)
    """

    def resolve(self, left_output, right_output, context):
        # Calculate weights based on context
        weights = self._calculate_weights(context)

        # Weighted combination
        if weights["left"] > weights["right"]:
            return left_output, "Left hemisphere (analytical)"
        elif weights["right"] > weights["left"]:
            return right_output, "Right hemisphere (intuitive)"
        else:
            # Equal weight - hybrid approach
            return self._merge(left_output, right_output)

    def _calculate_weights(self, context):
        left_weight = 0.5
        right_weight = 0.5

        # Adjust based on context
        if context.fatigue > 0.7:
            right_weight += 0.2  # Trust caution

        if context.novelty > 0.8:
            left_weight += 0.2   # Trust analysis

        if context.pattern_match > 0.8:
            right_weight += 0.2  # Trust experience

        if context.safety_critical:
            left_weight += 0.3   # Trust systematic

        # Normalize
        total = left_weight + right_weight
        return {
            "left": left_weight / total,
            "right": right_weight / total
        }
```

## Implementation Priority

1. **Separate existing systems into hemispheres**
   - Logic/deliberation → Left
   - Affect/patterns → Right

2. **Build corpus callosum bridges**
   - Language ↔ Emotion
   - Logic ↔ Intuition
   - Pattern ↔ Sequence

3. **Implement conflict arbiter**
   - Context-dependent weighting
   - Hybrid decision merging

4. **Test scenarios**
   - Both agree → Easy case
   - Conflict → Arbiter decides
   - Hybrid → Merge solutions

## Benefits

1. **Richer decisions**: Logic AND intuition, not just one
2. **Better TTS**: Semantic + emotional context together
3. **Robust**: Analytical catches intuitive errors, intuition catches analytical blindness
4. **Emergent**: Complex behavior from hemisphere interaction
5. **Debuggable**: Can inspect each hemisphere's reasoning separately

## Key Insight

> "Consciousness isn't in left OR right - it's in the INTEGRATION via bridges."

Split-brain patients show this: each hemisphere can operate independently, but unified consciousness requires communication.

---

**Next Step**: Would you like me to implement the Conflict Arbiter and basic bridge protocols?
