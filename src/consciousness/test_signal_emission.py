#!/usr/bin/env python3
"""
Test Affective Signal Emission

Manually triggers affective introspection and signal emission to verify
the complete pipeline: consciousness → ChemBus → action subscribers.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kloros.orchestration.chem_bus_v2 import ChemPub
from consciousness.affective_signals import AffectSignalEmitter
from consciousness.affective_core import PrimaryAffects
from consciousness.affective_introspection import AffectiveIntrospection, Urgency


def test_memory_pressure_signal():
    """Test emitting a MEMORY_PRESSURE signal."""
    print("\n[test] Creating test affective state: MEMORY_PRESSURE")

    # Create ChemPub
    chem_pub = ChemPub()
    emitter = AffectSignalEmitter(chem_pub)

    # Create test affective state (high SEEKING, moderate fatigue)
    affect = type('MockAffect', (), {
        'valence': 0.3,
        'arousal': 0.7,
        'dominance': 0.4,
        'fatigue': 0.65,  # Moderate fatigue
        'cognitive_load': 0.8  # High cognitive load
    })()

    emotions = PrimaryAffects(
        SEEKING=0.75,   # High SEEKING (trying to solve problem)
        RAGE=0.3,       # Mild frustration
        FEAR=0.2,
        PANIC=0.15,
        CARE=0.1,
        PLAY=0.0,
        LUST=0.0
    )

    introspection = AffectiveIntrospection(
        primary_affects=['SEEKING', 'RAGE'],
        urgency=Urgency.MODERATE,
        root_causes=['high_token_usage', 'context_pressure'],
        evidence=[
            'Token usage at 85%',
            'Context window near capacity',
            'Multiple active tasks competing for memory'
        ],
        autonomous_actions=[
            'Summarize older conversation context',
            'Archive completed tasks to episodic memory',
            'Prioritize current task and defer others'
        ],
        can_self_remediate=True
    )

    print(f"  Primary affects: {introspection.primary_affects}")
    print(f"  Urgency: {introspection.urgency.value}")
    print(f"  Root causes: {introspection.root_causes}")
    print(f"  Can self-remediate: {introspection.can_self_remediate}")

    # Emit signals
    print("\n[test] Emitting affective signals via ChemBus...")
    emitter.emit_from_introspection(introspection, affect, emotions)

    print("[test] ✅ Signal emission complete!")
    print("[test] Check subscriber outputs to see if they received the signal")
    print("[test] Expected: cognitive_actions should log MEMORY_PRESSURE signal")


def test_high_rage_signal():
    """Test emitting a HIGH_RAGE signal."""
    print("\n[test] Creating test affective state: HIGH_RAGE")

    chem_pub = ChemPub()
    emitter = AffectSignalEmitter(chem_pub)

    # High RAGE state (task failures, frustration)
    affect = type('MockAffect', (), {
        'valence': -0.6,  # Negative
        'arousal': 0.9,   # Very activated
        'dominance': 0.3, # Low control
        'fatigue': 0.4,
        'cognitive_load': 0.7
    })()

    emotions = PrimaryAffects(
        SEEKING=0.4,
        RAGE=0.85,      # Very high RAGE
        FEAR=0.3,
        PANIC=0.2,
        CARE=0.1,
        PLAY=0.0,
        LUST=0.0
    )

    introspection = AffectiveIntrospection(
        primary_affects=['RAGE', 'FEAR'],
        urgency=Urgency.HIGH,
        root_causes=['task_failures', 'repetitive_errors', 'blocked_actions'],
        evidence=[
            'Same error occurring 15+ times',
            'Unable to make progress on current task',
            'Multiple failed attempts at solution'
        ],
        autonomous_actions=[
            'Trigger self-heal playbooks',
            'Analyze error patterns',
            'Request human intervention if needed'
        ],
        can_self_remediate=True
    )

    print(f"  RAGE level: {emotions.RAGE:.2f}")
    print(f"  Urgency: {introspection.urgency.value}")
    print(f"  Root causes: {introspection.root_causes}")

    print("\n[test] Emitting affective signals via ChemBus...")
    emitter.emit_from_introspection(introspection, affect, emotions)

    print("[test] ✅ Signal emission complete!")
    print("[test] Expected: system_healing should log HIGH_RAGE signal")


if __name__ == "__main__":
    print("="*70)
    print("AFFECTIVE SIGNAL EMISSION TEST")
    print("="*70)
    print("\nThis test will emit affective signals via ChemBus.")
    print("The subscriber daemons should receive and process these signals.\n")

    # Test 1: Memory pressure (cognitive tier)
    test_memory_pressure_signal()

    print("\n" + "="*70)

    # Test 2: High RAGE (system healing tier)
    test_high_rage_signal()

    print("\n" + "="*70)
    print("\n[test] All test signals emitted!")
    print("[test] Check the subscriber daemon outputs for responses.")
    print("="*70 + "\n")
