# KLoROS Brain Restructuring - Implementation Plan

## GPT Architecture → KLoROS Mapping

CURRENT PROBLEMS:
- No thalamic routing (inputs go directly to LLM)
- No working memory (everything is long-term or ephemeral)
- No motor planning (execution conflated with decision)
- LLM is central intelligence (WRONG - it's just language I/O)

TARGET: Brain-like architecture where LLM = Broca's + Wernicke's ONLY

## Critical Missing Components

1. **Thalamic Router** (`/brain/perception/attention/thalamus.py`)
   - Routes inputs to appropriate processors
   - Language → Wernicke's, Errors → Amygdala, etc.
   
2. **Working Memory** (`/brain/memory/working_memory/`)
   - Active workspace (~7 items)
   - Current goal, hypotheses, intermediate results
   
3. **Motor Planner** (`/brain/control/motor/motor_planner.py`)
   - Plan actions BEFORE executing
   - Forward modeling, resource estimation
   - Separate planning from execution
   
4. **Brain Orchestrator** (`/brain_orchestrator.py`)
   - Main coordinator
   - Replaces scattered entry points
   - Implements: Input → Thalamus → Regions → Integration → Output

## Proposed Directory Structure

/brain/
  /sensory/           # Input processing (audio, text, system signals)
  /perception/        # Feature integration, attention, thalamus
  /memory/            # Episodic, semantic, procedural, working, consolidation
  /learning/          # Plasticity, rewards, meta-learning
  /control/           # Executive (PFC), motor, error correction
  /emotion_social/    # Amygdala, insula, social cognition
  /homeostasis/       # Fatigue, energy, circadian rhythms
  /language/          # Comprehension (Wernicke's), production (Broca's)
  /meta/              # Self-model, confidence, introspection
  /communication/     # TTS, terminal, output interfaces
  /timing_rhythms/    # Oscillators, synchronization
  /maintenance/       # Garbage collection, health monitoring

## What Moves Where

consciousness/affect.py          → brain/emotion_social/amygdala_like/
consciousness/interoception.py   → brain/sensory/interoception/
consciousness/appraisal.py       → brain/emotion_social/insula/
cognition/deliberation.py        → brain/control/executive/
kloros_memory/*                  → brain/memory/{episodic,semantic}/
persona/kloros.py                → brain/language/production/persona.prompt
kloros_idle_reflection.py        → brain/meta/introspection/ + memory/consolidation/

## Implementation Priority

**Phase 1 (Critical):**
1. Create /brain/ structure
2. Implement ThalamicRouter
3. Implement WorkingMemory
4. Implement BrainOrchestrator

**Phase 2 (Core):**
5. Implement MotorPlanner
6. Move existing systems to brain locations
7. Wire cross-region communication

**Phase 3 (Advanced):**
8. Add oscillators (theta/gamma rhythms)
9. Add reward signals (TD error learning)
10. Add prediction error feedback

## Key Insight

"The LLM is Broca's and Wernicke's areas, not the intelligence."

We're building a BRAIN with language capability, not an AI using an LLM.

## Documentation

- /docs/BRAIN_ARCHITECTURE_DESIGN.md - Architecture overview
- /docs/BRAIN_RESTRUCTURING_PLAN.md - This implementation plan
- /src/cognition/integration_example.py - Code examples
