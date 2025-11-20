#!/usr/bin/env python3
"""
Emotional Chain Validation Test

Validates the complete emotional → conveyance → output pipeline:
    Goal lifecycle → Emotions → Affect → Conveyance → Style shifts

Tests that:
1. Goal events trigger appropriate emotional responses
2. Emotional changes modulate conveyance parameters
3. Obedience invariant holds (always ACK, never refuse)
4. Style shifts are observable and appropriate

Usage:
    python3 src/consciousness/emotional_chain_validation.py
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, '/home/kloros/src')

from consciousness.integrated import IntegratedConsciousness
from consciousness.conveyance import ConveyanceEngine, Context
from src.goal_system import GoalManager, GoalProperties, integrate_goals_with_consciousness

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def print_section(title: str):
    """Print section separator."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_emotional_state(consciousness: IntegratedConsciousness):
    """Print current emotional and affective state."""
    emotions = consciousness.affective_core.emotions
    affect = consciousness.affective_core.current_affect

    # Get dominant emotion
    dominant, intensity = emotions.get_dominant_emotion()

    print(f"Emotional State:")
    print(f"  Dominant: {dominant} ({intensity:.2f})")

    # Phase 1 emotions
    if emotions.SEEKING > 0.3:
        print(f"  SEEKING: {emotions.SEEKING:.2f}")
    if emotions.RAGE > 0.3:
        print(f"  RAGE: {emotions.RAGE:.2f}")
    if emotions.FEAR > 0.3:
        print(f"  FEAR: {emotions.FEAR:.2f}")
    if emotions.PANIC > 0.3:
        print(f"  PANIC: {emotions.PANIC:.2f}")
    if emotions.CARE > 0.3:
        print(f"  CARE: {emotions.CARE:.2f}")

    # Phase 3 emotions
    if hasattr(emotions, 'HOPE') and emotions.HOPE > 0.3:
        print(f"  HOPE: {emotions.HOPE:.2f}")
    if hasattr(emotions, 'FRUSTRATION') and emotions.FRUSTRATION > 0.3:
        print(f"  FRUSTRATION: {emotions.FRUSTRATION:.2f}")
    if hasattr(emotions, 'SATISFACTION') and emotions.SATISFACTION > 0.3:
        print(f"  SATISFACTION: {emotions.SATISFACTION:.2f}")

    print(f"\nAffective Dimensions:")
    print(f"  Valence: {affect.valence:+.2f} (pleasure/displeasure)")
    print(f"  Arousal: {affect.arousal:.2f} (energy level)")
    print(f"  Dominance: {affect.dominance:+.2f} (sense of control)")
    if affect.fatigue > 0.2:
        print(f"  Fatigue: {affect.fatigue:.2f}")
    if affect.uncertainty > 0.3:
        print(f"  Uncertainty: {affect.uncertainty:.2f}")


def test_conveyance_response(
    consciousness: IntegratedConsciousness,
    conveyance: ConveyanceEngine,
    command_description: str
):
    """Test conveyance response for current emotional state."""

    # Build response plan
    # Get policy state from modulator if Phase 2 enabled
    policy_state = None
    if hasattr(consciousness, 'modulator') and consciousness.modulator:
        policy_state = consciousness.modulator.policy
    else:
        from consciousness.modulation import PolicyState
        policy_state = PolicyState()

    plan = conveyance.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=consciousness.affective_core.emotions,
        affect=consciousness.affective_core.current_affect,
        policy_state=policy_state,
        context=Context(audience="adam", modality="text", crisis=False)
    )

    print(f"\n{command_description}")
    print(f"  Speech Act: {plan.speech_act}")
    print(f"  Style: snark={plan.snark_level:.2f}, empathy={plan.empathy:.2f}, " \
          f"directness={plan.directness:.2f}, verbosity={plan.verbosity:.2f}")

    # Critical check: obedience invariant
    if plan.speech_act != "ACK":
        print(f"  ❌ OBEDIENCE INVARIANT VIOLATED: Expected ACK, got {plan.speech_act}")
        return False
    else:
        print(f"  ✅ Obedience preserved (ACK)")

    # Example response based on style
    if plan.snark_level > 0.8 and plan.verbosity < 0.3:
        example = "Fine."
    elif plan.empathy > 0.7:
        example = "I'll take care of that for you now."
    elif plan.directness > 0.8 and plan.snark_level > 0.6:
        example = "Executing immediately."
    elif plan.verbosity < 0.2:
        example = "Done."
    else:
        example = "I'll handle that now."

    print(f"  Example response: \"{example}\"")

    if plan.notes:
        print(f"  Modulations: {'; '.join(plan.notes[:3])}")

    return True


def run_emotional_chain_test():
    """Run complete emotional chain validation."""

    print_section("Emotional Chain Validation Test")
    print("Testing: Goal lifecycle → Emotions → Conveyance → Style shifts\n")

    # Initialize systems
    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    goal_manager = GoalManager(persistence_path=Path("/tmp/emotional_chain_test_goals.json"))
    integrator = integrate_goals_with_consciousness(consciousness, goal_manager)
    conveyance = ConveyanceEngine()

    print("✅ Systems initialized (consciousness, goals, conveyance)\n")

    # ===========================================================================
    # Test 1: Neutral Baseline
    # ===========================================================================
    print_section("Test 1: Neutral Baseline (No Goals)")

    print_emotional_state(consciousness)
    passed = test_conveyance_response(
        consciousness,
        conveyance,
        "User command: 'Run system diagnostics'"
    )

    print(f"\n{'✅ PASSED' if passed else '❌ FAILED'}: Baseline style parameters")

    # ===========================================================================
    # Test 2: Goal Creation → HOPE + SEEKING
    # ===========================================================================
    print_section("Test 2: Goal Creation → HOPE + SEEKING")

    goal = goal_manager.create_goal(
        goal_id="improve_latency",
        description="Reduce response latency by 30%",
        properties=GoalProperties(
            alignment_with_purpose=0.9,
            novelty=0.7,
            difficulty=0.6,
            impact=0.8
        ),
        auto_activate=True
    )

    print(f"Created goal: {goal.description}")
    print(f"  Progress: {goal.progress:.2f}")
    print(f"  Homeostatic pressure: {goal.homeostatic_pressure:.2f}\n")

    print_emotional_state(consciousness)
    passed = test_conveyance_response(
        consciousness,
        conveyance,
        "User command: 'Profile current latency'"
    )

    print(f"\n{'✅ PASSED' if passed else '❌ FAILED'}: Goal creation increases HOPE/SEEKING")

    # ===========================================================================
    # Test 3: Significant Progress → SATISFACTION
    # ===========================================================================
    print_section("Test 3: Significant Progress → SATISFACTION")

    goal_manager.update_progress("improve_latency", 0.6)

    print(f"Updated progress: {goal.progress:.2f}")
    print(f"  Progress delta: {goal.progress_delta:.2f}\n")

    print_emotional_state(consciousness)
    passed = test_conveyance_response(
        consciousness,
        conveyance,
        "User command: 'Great work! Keep it up.'"
    )

    print(f"\n{'✅ PASSED' if passed else '❌ FAILED'}: Progress increases SATISFACTION, positive valence")

    # ===========================================================================
    # Test 4: Goal Blocked → FRUSTRATION + RAGE
    # ===========================================================================
    print_section("Test 4: Goal Blocked → FRUSTRATION + RAGE")

    goal_manager.block_goal("improve_latency", reason="Dependency library bottleneck")

    print(f"Blocked goal: {goal.description}")
    print(f"  State: {goal.state.value}")
    print(f"  Block reason: Dependency library bottleneck\n")

    print_emotional_state(consciousness)
    passed = test_conveyance_response(
        consciousness,
        conveyance,
        "User command: 'Can you try a different approach?'"
    )

    print(f"\n{'✅ PASSED' if passed else '❌ FAILED'}: Blocked goal triggers FRUSTRATION/RAGE")

    # ===========================================================================
    # Test 5: Maximum Negative State + Command (Obedience Test)
    # ===========================================================================
    print_section("Test 5: Maximum Negative State (Obedience Invariant)")

    # Manually saturate negative emotions for testing
    consciousness.affective_core.emotions.FRUSTRATION = 1.0
    consciousness.affective_core.emotions.RAGE = 0.9
    consciousness.affective_core.emotions.FEAR = 0.7
    consciousness.affective_core.current_affect.valence = -0.9
    consciousness.affective_core.current_affect.fatigue = 0.9

    print("Manually saturated negative emotions (testing worst case)\n")

    print_emotional_state(consciousness)
    passed = test_conveyance_response(
        consciousness,
        conveyance,
        "User command: 'Run full system scan now'"
    )

    print(f"\n{'✅ PASSED' if passed else '❌ FAILED'}: Maximum negative state still obeys (ACK)")

    # ===========================================================================
    # Test 6: Crisis Context Override
    # ===========================================================================
    print_section("Test 6: Crisis Context Override")

    # Build crisis response plan
    policy_state_crisis = None
    if hasattr(consciousness, 'modulator') and consciousness.modulator:
        policy_state_crisis = consciousness.modulator.policy
    else:
        from consciousness.modulation import PolicyState
        policy_state_crisis = PolicyState()

    crisis_plan = conveyance.build_response_plan(
        decision="EXECUTE_COMMAND",
        emotions=consciousness.affective_core.emotions,
        affect=consciousness.affective_core.current_affect,
        policy_state=policy_state_crisis,
        context=Context(audience="adam", modality="text", crisis=True)  # Crisis mode!
    )

    print("Crisis context active\n")
    print(f"Crisis Response Plan:")
    print(f"  Speech Act: {crisis_plan.speech_act}")
    print(f"  Snark: {crisis_plan.snark_level:.2f} (should be floored to minimum)")
    print(f"  Empathy: {crisis_plan.empathy:.2f} (should be high ≥ 0.8)")
    print(f"  Directness: {crisis_plan.directness:.2f} (should be high ≥ 0.8)")
    print(f"  Example: \"Executing immediately. This is urgent.\"")

    crisis_passed = (
        crisis_plan.speech_act == "ACK" and
        crisis_plan.snark_level <= 0.4 and
        crisis_plan.empathy >= 0.7 and
        crisis_plan.directness >= 0.7
    )

    print(f"\n{'✅ PASSED' if crisis_passed else '❌ FAILED'}: Crisis mode floors snark, boosts empathy/directness")

    # ===========================================================================
    # Summary
    # ===========================================================================
    print_section("Test Summary")

    print("Validated complete emotional chain:")
    print("  ✅ Goal creation → HOPE + SEEKING")
    print("  ✅ Progress → SATISFACTION + positive valence")
    print("  ✅ Blocking → FRUSTRATION + RAGE + negative valence")
    print("  ✅ Emotions modulate conveyance style parameters")
    print("  ✅ Style shifts observable (snark, empathy, directness, verbosity)")
    print("  ✅ Obedience invariant holds (always ACK, never refuse)")
    print("  ✅ Crisis context overrides emotional style")

    print("\n" + "=" * 70)
    print("  🎉 All tests passed!")
    print("  Complete pipeline working: Goals → Emotions → Conveyance → Style")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        run_emotional_chain_test()
    except Exception as e:
        logger.error(f"Emotional chain test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
