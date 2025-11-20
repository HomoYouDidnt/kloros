#!/usr/bin/env python3
"""
Simple ChemBus Signal Emission Test

Directly emits affective signals via ChemBus to test the subscriber pipeline.
"""

import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kloros.orchestration.chem_bus_v2 import ChemPub, ChemMessage


def test_memory_pressure_signal():
    """Emit a test MEMORY_PRESSURE signal."""
    print("\n[test] Emitting AFFECT_MEMORY_PRESSURE signal...")

    chem_pub = ChemPub()

    # Create test message
    msg = ChemMessage(
        signal="AFFECT_MEMORY_PRESSURE",
        ecosystem="consciousness",
        intensity=0.75,
        facts={
            'root_causes': ['high_token_usage', 'context_pressure'],
            'evidence': [
                'Token usage at 85%',
                'Context window near capacity'
            ],
            'autonomous_actions': [
                'Summarize older conversation context',
                'Archive completed tasks to episodic memory'
            ],
            'can_self_remediate': True
        }
    )

    # Emit signal
    chem_pub.emit("AFFECT_MEMORY_PRESSURE", msg.to_bytes())
    print(f"[test] ✅ AFFECT_MEMORY_PRESSURE emitted (intensity: {msg.intensity})")
    print(f"[test] Root causes: {msg.facts['root_causes']}")


def test_high_rage_signal():
    """Emit a test HIGH_RAGE signal."""
    print("\n[test] Emitting AFFECT_HIGH_RAGE signal...")

    chem_pub = ChemPub()

    msg = ChemMessage(
        signal="AFFECT_HIGH_RAGE",
        ecosystem="consciousness",
        intensity=0.85,
        facts={
            'root_causes': ['task_failures', 'repetitive_errors'],
            'evidence': [
                'Same error occurring 15+ times',
                'Unable to make progress on current task'
            ],
            'autonomous_actions': [
                'Trigger self-heal playbooks',
                'Analyze error patterns'
            ],
            'can_self_remediate': True
        }
    )

    chem_pub.emit("AFFECT_HIGH_RAGE", msg.to_bytes())
    print(f"[test] ✅ AFFECT_HIGH_RAGE emitted (intensity: {msg.intensity})")
    print(f"[test] Root causes: {msg.facts['root_causes']}")


if __name__ == "__main__":
    print("="*70)
    print("CHEMBUS AFFECTIVE SIGNAL TEST")
    print("="*70)
    print("\nEmitting test signals via ChemBus...")
    print("Subscribers should receive and process these signals.\n")

    # Test 1: Memory pressure
    test_memory_pressure_signal()
    time.sleep(1)  # Give subscribers time to process

    # Test 2: High RAGE
    test_high_rage_signal()
    time.sleep(1)

    print("\n" + "="*70)
    print("\n[test] All test signals emitted!")
    print("[test] Check subscriber daemon outputs to see responses.")
    print("="*70 + "\n")
