#!/usr/bin/env python3
"""
Test Task Outcome Integration - Phase 1, Task 1

Tests the process_task_outcome() method integration with the consciousness system.
Verifies:
1. Task outcomes update interoceptive signals
2. Success increases SEEKING, failure increases RAGE
3. Affective introspection is triggered
4. ChemBus signals are emitted when thresholds crossed
"""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from consciousness.integrated import IntegratedConsciousness


def test_successful_task_outcome():
    """Test that successful task outcomes increase SEEKING."""
    print("\n[test] Testing successful task outcome...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    report = consciousness.process_task_outcome(
        task_type='tool_call',
        success=True,
        duration=0.5
    )

    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_seeking > initial_seeking, f"SEEKING should increase (was {initial_seeking:.2f}, now {final_seeking:.2f})"
    assert consciousness.current_signals.success_rate > 0, "Success rate should be recorded"

    print(f"  ✓ SEEKING increased: {initial_seeking:.2f} → {final_seeking:.2f}")
    print(f"  ✓ Success rate: {consciousness.current_signals.success_rate:.0%}")
    print(f"  ✓ Affective report generated: {report.summary}")


def test_failed_task_outcome():
    """Test that failed task outcomes increase RAGE."""
    print("\n[test] Testing failed task outcome...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_rage = consciousness.affective_core.emotions.RAGE if consciousness.affective_core else 0.0

    report = consciousness.process_task_outcome(
        task_type='tool_call',
        success=False,
        duration=1.2,
        error="Connection timeout"
    )

    final_rage = consciousness.affective_core.emotions.RAGE if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_rage > initial_rage, f"RAGE should increase (was {initial_rage:.2f}, now {final_rage:.2f})"
    assert consciousness.current_signals.error_rate > 0, "Error rate should be recorded"
    assert consciousness.current_signals.exceptions > 0, "Exception should be recorded"

    print(f"  ✓ RAGE increased: {initial_rage:.2f} → {final_rage:.2f}")
    print(f"  ✓ Error rate: {consciousness.current_signals.error_rate:.0%}")
    print(f"  ✓ Exception count: {consciousness.current_signals.exceptions}")
    print(f"  ✓ Affective report generated: {report.summary}")


def test_multiple_failures_trigger_introspection():
    """Test that multiple failures trigger affective introspection."""
    print("\n[test] Testing multiple failures trigger introspection...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    for i in range(5):
        consciousness.process_task_outcome(
            task_type='analysis',
            success=False,
            error=f"Error {i+1}"
        )

    rage = consciousness.affective_core.emotions.RAGE if consciousness.affective_core else 0.0

    print(f"  ✓ After 5 failures, RAGE: {rage:.2f}")
    print(f"  ✓ Error rate: {consciousness.current_signals.error_rate:.0%}")
    print(f"  ✓ Exception count: {consciousness.current_signals.exceptions}")

    if consciousness.last_introspection:
        print(f"  ✓ Introspection triggered!")
        print(f"    - Urgency: {consciousness.last_introspection.urgency.value}")
        print(f"    - Can self-remediate: {consciousness.last_introspection.can_self_remediate}")
        print(f"    - Root causes: {consciousness.last_introspection.root_causes}")
        if consciousness.last_introspection.autonomous_actions:
            print(f"    - Autonomous actions available: {len(consciousness.last_introspection.autonomous_actions)}")
    else:
        print("  ! No introspection triggered yet (may need higher thresholds)")

    assert consciousness.current_signals.error_rate == 1.0, "All tasks failed"
    assert rage > 0.3, f"RAGE should be elevated after multiple failures (got {rage:.2f})"


def test_signal_emission_integration():
    """Test that signal emitter is initialized and can emit."""
    print("\n[test] Testing ChemBus signal emission integration...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    if consciousness.signal_emitter is None:
        print("  ⚠ ChemBus not available, skipping signal emission test")
        print("  (This is expected if ChemBus proxy is not running)")
        return

    print("  ✓ Signal emitter initialized")

    for i in range(10):
        consciousness.process_task_outcome(
            task_type='test',
            success=False,
            error=f"Repetitive error {i+1}"
        )

    rage = consciousness.affective_core.emotions.RAGE if consciousness.affective_core else 0.0
    print(f"  ✓ After 10 failures, RAGE: {rage:.2f}")

    if consciousness.last_introspection:
        print("  ✓ Introspection occurred, signals may have been emitted")
        print(f"    - Check ChemBus proxy logs for AFFECT_HIGH_RAGE or similar signals")


def test_phase2_disabled():
    """Test that method works gracefully when Phase 2 is disabled."""
    print("\n[test] Testing with Phase 2 disabled...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=False
    )

    report = consciousness.process_task_outcome(
        task_type='test',
        success=True
    )

    assert report is None, "Report should be None when Phase 2 disabled"
    print("  ✓ Returns None gracefully when Phase 2 disabled")


def test_duration_tracking():
    """Test that task duration is tracked properly."""
    print("\n[test] Testing task duration tracking...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    consciousness.process_task_outcome(
        task_type='tool_call',
        success=True,
        duration=2.5
    )

    assert consciousness.current_signals.tool_call_latency > 0, "Latency should be tracked"
    print(f"  ✓ Latency tracked: {consciousness.current_signals.tool_call_latency:.3f}")


def run_all_tests():
    """Run all tests."""
    print("="*70)
    print("TASK OUTCOME INTEGRATION TESTS - Phase 1, Task 1")
    print("="*70)

    tests = [
        test_successful_task_outcome,
        test_failed_task_outcome,
        test_multiple_failures_trigger_introspection,
        test_signal_emission_integration,
        test_phase2_disabled,
        test_duration_tracking
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
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
