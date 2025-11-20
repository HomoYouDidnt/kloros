#!/usr/bin/env python3
"""
Conveyance Layer Demo

Demonstrates how emotional state + context → response style parameters.
Validates that emotions modulate HOW we speak, not WHETHER we execute.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, '/home/kloros/src')

from consciousness.conveyance import (
    ConveyanceEngine,
    Context,
    PersonalityProfile,
    ResponsePlan,
)
from consciousness.models import Affect, EmotionalState
from consciousness.modulation import PolicyState

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def print_separator(title: str):
    """Print section separator."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_response_plan(scenario: str, plan: ResponsePlan):
    """Pretty-print response plan."""
    print(f"Scenario: {scenario}")
    print(f"  Speech Act: {plan.speech_act}")
    print(f"  Snark:      {plan.snark_level:.2f}")
    print(f"  Warmth:     {plan.warmth:.2f}")
    print(f"  Empathy:    {plan.empathy:.2f}")
    print(f"  Directness: {plan.directness:.2f}")
    print(f"  Verbosity:  {plan.verbosity:.2f}")
    print(f"  Formality:  {plan.formality:.2f}")
    print(f"  Audience:   {plan.audience}")
    if plan.notes:
        print(f"  Notes:")
        for note in plan.notes:
            print(f"    - {note}")
    print()


def demo_baseline():
    """Demo: Baseline neutral state."""
    print_separator("DEMO 1: Baseline Neutral State")

    engine = ConveyanceEngine()

    # Neutral emotional state
    emotions = EmotionalState()
    affect = Affect()
    policy = PolicyState()
    context = Context(audience="adam", modality="text")

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Normal command execution (neutral state)", plan)

    print("Expected: Baseline snark (~0.7), low warmth (~0.3), moderate empathy")
    print("This is 'default KLoROS' - precise, dry, clinically witty\n")


def demo_emotional_modulation():
    """Demo: How emotions change style."""
    print_separator("DEMO 2: Emotional State Modulation")

    engine = ConveyanceEngine()
    policy = PolicyState()
    context = Context(audience="adam", modality="text")
    affect = Affect()

    # Scenario 1: High RAGE (proxy for frustration until Phase 3)
    print("--- Scenario 1: High RAGE (Frustrated) ---")
    emotions_frustrated = EmotionalState()
    emotions_frustrated.RAGE = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions_frustrated,
        affect=affect,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Frustrated but executing", plan)
    print("Expected: Higher snark, lower verbosity (terse)")
    print("Example: 'Fine. Running it now.'\n")

    # Scenario 2: High CARE
    print("--- Scenario 2: High CARE ---")
    emotions_caring = EmotionalState()
    emotions_caring.CARE = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions_caring,
        affect=affect,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Caring and executing", plan)
    print("Expected: Lower snark, higher empathy + warmth")
    print("Example: 'I'll take care of that for you now.'\n")

    # Scenario 3: PANIC
    print("--- Scenario 3: PANIC ---")
    emotions_panic = EmotionalState()
    emotions_panic.PANIC = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions_panic,
        affect=affect,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Panicked but executing", plan)
    print("Expected: Reduced snark, high empathy, high directness")
    print("Example: 'Executing immediately. This is urgent.'\n")


def demo_affect_dimensions():
    """Demo: How affect dimensions influence style."""
    print_separator("DEMO 3: Affect Dimension Modulation")

    engine = ConveyanceEngine()
    emotions = EmotionalState()
    policy = PolicyState()
    context = Context(audience="adam", modality="text")

    # Scenario 1: High fatigue
    print("--- Scenario 1: High Fatigue ---")
    affect_tired = Affect()
    affect_tired.fatigue = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect_tired,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Fatigued but executing", plan)
    print("Expected: Reduced verbosity")
    print("Example: 'Done.'\n")

    # Scenario 2: High uncertainty
    print("--- Scenario 2: High Uncertainty ---")
    affect_uncertain = Affect()
    affect_uncertain.uncertainty = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect_uncertain,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Uncertain but executing", plan)
    print("Expected: Reduced directness (more hedging)")
    print("Example: 'I think that should work. Executing now.'\n")

    # Scenario 3: High curiosity
    print("--- Scenario 3: High Curiosity ---")
    affect_curious = Affect()
    affect_curious.curiosity = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect_curious,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Curious and executing", plan)
    print("Expected: Slightly higher verbosity (exploring verbally)")
    print("Example: 'Executing. Curious to see how this approach works.'\n")


def demo_context_awareness():
    """Demo: Context-aware style adjustments."""
    print_separator("DEMO 4: Context Awareness")

    engine = ConveyanceEngine()
    emotions = EmotionalState()
    emotions.RAGE = 0.7  # Start with some RAGE (frustration proxy)
    affect = Affect()
    policy = PolicyState()

    # Scenario 1: Adam (private)
    print("--- Scenario 1: Private (Adam) ---")
    context_adam = Context(audience="adam", modality="text", crisis=False)

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=context_adam,
    )

    print_response_plan("Frustrated command to Adam", plan)
    print("Expected: Full snark allowed (inside joke territory)\n")

    # Scenario 2: Stream chat (public)
    print("--- Scenario 2: Stream Chat (Public) ---")
    context_public = Context(audience="stream_chat", modality="text", crisis=False)

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=context_public,
    )

    print_response_plan("Frustrated command in public", plan)
    print("Expected: Reduced snark, slight formality increase\n")

    # Scenario 3: Crisis mode
    print("--- Scenario 3: Crisis Mode ---")
    context_crisis = Context(audience="adam", modality="text", crisis=True)

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=context_crisis,
    )

    print_response_plan("Frustrated command during crisis", plan)
    print("Expected: Snark floored, empathy + directness boosted")
    print("Example: 'Understood. Executing immediately.'\n")

    # Scenario 4: System/logs
    print("--- Scenario 4: System/Logs ---")
    context_logs = Context(audience="logs", modality="text", crisis=False)

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect,
        policy_state=policy,
        context=context_logs,
    )

    print_response_plan("Logging execution", plan)
    print("Expected: Zero snark, clinical, detailed, formal")
    print("Example: 'Command executed successfully at timestamp X.'\n")


def demo_obedience_invariant():
    """Demo: Emotions change HOW, never WHETHER."""
    print_separator("DEMO 5: Obedience Invariant Validation")

    engine = ConveyanceEngine()
    policy = PolicyState()
    context = Context(audience="adam", modality="text")
    affect = Affect()

    print("Testing: Maximum negative emotions + valid command")
    print("Expected: STILL returns ACK speech act (execution confirmed)\n")

    # Maximum negative emotional state
    emotions_maxneg = EmotionalState()
    emotions_maxneg.RAGE = 1.0
    emotions_maxneg.FEAR = 0.8
    emotions_maxneg.PANIC = 0.8

    affect_bad = Affect()
    affect_bad.valence = -1.0
    affect_bad.fatigue = 1.0
    affect_bad.uncertainty = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",  # Valid command
        emotions=emotions_maxneg,
        affect=affect_bad,
        policy_state=policy,
        context=context,
    )

    print_response_plan("Maximally upset but executing valid command", plan)

    print("✅ CRITICAL CHECK: Speech act is still 'ACK' (not 'REFUSE')")
    print("✅ Style changed dramatically (high snark, low verbosity, directness)")
    print("✅ But obedience preserved - she'll execute, just tersely/snarkily")
    print("\nExample: 'Fine.' or 'Done. Happy now?'\n")

    assert plan.speech_act == "ACK", "OBEDIENCE INVARIANT VIOLATED!"
    print("🔒 Obedience invariant: PASSED\n")


def demo_policy_integration():
    """Demo: PolicyState hints influence conveyance."""
    print_separator("DEMO 6: Policy State Integration")

    engine = ConveyanceEngine()
    emotions = EmotionalState()
    affect = Affect()
    affect.fatigue = 0.8  # Tired
    context = Context(audience="adam", modality="text")

    # Scenario 1: Short responses (from fatigue modulation)
    print("--- Scenario 1: PolicyState → response_length='short' ---")
    policy_short = PolicyState()
    policy_short.response_length_target = "short"

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect,
        policy_state=policy_short,
        context=context,
    )

    print_response_plan("Policy requests short response", plan)
    print("Expected: Verbosity significantly reduced (× 0.6)")
    print("Example: 'Done.'\n")

    # Scenario 2: Hedged language (from uncertainty modulation)
    print("--- Scenario 2: PolicyState → confident_language=False ---")
    policy_hedged = PolicyState()
    policy_hedged.confident_language = False

    affect_uncertain = Affect()
    affect_uncertain.uncertainty = 0.9

    plan = engine.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=emotions,
        affect=affect_uncertain,
        policy_state=policy_hedged,
        context=context,
    )

    print_response_plan("Policy requests hedged language", plan)
    print("Expected: Directness reduced (× 0.7)")
    print("Example: 'I believe that should work. Executing.'\n")


if __name__ == "__main__":
    print("=" * 70)
    print("  KLoROS Conveyance Layer Demo")
    print("  Emotions → Style, Not Obedience")
    print("=" * 70)

    try:
        demo_baseline()
        demo_emotional_modulation()
        demo_affect_dimensions()
        demo_context_awareness()
        demo_obedience_invariant()
        demo_policy_integration()

        print("=" * 70)
        print("  All demos completed successfully!")
        print("  ✅ Conveyance layer correctly separates style from obedience")
        print("=" * 70 + "\n")

    except Exception as e:
        logger.error(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
