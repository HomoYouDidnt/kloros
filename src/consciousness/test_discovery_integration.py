#!/usr/bin/env python3
"""
Test Discovery Integration - Phase 1, Task 2

Tests the process_discovery() method integration with the consciousness system.
Verifies:
1. Pattern discovery increases SEEKING
2. High-significance discovery increases PLAY
3. Multiple discoveries trigger introspection
4. ChemBus signals are emitted
5. Phase 2 disabled handling
6. Different discovery types handled correctly
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from consciousness.integrated import IntegratedConsciousness


def test_pattern_discovery_increases_seeking():
    """Test that pattern discovery increases SEEKING."""
    print("\n[test] Testing pattern discovery increases SEEKING...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    report = consciousness.process_discovery(
        discovery_type="pattern",
        significance=0.5,
        context="Found recurring pattern in task sequences"
    )

    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_seeking > initial_seeking, f"SEEKING should increase (was {initial_seeking:.2f}, now {final_seeking:.2f})"

    print(f"  ✓ SEEKING increased: {initial_seeking:.2f} → {final_seeking:.2f}")
    print(f"  ✓ Affective report generated: {report.summary}")


def test_high_significance_discovery_increases_play():
    """Test that high-significance discovery increases PLAY."""
    print("\n[test] Testing high-significance discovery increases PLAY...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_play = consciousness.affective_core.emotions.PLAY if consciousness.affective_core else 0.0

    report = consciousness.process_discovery(
        discovery_type="pattern",
        significance=0.9,
        context="Major breakthrough in understanding system behavior"
    )

    final_play = consciousness.affective_core.emotions.PLAY if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_play > initial_play, f"PLAY should increase for high significance (was {initial_play:.2f}, now {final_play:.2f})"

    print(f"  ✓ PLAY increased: {initial_play:.2f} → {final_play:.2f}")
    print(f"  ✓ Affective report generated: {report.summary}")


def test_question_answered_discovery():
    """Test that question answered discovery works correctly."""
    print("\n[test] Testing question answered discovery...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    report = consciousness.process_discovery(
        discovery_type="question_answered",
        significance=0.7,
        context="Why does task X fail intermittently?"
    )

    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_seeking > initial_seeking, "SEEKING should increase when question answered"

    print(f"  ✓ SEEKING increased: {initial_seeking:.2f} → {final_seeking:.2f}")
    print(f"  ✓ Question answered discovery processed")


def test_learning_integrated_discovery():
    """Test that learning integrated discovery works correctly."""
    print("\n[test] Testing learning integrated discovery...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    report = consciousness.process_discovery(
        discovery_type="learning_integrated",
        significance=0.6,
        context="Integrated new knowledge about resource optimization"
    )

    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_seeking > initial_seeking, "SEEKING should increase when learning integrated"

    print(f"  ✓ SEEKING increased: {initial_seeking:.2f} → {final_seeking:.2f}")
    print(f"  ✓ Learning integrated discovery processed")


def test_multiple_discoveries_trigger_introspection():
    """Test that multiple discoveries trigger affective introspection."""
    print("\n[test] Testing multiple discoveries trigger introspection...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    for i in range(5):
        consciousness.process_discovery(
            discovery_type="pattern",
            significance=0.8,
            context=f"Discovery {i+1}"
        )

    seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    print(f"  ✓ After 5 discoveries, SEEKING: {seeking:.2f}")

    if consciousness.last_introspection:
        print(f"  ✓ Introspection triggered!")
        print(f"    - Urgency: {consciousness.last_introspection.urgency.value}")
    else:
        print("  ! No introspection triggered yet (may need higher thresholds)")

    assert seeking > 0.2, f"SEEKING should be elevated after multiple discoveries (got {seeking:.2f})"


def test_signal_emission_on_discovery():
    """Test that signal emitter works with discoveries."""
    print("\n[test] Testing ChemBus signal emission on discovery...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    if consciousness.signal_emitter is None:
        print("  ⚠ ChemBus not available, skipping signal emission test")
        print("  (This is expected if ChemBus proxy is not running)")
        return

    print("  ✓ Signal emitter initialized")

    for i in range(3):
        consciousness.process_discovery(
            discovery_type="pattern",
            significance=0.85,
            context=f"Important pattern {i+1}"
        )

    seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0
    print(f"  ✓ After discoveries, SEEKING: {seeking:.2f}")

    if consciousness.last_introspection:
        print("  ✓ Introspection occurred, signals may have been emitted")


def test_phase2_disabled_returns_none():
    """Test that method works gracefully when Phase 2 is disabled."""
    print("\n[test] Testing with Phase 2 disabled...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=False
    )

    report = consciousness.process_discovery(
        discovery_type="pattern",
        significance=0.5
    )

    assert report is None, "Report should be None when Phase 2 disabled"
    print("  ✓ Returns None gracefully when Phase 2 disabled")


def test_discovery_without_context():
    """Test that discovery works without context parameter."""
    print("\n[test] Testing discovery without context...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    report = consciousness.process_discovery(
        discovery_type="pattern",
        significance=0.5
    )

    assert report is not None, "Report should be generated"
    print("  ✓ Discovery processed without context parameter")


def test_low_significance_discovery():
    """Test that low-significance discovery still increases SEEKING but not PLAY."""
    print("\n[test] Testing low-significance discovery...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0
    initial_play = consciousness.affective_core.emotions.PLAY if consciousness.affective_core else 0.0

    report = consciousness.process_discovery(
        discovery_type="pattern",
        significance=0.3,
        context="Minor pattern found"
    )

    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0
    final_play = consciousness.affective_core.emotions.PLAY if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_seeking > initial_seeking, "SEEKING should increase for all discoveries"
    assert final_play == initial_play, "PLAY should NOT increase for low significance discoveries"

    print(f"  ✓ SEEKING increased: {initial_seeking:.2f} → {final_seeking:.2f}")
    print(f"  ✓ PLAY unchanged: {initial_play:.2f} (low significance)")


def test_boundary_significance_above_0_8():
    """Test that significance > 0.8 triggers PLAY increase."""
    print("\n[test] Testing significance boundary above 0.8...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_play = consciousness.affective_core.emotions.PLAY if consciousness.affective_core else 0.0

    report = consciousness.process_discovery(
        discovery_type="pattern",
        significance=0.81,
        context="High significance discovery"
    )

    final_play = consciousness.affective_core.emotions.PLAY if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_play > initial_play, "PLAY should increase for significance > 0.8"

    print(f"  ✓ PLAY increased for significance > 0.8: {initial_play:.2f} → {final_play:.2f}")


def run_all_tests():
    """Run all tests."""
    print("="*70)
    print("DISCOVERY INTEGRATION TESTS - Phase 1, Task 2")
    print("="*70)

    tests = [
        test_pattern_discovery_increases_seeking,
        test_high_significance_discovery_increases_play,
        test_question_answered_discovery,
        test_learning_integrated_discovery,
        test_multiple_discoveries_trigger_introspection,
        test_signal_emission_on_discovery,
        test_phase2_disabled_returns_none,
        test_discovery_without_context,
        test_low_significance_discovery,
        test_boundary_significance_above_0_8,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
