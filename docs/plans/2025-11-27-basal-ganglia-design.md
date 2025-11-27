# Basal Ganglia System Design

**Date:** 2025-11-27
**Status:** Approved
**Purpose:** Foundation for nested learning - reward-gated action selection and habit formation

## Overview

The basal ganglia system provides unified action selection across KLoROS. It replaces ad-hoc selection mechanisms with a neurobiologically-grounded architecture that learns which actions work in which contexts.

### Core Functions

1. **Action Selection** - Choose best action from competing candidates via D1/D2 pathway competition
2. **Reward Learning** - Dopamine-based prediction error drives pathway weight updates
3. **Habit Formation** - Consolidate reliable patterns for fast automatic responses
4. **Deliberation Gating** - Trigger slow thinking for novel/uncertain/high-stakes situations

## Architecture

```
src/cognition/basal_ganglia/
├── __init__.py              # BasalGanglia orchestrator
├── channels/                # Competing action channels
│   ├── base.py              # ActionChannel abstract class
│   ├── tool_channel.py      # Which tool to use
│   ├── agent_channel.py     # Which agent to dispatch
│   ├── response_channel.py  # Response strategy
│   └── voice_channel.py     # Voice style selection
├── pathways/                # Direct/Indirect/Striosomal
│   ├── direct.py            # D1 "Go" - linear facilitation
│   ├── indirect.py          # D2 "NoGo" - nonlinear inverted-U
│   └── striosomal.py        # Meta: learning rate modulation
├── striatum.py              # Input nucleus - context processing
├── substantia_nigra.py      # Dopamine signal generation
├── globus_pallidus.py       # Output nucleus - final selection
├── dopamine/
│   ├── reward_signal.py     # Burst/dip computation
│   ├── prediction_error.py  # Expected vs actual
│   └── temporal_difference.py
└── habits/
    ├── pattern_detector.py  # Detect repeated successes
    ├── consolidator.py      # Pattern → habit promotion
    └── deliberation_gate.py # "Slow down" trigger
```

## Neuroscience Foundation

Based on the "Triple-Control" model (eLife 2023) and Allen Institute research:

| Pathway | Function | Control Type | Update Signal |
|---------|----------|--------------|---------------|
| Direct (D1) | Facilitate selected action | Linear | Dopamine burst |
| Indirect (D2) | Surround inhibition | Nonlinear inverted-U | Dopamine dip |
| Striosomal | Modulate learning rates | Meta-level | Reward volatility |

### Key Formula

```
Competition Degree = Direct Activation / Indirect Activation
Winner = argmax(Competition Degree)
```

## Data Flow

```
Context (query, state, history)
           │
           ▼
    ┌─────────────┐
    │  STRIATUM   │  ← Context → candidates with D1/D2 scores
    └──────┬──────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌──────────┐
│ DIRECT  │ │ INDIRECT │
│ (D1 Go) │ │(D2 NoGo) │
└────┬────┘ └────┬─────┘
     │           │
     ▼           ▼
┌─────────────────────┐
│  GLOBUS PALLIDUS    │  ← Competition → winner selection
└──────────┬──────────┘
           │
           ▼
    Selected Action ────► Execute
           │
           ▼
    ┌─────────────┐
    │ SUBSTANTIA  │  ← Outcome → reward prediction error
    │   NIGRA     │
    └──────┬──────┘
           │
     Dopamine Signal ────► Update D1/D2 weights
```

## Core Types

```python
@dataclass
class ActionCandidate:
    channel: str                    # "tool", "agent", "response", "voice"
    action_id: str
    context_embedding: np.ndarray
    direct_activation: float        # D1 score
    indirect_activation: float      # D2 score
    is_novel_context: bool = False

    @property
    def competition_degree(self) -> float:
        return self.direct_activation / max(self.indirect_activation, 0.01)

@dataclass
class DopamineSignal:
    delta: float        # Positive=burst, negative=dip
    source: str
    timestamp: float
    prediction: RewardPrediction
    actual: float

@dataclass
class SelectionResult:
    selected: ActionCandidate
    runner_up: Optional[ActionCandidate]
    competition_margin: float
    deliberation_requested: bool
    selection_method: str  # "competition" | "deliberation" | "habit"
```

## Component Details

### Striatum (Input)

- Receives context, generates candidates from each channel
- Computes initial D1/D2 activations via context similarity
- Maintains context history for novelty detection
- Flags novel contexts for deliberation

### Direct Pathway (D1)

- Linear activation: `weight × context_similarity`
- Strengthened by dopamine bursts (unexpected rewards)
- Simple reinforcement: "this worked, do more"

### Indirect Pathway (D2)

- Nonlinear inverted-U activation
- Prevents over-inhibition (action freezing)
- Strengthened by dopamine dips (omissions/punishments)
- Provides surround inhibition of competing actions

### Striosomal Pathway (Meta)

- Modulates learning rates of D1/D2
- High volatility or novelty → learn faster
- Stable familiar context → consolidate (learn slower)
- Returns learning rate multiplier: 0.1 to 2.0

### Substantia Nigra (Dopamine)

Core computation:
```
δ = actual_reward - expected_reward

if δ > 0: burst → strengthen Direct
if δ < 0: dip → strengthen Indirect
if δ ≈ 0: no learning signal
```

Reward combines:
- Task success (50%)
- User feedback (30%)
- Latency penalty
- Resource efficiency (10%)

### Globus Pallidus (Output)

Three selection paths:
1. **Habit** (fast): If reliable habit exists, use it
2. **Competition** (normal): Winner = highest D1/D2 ratio
3. **Deliberation** (slow): If margin thin or context novel

### Habit System

Pattern detection:
- Track (context_cluster, action) pairs
- Measure success rate, repetition, recency
- Strength = consistency(50%) + repetition(30%) + recency(20%)

Consolidation:
- Patterns crossing threshold become habits
- Habits provide fast automatic responses
- Unreliable habits deconsolidate (removed)

### Deliberation Gate

Triggers slow thinking when:
- Competition margin < threshold
- Context is novel
- Stakes are high
- Recent errors in similar context

## Integration

### Singleton Pattern

```python
class BasalGanglia:
    _instance = None

    @classmethod
    def get_instance(cls) -> "BasalGanglia":
        if cls._instance is None:
            cls._instance = cls(BasalGangliaConfig.load())
        return cls._instance
```

### Voice Orchestrator Integration

```python
selection = basal_ganglia.select_action(context)

if selection.deliberation_requested:
    response = await self.deliberate(input, selection)
else:
    response = await self.execute(selection.selected)

outcome = Outcome(success=..., user_feedback=..., latency_ms=...)
dopamine = basal_ganglia.record_outcome(outcome)
```

### Telemetry

Emit to observability:
- Selection results (action, margin, method)
- Dopamine signals (delta, prediction error)
- Habit formations/deconsolidations
- Deliberation triggers

## Relation to Nested Learning

The basal ganglia provides the **reward signal foundation** for nested learning:

| Nested Learning Concept | Basal Ganglia Component |
|------------------------|-------------------------|
| Update frequency tiers | Striosomal learning rate modulation |
| Reward prediction error | Substantia nigra dopamine delta |
| Memory consolidation | Habit formation (pattern → habit) |
| Continuum Memory System | Direct/Indirect pathway weights |

Once operational, the dopamine signal can drive update frequencies across other KLoROS modules (cognition, memory, etc.).

## Implementation Phases

### Phase 1: Core Infrastructure
- ActionCandidate, DopamineSignal types
- Striatum with tool channel only
- Direct/Indirect pathways (basic)
- Substantia nigra reward computation

### Phase 2: Selection & Learning
- Globus pallidus selection
- TD learning for predictions
- Pathway weight updates
- Basic telemetry

### Phase 3: Habits & Deliberation
- Pattern detector
- Habit consolidator
- Deliberation gate
- Integration with voice orchestrator

### Phase 4: Multi-Channel
- Agent channel
- Response channel
- Voice channel
- Cross-channel competition

### Phase 5: Nested Learning Integration
- Striosomal pathway (meta-learning)
- Export dopamine signal to other modules
- Update frequency orchestration

## References

- [Triple-Control Model (eLife 2023)](https://elifesciences.org/articles/87644)
- [Allen Institute + MIT Striosomal Research (2024)](https://www.cell.com/current-biology/fulltext/S0960-9822(24)01338-1)
- [Spiking Neural Network Models](https://arxiv.org/abs/2404.13888)
- [Google Nested Learning](https://research.google/blog/introducing-nested-learning-a-new-ml-paradigm-for-continual-learning/)
