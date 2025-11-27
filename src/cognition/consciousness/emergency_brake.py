#!/usr/bin/env python3
"""
Emergency Brake - Affective Action Tier 1

Listens for AFFECT_EMERGENCY_BRAKE signals and immediately halts
processing when PANIC > 0.7 or critical urgency detected.

This is the highest priority affective action - prevents thrashing
and runaway loops by forcing a pause for human intervention.
"""

import json
import time
import os
import sys
from pathlib import Path

# Global pause flag
PAUSE_FLAG_PATH = Path("/tmp/kloros_emergency_brake_active")


def set_emergency_brake(active: bool):
    """
    Set or clear the emergency brake flag.

    Args:
        active: True to activate brake, False to clear
    """
    if active:
        PAUSE_FLAG_PATH.write_text(str(time.time()))
        print(f"\n{'='*70}")
        print("🚨 EMERGENCY BRAKE ACTIVATED 🚨")
        print(f"{'='*70}")
        print("System paused due to critical affective state.")
        print("Runaway loops and processing halted.")
        print(f"\nBrake flag: {PAUSE_FLAG_PATH}")
        print(f"{'='*70}\n")
    else:
        if PAUSE_FLAG_PATH.exists():
            PAUSE_FLAG_PATH.unlink()
            print("[emergency_brake] ✅ Emergency brake CLEARED")


def is_brake_active() -> bool:
    """Check if emergency brake is currently active."""
    return PAUSE_FLAG_PATH.exists()


def handle_emergency_signal(msg: dict):
    """
    Handle AFFECT_EMERGENCY_BRAKE signal.

    Args:
        msg: JSON message dict from UMN
    """
    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 1.0)

        print(f"\n[emergency_brake] 🚨 EMERGENCY signal received")
        print(f"  Intensity: {intensity:.2f}")
        print(f"  Urgency: {facts.get('urgency', 'unknown')}")
        print(f"  Primary affects: {facts.get('primary_affects', [])}")

        # Activate emergency brake
        set_emergency_brake(True)

        # Log evidence
        evidence = facts.get('evidence', [])
        if evidence:
            print("\n  Evidence:")
            for item in evidence:
                print(f"    • {item}")

        # Check if self-remediation possible
        can_self_remediate = facts.get('can_self_remediate', False)
        if can_self_remediate:
            print("\n  ⚠️ System may be able to self-remediate")
            print("  Waiting for cognitive actions to attempt recovery...")
        else:
            print("\n  ⚠️ USER INTERVENTION REQUIRED")
            print("  System cannot self-remediate - manual action needed")

    except Exception as e:
        print(f"[emergency_brake] Error handling emergency signal: {e}")
        # Activate brake anyway on error
        set_emergency_brake(True)


def handle_critical_fatigue(msg: dict):
    """
    Handle AFFECT_CRITICAL_FATIGUE signal.

    Args:
        msg: JSON message dict from UMN
    """
    try:
        facts = msg.get('facts', {})
        fatigue = facts.get('fatigue', 0.0)

        print(f"\n[emergency_brake] ⚠️ CRITICAL FATIGUE detected")
        print(f"  Fatigue level: {fatigue:.0%}")
        print("  Activating emergency brake to prevent system degradation")

        set_emergency_brake(True)

        print("\n  Recommended action: Extended rest period required")
        print("  System should not resume until fatigue recovers")

    except Exception as e:
        print(f"[emergency_brake] Error handling fatigue signal: {e}")


def run_daemon():
    """
    Run emergency brake daemon.

    Subscribes to emergency signals and activates brake when needed.
    """
    print("[emergency_brake] Starting Emergency Brake Daemon")
    print(f"[emergency_brake] Brake flag: {PAUSE_FLAG_PATH}")

    # Clear any stale brake from previous runs
    set_emergency_brake(False)

    try:
        from src.orchestration.core.umn_bus import UMNSub

        # Subscribe to emergency signals
        print("[emergency_brake] Subscribing to AFFECT_EMERGENCY_BRAKE...")
        brake_sub = UMNSub(
            topic="AFFECT_EMERGENCY_BRAKE",
            on_json=handle_emergency_signal,
            zooid_name="emergency_brake",
            niche="affective_actions"
        )

        print("[emergency_brake] Subscribing to AFFECT_CRITICAL_FATIGUE...")
        fatigue_sub = UMNSub(
            topic="AFFECT_CRITICAL_FATIGUE",
            on_json=handle_critical_fatigue,
            zooid_name="emergency_brake",
            niche="affective_actions"
        )

        print("[emergency_brake] ✅ Emergency Brake Daemon ready")
        print("[emergency_brake] Monitoring for critical affective states...")

        # Keep daemon running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[emergency_brake] Daemon stopped by user")
        set_emergency_brake(False)
    except Exception as e:
        print(f"[emergency_brake] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_daemon()
