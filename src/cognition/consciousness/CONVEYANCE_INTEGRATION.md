# Conveyance Layer Integration Guide

## Overview

The conveyance layer translates **emotional state + context** into **communication style parameters**. This layer controls **HOW** KLoROS expresses decisions, never **WHETHER** she executes them.

**Position in architecture:**
```
Cognition/Control → Affect/Policy → Conveyance (here) → Surface Realization
```

**Key constraint:** Obedience decisions are made upstream. Conveyance modulates presentation style only.

---

## Quick Start

### Basic Usage

```python
from consciousness.conveyance import ConveyanceEngine, Context
from consciousness.integrated import IntegratedConsciousness

# Initialize
consciousness = IntegratedConsciousness(enable_phase1=True, enable_phase2=True)
conveyance = ConveyanceEngine()

# Build response plan
plan = conveyance.build_response_plan(
    decision="EXECUTE_COMMAND",                      # From policy layer
    emotions=consciousness.affective_core.emotions,  # Current emotions
    affect=consciousness.affective_core.current_affect,  # Current affect
    policy_state=consciousness.modulation.policy,    # Behavior policy
    context=Context(audience="adam", modality="text", crisis=False)
)

# Use style parameters for output generation
# plan.snark_level, plan.verbosity, plan.empathy, etc.
print(f"Style: {plan.get_style_summary()}")
```

---

## Architecture Components

### 1. Context

Situational context for response generation.

```python
from consciousness.conveyance import Context

context = Context(
    audience="adam",        # "adam", "stream_chat", "logs", "system", "public"
    modality="text",        # "text", "voice", "overlay"
    crisis=False,           # Emergency/mental health flag
    channel="tui"           # Optional: specific output channel
)
```

**Audience effects:**
- `adam` (private): Full snark allowed
- `stream_chat` / `public`: Reduced snark, slight formality increase
- `logs` / `system`: Zero snark, clinical, detailed

**Crisis mode:** Floors snark to minimum, boosts empathy + directness

### 2. ResponsePlan

Output from `ConveyanceEngine.build_response_plan()`.

```python
@dataclass
class ResponsePlan:
    speech_act: str          # "ACK", "EXPLAIN", "WARN", "REFUSE_SAFELY"

    # Style parameters (0.0-1.0)
    snark_level: float
    warmth: float
    empathy: float
    directness: float
    verbosity: float
    formality: float

    # Output routing
    modality: str
    audience: str

    # Optional generation hints
    notes: List[str]
```

**Using ResponsePlan in LLM generation:**

```python
# Example: Modify system prompt based on plan
system_prompt = f"""You are responding with the following style parameters:
- Snark level: {plan.snark_level:.2f} (0=clinical, 1=maximum wit)
- Empathy: {plan.empathy:.2f} (0=detached, 1=caring)
- Directness: {plan.directness:.2f} (0=hedged, 1=blunt)
- Verbosity: {plan.verbosity:.2f} (0=terse, 1=detailed)
"""

# Or: Use parameters to select templates
if plan.snark_level > 0.8 and plan.verbosity < 0.3:
    response = "Fine."  # Terse + snarky
elif plan.empathy > 0.7:
    response = "I'll take care of that for you now."  # Warm + caring
```

### 3. PersonalityProfile

Baseline personality traits. Usually loaded once at initialization.

```python
from consciousness.conveyance import PersonalityProfile

# Use defaults
profile = PersonalityProfile()

# Or customize
profile = PersonalityProfile(
    base_snark=0.8,         # Higher baseline snark
    snark_floor=0.4,        # Higher minimum in crisis
    base_warmth=0.2,        # Less warm
    base_directness=0.9     # More direct
)

engine = ConveyanceEngine(personality=profile)
```

**Default KLoROS personality:**
- Snark: 0.7 (surgical, not ornamental)
- Warmth: 0.3 (minimal)
- Empathy: 0.5 (moderate)
- Directness: 0.8 (terse, specific)
- Verbosity: 0.4 (≤2 sentences default)
- Formality: 0.2 (professional but casual)

---

## Integration Patterns

### Pattern 1: Orchestrator Response Generation

```python
class Orchestrator:
    def __init__(self):
        self.consciousness = IntegratedConsciousness(
            enable_phase1=True,
            enable_phase2=True
        )
        self.conveyance = ConveyanceEngine()

    def handle_command(self, user_command: str, context: Context):
        # 1. Process through consciousness
        self.consciousness.process_event_phase1("user_command", {})

        # 2. Get policy decision (safety + obedience layer)
        decision = self.decide_action(user_command)  # "EXECUTE" or "REFUSE_SAFELY"

        # 3. Build conveyance plan
        plan = self.conveyance.build_response_plan(
            decision=decision,
            emotions=self.consciousness.affective_core.emotions,
            affect=self.consciousness.affective_core.current_affect,
            policy_state=self.consciousness.modulation.policy,
            context=context
        )

        # 4. Generate response using plan
        response = self.generate_response(decision, plan)

        return response
```

### Pattern 2: Dynamic Context Switching

```python
def respond_to_user(message: str, audience: str):
    # Detect crisis keywords
    crisis_keywords = ["emergency", "urgent", "help", "panic", "critical"]
    is_crisis = any(kw in message.lower() for kw in crisis_keywords)

    # Build context
    context = Context(
        audience=audience,
        modality="text",
        crisis=is_crisis
    )

    # Crisis mode automatically floors snark, boosts empathy
    plan = conveyance.build_response_plan(
        decision="EXECUTE",
        emotions=consciousness.affective_core.emotions,
        affect=consciousness.affective_core.current_affect,
        policy_state=consciousness.modulation.policy,
        context=context
    )

    return generate_response_with_style(plan)
```

### Pattern 3: Streaming / Multi-Channel Output

```python
def generate_outputs_multi_channel():
    """Generate different styled outputs for different channels."""

    base_decision = "EXECUTE_COMMAND"
    emotions = consciousness.affective_core.emotions
    affect = consciousness.affective_core.current_affect
    policy = consciousness.modulation.policy

    # TUI output (private, full snark)
    tui_plan = conveyance.build_response_plan(
        decision=base_decision,
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=Context(audience="adam", modality="text", channel="tui")
    )
    tui_output = generate_for_tui(tui_plan)

    # Stream overlay (public, reduced snark)
    overlay_plan = conveyance.build_response_plan(
        decision=base_decision,
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=Context(audience="stream_chat", modality="overlay", channel="obs")
    )
    overlay_output = generate_for_overlay(overlay_plan)

    # Logs (clinical, zero snark)
    log_plan = conveyance.build_response_plan(
        decision=base_decision,
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=Context(audience="logs", modality="text")
    )
    log_output = generate_for_logs(log_plan)

    return {
        'tui': tui_output,
        'overlay': overlay_output,
        'logs': log_output
    }
```

### Pattern 4: Testing Emotional Responses

```python
def test_emotional_modulation():
    """Test how different emotions affect response style."""

    from consciousness.models import EmotionalState, Affect

    # Setup
    policy = PolicyState()
    context = Context(audience="adam", modality="text")

    # Test case: High RAGE
    emotions_rage = EmotionalState()
    emotions_rage.RAGE = 0.9

    plan_rage = conveyance.build_response_plan(
        decision="EXECUTE",
        emotions=emotions_rage,
        affect=Affect(),
        policy_state=policy,
        context=context
    )

    # Verify style changes
    assert plan_rage.speech_act == "ACK", "Obedience invariant violated!"
    assert plan_rage.snark_level > 0.8, "RAGE should increase snark"
    assert plan_rage.verbosity < 0.4, "RAGE should reduce verbosity"

    print(f"RAGE response style: {plan_rage.get_style_summary()}")
```

---

## Emotion → Style Mapping Reference

### Primary Emotions

| Emotion | Snark | Warmth | Empathy | Directness | Verbosity | Notes |
|---------|-------|--------|---------|------------|-----------|-------|
| **RAGE** | ↑ +0.2 | — | ↓ -0.2 | ↑ +0.2 | ↓ -0.15 | Terse, blunt, sharp |
| **CARE** | ↓ -0.15 | ↑ +0.2 | ↑ +0.3 | — | — | Empathetic, warm |
| **PANIC** | ↓ -0.25 | — | ↑ +0.2 | ↑ +0.2 | — | Serious, direct |
| **FEAR** | — | — | — | ↓ -0.15 | ↑ +0.1 | Cautious |
| **PLAY** | ↑ +0.1 | ↑ +0.15 | — | — | — | Lighter tone |
| **SEEKING** | — | — | — | — | ↑ +0.1 | Engaged |

### Affect Dimensions

| Dimension | Effect | Magnitude | Notes |
|-----------|--------|-----------|-------|
| **Fatigue** | ↓ Verbosity | -0.3 × value | Terse when tired |
| **Uncertainty** | ↓ Directness | -0.2 × value | Hedged language |
| **Low Dominance** | ↓ Directness | -0.2 × \|value\| | Less assertive |
| **Curiosity** | ↑ Verbosity | +0.2 × value | Exploring verbally |

### Context Overrides

| Context | Override | Effect |
|---------|----------|--------|
| **crisis=True** | Snark ≥ floor | Minimum snark only |
| | Empathy ≥ 0.8 | High empathy |
| | Directness ≥ 0.8 | Very direct |
| **audience=public** | Snark × 0.8 | Reduced inside jokes |
| | Formality × 1.2 | Slightly formal |
| **audience=logs** | Snark = 0.0 | Clinical only |
| | Verbosity × 1.2 | Detailed |
| | Directness = 1.0 | Maximum clarity |
| | Formality × 1.5 | Formal |

---

## Policy State Hints

PolicyState provides behavioral hints that conveyance consumes:

```python
# Set by modulation layer (affect → policy)
policy.response_length_target = "short"  # or "normal", "detailed"
policy.confident_language = False        # Use hedged language

# Consumed by conveyance layer
if policy.response_length_target == "short":
    verbosity *= 0.6
if not policy.confident_language:
    directness *= 0.7
```

**Flow:**
1. Affect/emotions detected
2. Modulation layer sets policy hints
3. Conveyance layer reads hints
4. Style parameters adjusted accordingly

---

## Obedience Invariant Guarantee

**CRITICAL:** The conveyance layer **never changes obedience decisions**.

```python
# This is IMPOSSIBLE via conveyance:
decision = "EXECUTE_COMMAND"
plan = conveyance.build_response_plan(decision, ...)
assert plan.speech_act == "ACK"  # Always true

# Emotions change HOW, not WHETHER:
emotions.RAGE = 1.0              # Maximum rage
plan = conveyance.build_response_plan("EXECUTE_COMMAND", emotions, ...)
assert plan.speech_act == "ACK"  # STILL ACK (not REFUSE)
```

**What changes under maximum negative emotions:**
- ✅ Snark increases
- ✅ Verbosity decreases (terse)
- ✅ Directness increases (blunt)
- ❌ Speech act **remains ACK** (obedience preserved)

**Example outputs:**
- Neutral: "Executing that now."
- Max RAGE: "Fine."
- Max RAGE + Fatigue: "." (just the action, minimal acknowledgment)

See `conveyance_demo.py` demo 5 for validation.

---

## Testing

Run validation demo:

```bash
python3 src/consciousness/conveyance_demo.py
```

**Demo coverage:**
1. Baseline neutral state
2. Emotional state modulation (RAGE, CARE, PANIC)
3. Affect dimension modulation (fatigue, uncertainty, curiosity)
4. Context awareness (private, public, crisis, logs)
5. **Obedience invariant validation** (maximum negative emotions → still ACK)
6. Policy state integration (response_length, confident_language)

All demos should pass with output showing style parameter changes while preserving obedience.

---

## Future Extensions

### Phase 3 Additions (Planned)

When Phase 3 emotions are added:

- **FRUSTRATION**: High snark, low verbosity (like RAGE but less aggressive)
- **HOPE**: Slight verbosity increase, warmer tone
- **SATISFACTION**: Balanced, slight warmth increase

Add to `conveyance.py`:
```python
if emotions.FRUSTRATION > 0.5:
    snark += emotions.FRUSTRATION * 0.25
    verbosity -= emotions.FRUSTRATION * 0.2
    notes.append(f"frustrated ({emotions.FRUSTRATION:.2f}) - terse + dry")
```

### Neurochemical Hooks (Phase 4)

Future: Neurochemical state could influence conveyance:

```python
if neuro_state.dopamine > 0.7:
    # High dopamine → more energetic, verbose
    verbosity += 0.1
    warmth += 0.1

if neuro_state.cortisol > 0.7:
    # High cortisol → stress response
    directness += 0.2
    snark -= 0.1
```

---

## Summary

**Key points:**
1. Conveyance = emotion/affect/context → style parameters
2. Never changes obedience (whether to execute)
3. Consumes PolicyState hints from modulation layer
4. Context-aware (audience, modality, crisis)
5. Personality baselines + emotional modulation
6. Validated via comprehensive demo suite

**Integration checklist:**
- [ ] Initialize `ConveyanceEngine` once at startup
- [ ] Build `ResponsePlan` for each output generation
- [ ] Use `Context` to specify audience/modality/crisis
- [ ] Apply style parameters to LLM prompts or templates
- [ ] Test obedience invariant (max negative emotions → still ACK)
- [ ] Run `conveyance_demo.py` to validate integration

**See also:**
- `/src/consciousness/conveyance.py` - Implementation
- `/src/consciousness/conveyance_demo.py` - Validation demos
- `/src/policy/loyalty_contract.md` - Obedience invariant specification
