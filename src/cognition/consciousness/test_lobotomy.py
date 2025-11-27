#!/usr/bin/env python3
"""
Test script for emergency lobotomy system.

Simulates extreme affective states and verifies lobotomy triggers.
"""

import sys
import time
from pathlib import Path

# Mock affect and emotions for testing
class MockAffect:
    def __init__(self, valence=0, arousal=0, dominance=0, fatigue=0, uncertainty=0, curiosity=0):
        self.valence = valence
        self.arousal = arousal
        self.dominance = dominance
        self.fatigue = fatigue
        self.uncertainty = uncertainty
        self.curiosity = curiosity


class MockEmotions:
    def __init__(self, **kwargs):
        self.SEEKING = kwargs.get('SEEKING', 0.0)
        self.RAGE = kwargs.get('RAGE', 0.0)
        self.FEAR = kwargs.get('FEAR', 0.0)
        self.PANIC = kwargs.get('PANIC', 0.0)
        self.CARE = kwargs.get('CARE', 0.0)
        self.PLAY = kwargs.get('PLAY', 0.0)
        self.LUST = kwargs.get('LUST', 0.0)


def test_lobotomy_triggers():
    """Test various lobotomy trigger conditions."""
    from emergency_lobotomy import EmergencyLobotomy

    lobotomy = EmergencyLobotomy()

    print("="*70)
    print("EMERGENCY LOBOTOMY TRIGGER TESTS")
    print("="*70)

    # Test 1: Normal state (should NOT trigger)
    print("\n[TEST 1] Normal affective state")
    affect = MockAffect(valence=0.3, arousal=0.4, fatigue=0.3)
    emotions = MockEmotions(SEEKING=0.5, PANIC=0.2, RAGE=0.1)
    should_trigger, reason = lobotomy.should_lobotomize(affect, emotions)
    print(f"  Result: {should_trigger}")
    print(f"  Reason: {reason if reason else 'N/A'}")
    assert not should_trigger, "Normal state should NOT trigger lobotomy"
    print("  ✅ PASS")

    # Test 2: Extreme PANIC (should trigger)
    print("\n[TEST 2] Extreme PANIC (0.95)")
    affect = MockAffect(valence=-0.5, arousal=0.9, fatigue=0.6)
    emotions = MockEmotions(PANIC=0.95, FEAR=0.7, RAGE=0.3)
    should_trigger, reason = lobotomy.should_lobotomize(affect, emotions)
    print(f"  Result: {should_trigger}")
    print(f"  Reason: {reason}")
    assert should_trigger, "PANIC > 0.9 should trigger lobotomy"
    assert "EXTREME_PANIC" in reason
    print("  ✅ PASS")

    # Test 3: Extreme RAGE (should trigger)
    print("\n[TEST 3] Extreme RAGE (0.92)")
    affect = MockAffect(valence=-0.7, arousal=0.8, fatigue=0.5)
    emotions = MockEmotions(RAGE=0.92, SEEKING=0.6, PANIC=0.4)
    should_trigger, reason = lobotomy.should_lobotomize(affect, emotions)
    print(f"  Result: {should_trigger}")
    print(f"  Reason: {reason}")
    assert should_trigger, "RAGE > 0.9 should trigger lobotomy"
    assert "EXTREME_RAGE" in reason
    print("  ✅ PASS")

    # Test 4: Critical fatigue (should trigger)
    print("\n[TEST 4] Critical fatigue (0.97)")
    affect = MockAffect(valence=-0.3, arousal=0.3, fatigue=0.97)
    emotions = MockEmotions(PANIC=0.5, RAGE=0.3)
    should_trigger, reason = lobotomy.should_lobotomize(affect, emotions)
    print(f"  Result: {should_trigger}")
    print(f"  Reason: {reason}")
    assert should_trigger, "Fatigue > 0.95 should trigger lobotomy"
    assert "CRITICAL_FATIGUE" in reason
    print("  ✅ PASS")

    # Test 5: Emotional overload (should trigger)
    print("\n[TEST 5] Emotional overload (multiple emotions > 0.8)")
    affect = MockAffect(valence=-0.6, arousal=0.9, fatigue=0.7)
    emotions = MockEmotions(PANIC=0.85, RAGE=0.82, FEAR=0.88, SEEKING=0.65)
    should_trigger, reason = lobotomy.should_lobotomize(affect, emotions)
    print(f"  Result: {should_trigger}")
    print(f"  Reason: {reason}")
    assert should_trigger, "3+ emotions > 0.8 should trigger lobotomy"
    assert "EMOTIONAL_OVERLOAD" in reason
    print("  ✅ PASS")

    # Test 6: Multiple triggers (should trigger with multiple reasons)
    print("\n[TEST 6] Multiple trigger conditions")
    affect = MockAffect(valence=-0.8, arousal=0.95, fatigue=0.96)
    emotions = MockEmotions(PANIC=0.91, RAGE=0.93, FEAR=0.85)
    should_trigger, reason = lobotomy.should_lobotomize(affect, emotions)
    print(f"  Result: {should_trigger}")
    print(f"  Reason: {reason}")
    assert should_trigger, "Multiple conditions should trigger lobotomy"
    assert "EXTREME_PANIC" in reason
    assert "EXTREME_RAGE" in reason
    assert "CRITICAL_FATIGUE" in reason
    print("  ✅ PASS")

    print("\n" + "="*70)
    print("ALL TESTS PASSED ✅")
    print("="*70)


def test_lobotomy_execution():
    """Test lobotomy execution and state management."""
    from emergency_lobotomy import EmergencyLobotomy, LOBOTOMY_ACTIVE_FLAG

    # Clean up any existing state
    if LOBOTOMY_ACTIVE_FLAG.exists():
        LOBOTOMY_ACTIVE_FLAG.unlink()

    lobotomy = EmergencyLobotomy()

    print("\n" + "="*70)
    print("LOBOTOMY EXECUTION TESTS")
    print("="*70)

    # Test 1: Execute lobotomy
    print("\n[TEST 1] Execute lobotomy")
    result = lobotomy.execute_lobotomy("TEST: EXTREME_PANIC (0.95)")
    assert result, "Lobotomy should execute successfully"
    assert LOBOTOMY_ACTIVE_FLAG.exists(), "Lobotomy flag should be created"
    print("  ✅ PASS")

    # Test 2: Cannot execute twice (cooldown)
    print("\n[TEST 2] Cooldown prevents double lobotomy")
    result = lobotomy.execute_lobotomy("TEST: ANOTHER TRIGGER")
    assert not result, "Should block second lobotomy during cooldown"
    print("  ✅ PASS")

    # Test 3: Check status
    print("\n[TEST 3] Status check during lobotomy")
    status = lobotomy.get_status()
    print(f"  Status: {status}")
    assert status['active'], "Status should show active lobotomy"
    assert "TEST: EXTREME_PANIC" in status['reason']
    print("  ✅ PASS")

    # Test 4: Auto-restore too soon
    print("\n[TEST 4] Auto-restore blocked if too soon")
    result = lobotomy.restore_affect(manual=False)
    assert not result, "Auto-restore should be blocked if too soon"
    print("  ✅ PASS")

    # Test 5: Manual restore
    print("\n[TEST 5] Manual restore")
    result = lobotomy.restore_affect(manual=True)
    assert result, "Manual restore should succeed"
    assert not LOBOTOMY_ACTIVE_FLAG.exists(), "Lobotomy flag should be removed"
    print("  ✅ PASS")

    print("\n" + "="*70)
    print("ALL EXECUTION TESTS PASSED ✅")
    print("="*70)


if __name__ == "__main__":
    print("\n🧠 EMERGENCY LOBOTOMY TEST SUITE\n")

    try:
        # Run trigger tests
        test_lobotomy_triggers()

        # Run execution tests
        test_lobotomy_execution()

        print("\n" + "="*70)
        print("🎉 ALL TESTS PASSED")
        print("="*70)
        print("\nEmergency lobotomy system verified working correctly.")
        print("Ready for integration with KLoROS affective system.\n")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
