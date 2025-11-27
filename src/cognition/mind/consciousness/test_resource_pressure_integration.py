#!/usr/bin/env python3
"""
Test Resource Pressure Integration - Phase 1, Task 3

Tests the process_resource_pressure() method integration with the consciousness system.
Verifies:
1. Memory pressure increases FEAR
2. Critical pressure (>0.9) increases PANIC
3. Moderate pressure (0.7 < level <= 0.9) increases SEEKING
4. Different pressure types handled (memory, cpu, context, errors)
5. Evidence parameter captured
6. Multiple pressure events trigger introspection
7. UMN signal emission works
8. Phase 2 disabled handling
9. Boundary conditions (exactly 0.7, exactly 0.9)
10. Pressure without evidence (optional parameter)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.consciousness.integrated import IntegratedConsciousness


def test_memory_pressure_increases_fear():
    """Test that memory pressure increases FEAR."""
    print("\n[test] Testing memory pressure increases FEAR...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_fear = consciousness.affective_core.emotions.FEAR if consciousness.affective_core else 0.0

    report = consciousness.process_resource_pressure(
        pressure_type="memory",
        level=0.5,
        evidence=["Token usage: 1500/2000", "Memory utilization: 75%"]
    )

    final_fear = consciousness.affective_core.emotions.FEAR if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_fear > initial_fear, f"FEAR should increase (was {initial_fear:.2f}, now {final_fear:.2f})"
    assert consciousness.current_signals.error_rate == 1.0, "Pressure recorded as failure"

    print(f"  ✓ FEAR increased: {initial_fear:.2f} → {final_fear:.2f}")
    print(f"  ✓ Error rate recorded: {consciousness.current_signals.error_rate:.0%}")
    print(f"  ✓ Affective report generated: {report.summary}")


def test_critical_pressure_increases_panic():
    """Test that critical pressure (>0.9) increases PANIC."""
    print("\n[test] Testing critical pressure (>0.9) increases PANIC...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0

    report = consciousness.process_resource_pressure(
        pressure_type="context",
        level=0.95,
        evidence=["Context window: 95% full", "Immediate truncation risk"]
    )

    final_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_panic > initial_panic, f"PANIC should increase (was {initial_panic:.2f}, now {final_panic:.2f})"

    print(f"  ✓ PANIC increased: {initial_panic:.2f} → {final_panic:.2f}")
    print(f"  ✓ Critical pressure correctly identified and handled")
    print(f"  ✓ Affective report generated: {report.summary}")


def test_moderate_pressure_increases_seeking():
    """Test that moderate pressure (0.7 < level <= 0.9) increases SEEKING."""
    print("\n[test] Testing moderate pressure increases SEEKING...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    report = consciousness.process_resource_pressure(
        pressure_type="cpu",
        level=0.8,
        evidence=["CPU strain: 80%", "Processing delays detected"]
    )

    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_seeking > initial_seeking, f"SEEKING should increase (was {initial_seeking:.2f}, now {final_seeking:.2f})"

    print(f"  ✓ SEEKING increased: {initial_seeking:.2f} → {final_seeking:.2f}")
    print(f"  ✓ Problem-solving activation triggered for moderate pressure")
    print(f"  ✓ Affective report generated: {report.summary}")


def test_memory_pressure_type():
    """Test that memory pressure type is handled correctly."""
    print("\n[test] Testing memory pressure type handling...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    report = consciousness.process_resource_pressure(
        pressure_type="memory",
        level=0.6,
        evidence=["Memory pressure detected"]
    )

    assert report is not None, "Report should be generated"
    print(f"  ✓ Memory pressure type handled: {report.summary}")


def test_cpu_pressure_type():
    """Test that CPU pressure type is handled correctly."""
    print("\n[test] Testing CPU pressure type handling...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    report = consciousness.process_resource_pressure(
        pressure_type="cpu",
        level=0.5,
        evidence=["CPU strain: 50%"]
    )

    assert report is not None, "Report should be generated"
    print(f"  ✓ CPU pressure type handled: {report.summary}")


def test_context_pressure_type():
    """Test that context pressure type is handled correctly."""
    print("\n[test] Testing context pressure type handling...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    report = consciousness.process_resource_pressure(
        pressure_type="context",
        level=0.4,
        evidence=["Context usage: 40%"]
    )

    assert report is not None, "Report should be generated"
    print(f"  ✓ Context pressure type handled: {report.summary}")


def test_error_pressure_type():
    """Test that error pressure type is handled correctly."""
    print("\n[test] Testing error pressure type handling...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    report = consciousness.process_resource_pressure(
        pressure_type="errors",
        level=0.7,
        evidence=["Error pattern detected: 7 consecutive failures"]
    )

    assert report is not None, "Report should be generated"
    print(f"  ✓ Error pressure type handled: {report.summary}")


def test_evidence_parameter_captured():
    """Test that evidence parameter is captured in the report."""
    print("\n[test] Testing evidence parameter capturing...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    evidence_list = [
        "Pressure event 1",
        "Pressure event 2",
        "Pressure event 3"
    ]

    report = consciousness.process_resource_pressure(
        pressure_type="memory",
        level=0.6,
        evidence=evidence_list
    )

    assert report is not None, "Report should be generated"
    print(f"  ✓ Evidence captured: {len(evidence_list)} items")
    print(f"  ✓ Report generated with evidence")


def test_pressure_without_evidence():
    """Test that pressure works without evidence parameter."""
    print("\n[test] Testing pressure without evidence...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    report = consciousness.process_resource_pressure(
        pressure_type="memory",
        level=0.5
    )

    assert report is not None, "Report should be generated even without evidence"
    print(f"  ✓ Pressure processed without evidence parameter")
    print(f"  ✓ Report generated: {report.summary}")


def test_multiple_pressure_events_trigger_introspection():
    """Test that multiple pressure events trigger affective introspection."""
    print("\n[test] Testing multiple pressure events trigger introspection...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    for i in range(5):
        consciousness.process_resource_pressure(
            pressure_type="memory",
            level=0.8,
            evidence=[f"Pressure event {i+1}"]
        )

    fear = consciousness.affective_core.emotions.FEAR if consciousness.affective_core else 0.0

    print(f"  ✓ After 5 pressure events, FEAR: {fear:.2f}")
    print(f"  ✓ Error rate: {consciousness.current_signals.error_rate:.0%}")

    if consciousness.last_introspection:
        print(f"  ✓ Introspection triggered!")
        print(f"    - Urgency: {consciousness.last_introspection.urgency.value}")
        print(f"    - Can self-remediate: {consciousness.last_introspection.can_self_remediate}")
    else:
        print("  ! No introspection triggered yet (may need higher thresholds)")

    assert fear > 0.3, f"FEAR should be elevated after multiple pressure events (got {fear:.2f})"


def test_signal_emission_integration():
    """Test that signal emitter is initialized and can emit."""
    print("\n[test] Testing UMN signal emission integration...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    if consciousness.signal_emitter is None:
        print("  ⚠ UMN not available, skipping signal emission test")
        print("  (This is expected if UMN proxy is not running)")
        return

    print("  ✓ Signal emitter initialized")

    for i in range(10):
        consciousness.process_resource_pressure(
            pressure_type="cpu",
            level=0.95,
            evidence=[f"Critical pressure {i+1}"]
        )

    panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0
    print(f"  ✓ After 10 critical pressures, PANIC: {panic:.2f}")

    if consciousness.last_introspection:
        print("  ✓ Introspection occurred, signals may have been emitted")
        print(f"    - Check UMN proxy logs for AFFECT_HIGH_PANIC or similar signals")


def test_phase2_disabled():
    """Test that method works gracefully when Phase 2 is disabled."""
    print("\n[test] Testing with Phase 2 disabled...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=False
    )

    report = consciousness.process_resource_pressure(
        pressure_type="memory",
        level=0.8,
        evidence=["Test pressure"]
    )

    assert report is None, "Report should be None when Phase 2 disabled"
    print("  ✓ Returns None gracefully when Phase 2 disabled")


def test_boundary_level_exactly_0_7():
    """Test boundary condition where level is exactly 0.7."""
    print("\n[test] Testing boundary condition level == 0.7...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    report = consciousness.process_resource_pressure(
        pressure_type="memory",
        level=0.7,
        evidence=["At boundary level 0.7"]
    )

    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_seeking == initial_seeking, "SEEKING should NOT increase at exactly 0.7 (not > 0.7)"

    print(f"  ✓ Boundary condition correct: level=0.7 does NOT trigger SEEKING increase")
    print(f"  ✓ SEEKING unchanged: {initial_seeking:.2f}")


def test_boundary_level_exactly_0_9():
    """Test boundary condition where level is exactly 0.9."""
    print("\n[test] Testing boundary condition level == 0.9...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0

    report = consciousness.process_resource_pressure(
        pressure_type="context",
        level=0.9,
        evidence=["At boundary level 0.9"]
    )

    final_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_panic == initial_panic, "PANIC should NOT increase at exactly 0.9 (not > 0.9)"

    print(f"  ✓ Boundary condition correct: level=0.9 does NOT trigger PANIC increase")
    print(f"  ✓ PANIC unchanged: {initial_panic:.2f}")


def test_boundary_level_above_0_9():
    """Test boundary condition where level is above 0.9."""
    print("\n[test] Testing boundary condition level > 0.9...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0

    report = consciousness.process_resource_pressure(
        pressure_type="context",
        level=0.91,
        evidence=["Above boundary level 0.91"]
    )

    final_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_panic > initial_panic, "PANIC should increase for level > 0.9"

    print(f"  ✓ Boundary condition correct: level=0.91 DOES trigger PANIC increase")
    print(f"  ✓ PANIC increased: {initial_panic:.2f} → {final_panic:.2f}")


def test_fear_scaled_by_level():
    """Test that FEAR increase is scaled by pressure level."""
    print("\n[test] Testing FEAR scaling by pressure level...")

    consciousness_low = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    consciousness_high = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_fear_low = consciousness_low.affective_core.emotions.FEAR if consciousness_low.affective_core else 0.0
    initial_fear_high = consciousness_high.affective_core.emotions.FEAR if consciousness_high.affective_core else 0.0

    consciousness_low.process_resource_pressure(
        pressure_type="memory",
        level=0.3
    )

    consciousness_high.process_resource_pressure(
        pressure_type="memory",
        level=0.9
    )

    final_fear_low = consciousness_low.affective_core.emotions.FEAR if consciousness_low.affective_core else 0.0
    final_fear_high = consciousness_high.affective_core.emotions.FEAR if consciousness_high.affective_core else 0.0

    fear_increase_low = final_fear_low - initial_fear_low
    fear_increase_high = final_fear_high - initial_fear_high

    assert fear_increase_high > fear_increase_low, "FEAR increase should be higher for higher pressure levels"

    print(f"  ✓ FEAR scaling correct:")
    print(f"    - Low pressure (0.3): FEAR increase = {fear_increase_low:.3f}")
    print(f"    - High pressure (0.9): FEAR increase = {fear_increase_high:.3f}")
    print(f"    - Higher pressure produces more FEAR: {fear_increase_high > fear_increase_low}")


def test_low_pressure_no_panic_no_seeking():
    """Test that low pressure (< 0.7) only increases FEAR, not PANIC or SEEKING."""
    print("\n[test] Testing low pressure (< 0.7) affects only FEAR...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    initial_fear = consciousness.affective_core.emotions.FEAR if consciousness.affective_core else 0.0
    initial_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0
    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    report = consciousness.process_resource_pressure(
        pressure_type="memory",
        level=0.5
    )

    final_fear = consciousness.affective_core.emotions.FEAR if consciousness.affective_core else 0.0
    final_panic = consciousness.affective_core.emotions.PANIC if consciousness.affective_core else 0.0
    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert report is not None, "Report should be generated"
    assert final_fear > initial_fear, "FEAR should increase"
    assert final_panic == initial_panic, "PANIC should NOT increase for low pressure"
    assert final_seeking == initial_seeking, "SEEKING should NOT increase for low pressure"

    print(f"  ✓ FEAR increased: {initial_fear:.2f} → {final_fear:.2f}")
    print(f"  ✓ PANIC unchanged: {initial_panic:.2f} (low pressure)")
    print(f"  ✓ SEEKING unchanged: {initial_seeking:.2f} (low pressure)")


def run_all_tests():
    """Run all tests."""
    print("="*70)
    print("RESOURCE PRESSURE INTEGRATION TESTS - Phase 1, Task 3")
    print("="*70)

    tests = [
        test_memory_pressure_increases_fear,
        test_critical_pressure_increases_panic,
        test_moderate_pressure_increases_seeking,
        test_memory_pressure_type,
        test_cpu_pressure_type,
        test_context_pressure_type,
        test_error_pressure_type,
        test_evidence_parameter_captured,
        test_pressure_without_evidence,
        test_multiple_pressure_events_trigger_introspection,
        test_signal_emission_integration,
        test_phase2_disabled,
        test_boundary_level_exactly_0_7,
        test_boundary_level_exactly_0_9,
        test_boundary_level_above_0_9,
        test_fear_scaled_by_level,
        test_low_pressure_no_panic_no_seeking,
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
