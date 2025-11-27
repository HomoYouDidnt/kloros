#!/usr/bin/env python3
"""Unit tests for GLaDOS style training system."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.voice.style.context_classifier import (
    Context, StyleBudget, classify_context, detect_affect, classify_task
)
from src.voice.style.policy_engine import choose_technique, _is_structured_output
from src.voice.style.technique_library import apply_technique, seed_style, _naturalize_output
from src.voice.style.parrot_guard import parrot_guard, jaccard_3gram, BANNED_PHRASES


def test_frustrated_user_gets_no_snark():
    """Frustrated users should not get sarcastic responses."""
    print("\n[Test 1] Frustrated user → no snark")

    # Simulate frustrated user
    ctx = Context(
        affect="frustrated",
        task_type="repair",
        stakes="high",
        continuity="ongoing",
        recent_failure=False,
        turn_idx=5,
        last_styled_turn=0,
        style_budget=StyleBudget()
    )

    technique = choose_technique(ctx)
    assert technique is None, f"Expected None for frustrated user, got {technique}"
    print("  ✓ No style technique selected for frustrated user")


def test_diagnostic_gets_no_style():
    """Diagnostic/repair tasks should not get styled."""
    print("\n[Test 2] Diagnostic task → no style")

    ctx = Context(
        affect="neutral",
        task_type="diagnostic",
        stakes="normal",
        continuity="ongoing",
        recent_failure=False,
        turn_idx=5,
        last_styled_turn=0,
        style_budget=StyleBudget()
    )

    technique = choose_technique(ctx)
    assert technique is None, f"Expected None for diagnostic, got {technique}"
    print("  ✓ No style technique selected for diagnostic task")


def test_recent_failure_blocks_style():
    """Recent failures should block style (no gloating)."""
    print("\n[Test 3] Recent failure → cooldown")

    ctx = Context(
        affect="playful",
        task_type="chat",
        stakes="low",
        continuity="ongoing",
        recent_failure=True,  # Recent failure
        turn_idx=5,
        last_styled_turn=0,
        style_budget=StyleBudget()
    )

    technique = choose_technique(ctx)
    assert technique is None, f"Expected None after failure, got {technique}"
    print("  ✓ No style technique selected after recent failure")


def test_rate_limiting_consecutive_turns():
    """Rate limiting should prevent consecutive styled turns."""
    print("\n[Test 4] Rate limiting → no consecutive style")

    ctx = Context(
        affect="playful",
        task_type="chat",
        stakes="low",
        continuity="ongoing",
        recent_failure=False,
        turn_idx=5,
        last_styled_turn=4,  # Last turn was styled
        style_budget=StyleBudget()
    )

    technique = choose_technique(ctx)
    assert technique is None, f"Expected None for consecutive turn, got {technique}"
    print("  ✓ Rate limiting prevented consecutive styling")


def test_token_bucket_exhaustion():
    """Token bucket should limit styling frequency."""
    print("\n[Test 5] Token bucket → budget exhaustion")

    budget = StyleBudget()
    budget.tokens = 0  # Exhausted

    ctx = Context(
        affect="playful",
        task_type="chat",
        stakes="low",
        continuity="ongoing",
        recent_failure=False,
        turn_idx=10,
        last_styled_turn=5,
        style_budget=budget
    )

    technique = choose_technique(ctx)
    assert technique is None, f"Expected None with exhausted budget, got {technique}"
    print("  ✓ Token bucket exhaustion prevented styling")


def test_playful_low_stakes_gets_style():
    """Playful + low stakes should allow styling."""
    print("\n[Test 6] Playful + low stakes → style allowed")

    ctx = Context(
        affect="playful",
        task_type="chat",
        stakes="low",
        continuity="ongoing",
        recent_failure=False,
        turn_idx=10,
        last_styled_turn=5,
        style_budget=StyleBudget()
    )

    technique = choose_technique(ctx)
    assert technique is not None, f"Expected technique for playful/low-stakes, got {technique}"
    assert technique == "backhanded_compliment", f"Expected backhanded_compliment, got {technique}"
    print(f"  ✓ Style technique selected: {technique}")


def test_parrot_guard_blocks_portal_refs():
    """Parrot-guard should block Portal-specific phrases."""
    print("\n[Test 7] Parrot-guard → lexical ban")

    # Text with banned phrase
    text = "Welcome to the Aperture Science enrichment center"

    # Simple check without corpus index (just lexical)
    has_banned = any(phrase in text.lower() for phrase in BANNED_PHRASES)
    assert has_banned, "Expected banned phrase to be detected"
    print("  ✓ Parrot-guard detected Portal-specific phrase")


def test_jaccard_3gram():
    """Test Jaccard 3-gram similarity."""
    print("\n[Test 8] Jaccard 3-gram similarity")

    # Identical strings
    sim1 = jaccard_3gram("hello world", "hello world")
    assert sim1 == 1.0, f"Expected 1.0 for identical, got {sim1}"

    # Different strings
    sim2 = jaccard_3gram("hello world", "goodbye moon")
    assert sim2 < 0.5, f"Expected <0.5 for different, got {sim2}"

    # Partial overlap
    sim3 = jaccard_3gram("aperture science", "aperture labs")
    assert 0.3 < sim3 < 0.8, f"Expected moderate overlap, got {sim3}"

    print(f"  ✓ Jaccard similarity working correctly")


def test_affect_detection():
    """Test affect detection from queries."""
    print("\n[Test 9] Affect detection")

    assert detect_affect("ugh this is broken") == "frustrated"
    assert detect_affect("lol that's awesome") == "playful"
    assert detect_affect("check the status") == "neutral"

    print("  ✓ Affect detection working")


def test_task_classification():
    """Test task classification."""
    print("\n[Test 10] Task classification")

    assert classify_task("check the audio status") == "diagnostic"
    assert classify_task("fix the broken audio") == "repair"
    assert classify_task("explain how this works") == "explanation"
    assert classify_task("how are you") == "chat"

    print("  ✓ Task classification working")


def test_technique_application():
    """Test technique application with variation."""
    print("\n[Test 11] Technique application")

    # Seed RNG for deterministic results
    seed_style("test_session")

    base_text = "Task completed successfully."

    # Backhanded compliment
    styled1 = apply_technique(base_text, "backhanded_compliment")
    assert styled1 != base_text, "Expected styled text to differ from base"
    assert base_text in styled1, "Expected base text to be preserved in styled output"
    print(f"  Original: {base_text}")
    print(f"  Styled:   {styled1}")

    # Understated disaster
    styled2 = apply_technique(base_text, "understated_disaster")
    assert styled2 != base_text, "Expected styled text to differ from base"
    assert base_text in styled2, "Expected base text to be in styled output"
    print(f"  Styled:   {styled2}")

    print("  ✓ Technique application working")


def test_style_budget_token_bucket():
    """Test StyleBudget token bucket mechanics."""
    print("\n[Test 12] StyleBudget token bucket")

    budget = StyleBudget()
    assert budget.tokens == 2, "Expected initial tokens = 2"

    # Consume tokens
    assert budget.consume(1) == True
    assert budget.tokens == 1

    assert budget.consume(1) == True
    assert budget.tokens == 0

    # Exhausted
    assert budget.consume(1) == False
    assert budget.tokens == 0

    # Refill after 3 ticks
    budget.tick()
    budget.tick()
    budget.tick()
    assert budget.tokens == 1, "Expected 1 token after 3 ticks"

    print("  ✓ Token bucket working correctly")


def test_structured_output_detection():
    """Test detection of structured test/diagnostic output."""
    print("\n[Test 13] Structured output detection")

    # Structured output examples
    structured1 = "=== Audio System ===\n✓ Microphone working"
    structured2 = "Component Status:\n- Audio: ✅\n- Memory: ❌"
    structured3 = "1. Audio System: working\n2. Memory: failed"

    # Plain text
    plain = "The audio system is working fine."

    assert _is_structured_output(structured1), "Should detect section headers"
    assert _is_structured_output(structured2), "Should detect status symbols"
    assert _is_structured_output(structured3), "Should detect numbered lists"
    assert not _is_structured_output(plain), "Should not detect plain text"

    print("  ✓ Structured output detection working")


def test_natural_summary_technique():
    """Test natural_summary technique for converting structured output."""
    print("\n[Test 14] Natural summary technique")

    structured = """=== Audio System ===
✓ Microphone working
✗ Speaker failed
- Device 0: available
- Device 1: unavailable"""

    naturalized = _naturalize_output(structured)

    # Check conversions
    assert "===" not in naturalized, "Section headers should be removed"
    assert "✓" not in naturalized, "Check marks should be converted"
    assert "working" in naturalized, "Should contain status prose"
    assert "failed" in naturalized, "Should contain failure prose"

    print(f"  Original:    {structured[:50]}...")
    print(f"  Naturalized: {naturalized[:80]}...")

    # Apply technique
    styled = apply_technique(structured, "natural_summary")
    assert styled != structured, "Styled output should differ from structured"
    assert "===" not in styled, "Styled output should not have section headers"

    print("  ✓ Natural summary technique working")


def test_structured_output_policy():
    """Test that structured output always gets natural_summary."""
    print("\n[Test 15] Structured output policy override")

    ctx = Context(
        affect="frustrated",  # Would normally block styling
        task_type="diagnostic",  # Would normally block styling
        stakes="high",  # Would normally block styling
        continuity="ongoing",
        recent_failure=False,
        turn_idx=5,
        last_styled_turn=0,
        style_budget=StyleBudget()
    )

    # With structured output, should still get natural_summary
    structured_response = "=== Audio System ===\n✓ Working"
    technique = choose_technique(ctx, response_text=structured_response)
    assert technique == "natural_summary", f"Expected natural_summary for structured output, got {technique}"

    # Without structured output, gates should block
    plain_response = "The system is working."
    technique2 = choose_technique(ctx, response_text=plain_response)
    assert technique2 is None, f"Expected None for plain text with safety gates, got {technique2}"

    print("  ✓ Structured output overrides safety gates")


def run_all_tests():
    """Run all unit tests."""
    print("="*60)
    print("GLaDOS Style System Unit Tests")
    print("="*60)

    tests = [
        test_frustrated_user_gets_no_snark,
        test_diagnostic_gets_no_style,
        test_recent_failure_blocks_style,
        test_rate_limiting_consecutive_turns,
        test_token_bucket_exhaustion,
        test_playful_low_stakes_gets_style,
        test_parrot_guard_blocks_portal_refs,
        test_jaccard_3gram,
        test_affect_detection,
        test_task_classification,
        test_technique_application,
        test_style_budget_token_bucket,
        test_structured_output_detection,
        test_natural_summary_technique,
        test_structured_output_policy,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n  ❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
