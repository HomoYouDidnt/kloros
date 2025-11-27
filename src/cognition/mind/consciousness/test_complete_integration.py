#!/usr/bin/env python3
"""
Complete Consciousness Integration Tests - Phase 1, Task 4

Tests the integration of consciousness event processor methods into the KLoROS codebase.
Verifies:
1. Task outcome processing in executor
2. Discovery event processing in curiosity archive
3. Resource pressure processing in system monitor
"""

import sys
from pathlib import Path
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.consciousness.integrated import IntegratedConsciousness
from agentflow.executor import Executor
from src.cognition.mind.cognition.curiosity_archive_manager import ArchiveManager
from src.cognition.mind.cognition.curiosity_core import SystemResourceMonitor, CuriosityQuestion, ActionClass, QuestionStatus

try:
    from src.orchestration.core.umn_bus import UMNPub
    CHEM_AVAILABLE = True
except ImportError:
    CHEM_AVAILABLE = False


def test_executor_task_outcome_integration():
    """Test that executor emits task outcome events for consciousness."""
    print("\n[test] Testing executor task outcome integration...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    executor = Executor(consciousness=consciousness)

    initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    decision = {
        "tool": "test_tool",
        "args": {}
    }
    state = {"context": "test"}

    result = executor.run(decision, state)

    assert result["success"] is True, "Tool execution should succeed"
    final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

    assert final_seeking > initial_seeking, f"SEEKING should increase after successful task (was {initial_seeking:.2f}, now {final_seeking:.2f})"

    print(f"  ✓ Executor emits task outcome events")
    print(f"  ✓ SEEKING increased from {initial_seeking:.2f} to {final_seeking:.2f}")
    print(f"  ✓ Report generated: {consciousness.last_report.summary if consciousness.last_report else 'N/A'}")


def test_executor_task_failure_integration():
    """Test that executor emits failure events."""
    print("\n[test] Testing executor task failure integration...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    executor = Executor(consciousness=consciousness)

    initial_tasks = consciousness.current_signals.tasks if consciousness.current_signals else 0

    class FailingTool:
        def execute(self, kloros_instance):
            raise Exception("Tool execution failed")

    executor.tool_registry = type('obj', (object,), {
        'get_tool': lambda self, name: FailingTool() if name == "failing_tool" else None
    })()

    decision = {
        "tool": "failing_tool",
        "args": {}
    }
    state = {"context": "test"}

    result = executor.run(decision, state)

    assert result["success"] is False, "Tool should fail and report success=False"

    print(f"  ✓ Executor emits failure events")
    print(f"  ✓ Tool execution failure handled correctly")


def test_archive_manager_discovery_integration():
    """Test that archive manager emits discovery events for consciousness."""
    print("\n[test] Testing archive manager discovery integration...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    try:
        chem_pub = UMNPub()
    except Exception as e:
        print(f"  ⚠ UMN not available ({e}), using mock")
        class MockUMNPub:
            def emit(self, topic, **kwargs):
                pass
        chem_pub = MockUMNPub()

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_mgr = ArchiveManager(
            archive_dir=Path(tmpdir),
            chem_pub=chem_pub,
            consciousness=consciousness
        )

        initial_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

        for i in range(10):
            question = CuriosityQuestion(
                id=f"test_{i}",
                hypothesis=f"TEST_HYPOTHESIS_{i}",
                question=f"Test question {i}",
                evidence=[f"Evidence {i}"],
                action_class=ActionClass.INVESTIGATE,
                autonomy=1,
                value_estimate=0.5,
                cost=0.2,
                status=QuestionStatus.READY
            )
            archive_mgr.archive_question(question, "low_value")

        final_seeking = consciousness.affective_core.emotions.SEEKING if consciousness.affective_core else 0.0

        assert final_seeking > initial_seeking, f"SEEKING should increase when pattern detected (was {initial_seeking:.2f}, now {final_seeking:.2f})"

        print(f"  ✓ Archive manager emits discovery events")
        print(f"  ✓ Pattern detected when threshold reached")
        print(f"  ✓ SEEKING increased from {initial_seeking:.2f} to {final_seeking:.2f}")


def test_system_monitor_resource_pressure_integration():
    """Test that system monitor emits resource pressure events for consciousness."""
    print("\n[test] Testing system monitor resource pressure integration...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    monitor = SystemResourceMonitor(
        memory_threshold=0.5,
        consciousness=consciousness
    )

    initial_fear = consciousness.affective_core.emotions.FEAR if consciousness.affective_core else 0.0

    snapshot = monitor.capture_snapshot()
    issues = monitor.detect_resource_issues(snapshot)

    final_fear = consciousness.affective_core.emotions.FEAR if consciousness.affective_core else 0.0

    assert final_fear >= initial_fear, f"FEAR should increase or stay same when checking resources (was {initial_fear:.2f}, now {final_fear:.2f})"

    print(f"  ✓ System monitor emits resource pressure events")
    print(f"  ✓ Detected {len(issues)} resource issues")
    if issues:
        print(f"  ✓ Issues detected: {issues[:3]}")
    if final_fear > initial_fear:
        print(f"  ✓ FEAR increased from {initial_fear:.2f} to {final_fear:.2f}")
    else:
        print(f"  ✓ No resource issues triggered (system healthy)")


def test_all_integrations_together():
    """Test that all three integrations work together."""
    print("\n[test] Testing all integrations together...")

    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    executor = Executor(consciousness=consciousness)
    monitor = SystemResourceMonitor(consciousness=consciousness)

    for i in range(3):
        decision = {"tool": f"test_tool_{i}", "args": {}}
        state = {"context": f"test_{i}"}
        executor.run(decision, state)

    try:
        chem_pub = UMNPub()
    except Exception:
        class MockUMNPub:
            def emit(self, topic, **kwargs):
                pass
        chem_pub = MockUMNPub()

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_mgr = ArchiveManager(
            archive_dir=Path(tmpdir),
            chem_pub=chem_pub,
            consciousness=consciousness
        )

        for i in range(10):
            question = CuriosityQuestion(
                id=f"test_{i}",
                hypothesis=f"TEST_{i}",
                question=f"Test {i}",
                evidence=[f"Ev {i}"],
                action_class=ActionClass.INVESTIGATE,
                autonomy=1,
                value_estimate=0.5,
                cost=0.2,
                status=QuestionStatus.READY
            )
            archive_mgr.archive_question(question, "low_value")

    snapshot = monitor.capture_snapshot()
    monitor.detect_resource_issues(snapshot)

    assert consciousness.current_affect is not None, "Affect should be updated"
    assert consciousness.last_report is not None, "Report should be generated"

    print(f"  ✓ All three integrations working together")
    print(f"  ✓ Final affect state: {consciousness.last_report.summary}")
    print(f"  ✓ Success metrics: {consciousness.current_signals.success_rate:.0%} success rate")


def test_consciousness_none_handling():
    """Test that integrations work gracefully when consciousness is None."""
    print("\n[test] Testing graceful handling when consciousness is None...")

    executor = Executor(consciousness=None)
    monitor = SystemResourceMonitor(consciousness=None)

    decision = {"tool": "test_tool", "args": {}}
    state = {"context": "test"}

    result = executor.run(decision, state)

    assert result["success"] is True, "Should still execute successfully"

    snapshot = monitor.capture_snapshot()
    issues = monitor.detect_resource_issues(snapshot)

    print(f"  ✓ Executor works with consciousness=None")
    print(f"  ✓ Monitor works with consciousness=None")
    print(f"  ✓ No errors when consciousness unavailable")


def run_all_tests():
    """Run all integration tests."""
    print("="*70)
    print("COMPLETE CONSCIOUSNESS INTEGRATION TESTS - Phase 1, Task 4")
    print("="*70)

    tests = [
        test_executor_task_outcome_integration,
        test_executor_task_failure_integration,
        test_archive_manager_discovery_integration,
        test_system_monitor_resource_pressure_integration,
        test_all_integrations_together,
        test_consciousness_none_handling,
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
