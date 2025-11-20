#!/usr/bin/env python3
"""
System Healing Subscriber - Affective Action Tier 2

Listens for affective signals (RAGE, RESOURCE_STRAIN, etc.) and triggers
existing HealExecutor playbooks to fix system-level issues.

Maps affective states → infrastructure healing actions.
"""

import json
import time
import sys
from pathlib import Path
from kloros.orchestration.chem_bus_v2 import ChemPub

chem_pub = None


def _get_chem_pub():
    """Lazy initialization of ChemPub."""
    global chem_pub
    if chem_pub is None:
        chem_pub = ChemPub()
    return chem_pub


def check_emergency_brake() -> bool:
    """Check if emergency brake is active."""
    brake_flag = Path("/tmp/kloros_emergency_brake_active")
    return brake_flag.exists()


def emit_heal_request(strategy: str, context: dict, priority: str = 'normal'):
    """
    Emit HEAL_REQUEST signal via ChemBus.

    Args:
        strategy: Healing strategy to execute (e.g., 'analyze_error_pattern')
        context: Context dict with evidence and pattern info
        priority: Priority level ('low', 'normal', 'high', 'critical')
    """
    try:
        intensity_map = {
            'low': 0.5,
            'normal': 0.7,
            'high': 0.85,
            'critical': 0.95
        }

        intensity = intensity_map.get(priority, 0.7)

        _get_chem_pub().emit(
            "HEAL_REQUEST",
            ecosystem="system_healing",
            intensity=intensity,
            facts={
                'strategy': strategy,
                'context': context,
                'priority': priority,
                'timestamp': time.time(),
                'requested_by': 'system_healing_subscriber'
            }
        )

        print(f"  📡 Emitted HEAL_REQUEST: {strategy} (priority: {priority})")

    except Exception as e:
        print(f"  ❌ Failed to emit HEAL_REQUEST: {e}")


def handle_high_rage(msg: dict):
    """
    Handle AFFECT_HIGH_RAGE signal.

    High RAGE indicates system frustration - likely repetitive failures
    or blocked actions. Emit HEAL_REQUEST signals for appropriate healing strategies.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[system_healing] ⏸️  Emergency brake active, skipping healing")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)
        root_causes = facts.get('root_causes', [])
        evidence = facts.get('evidence', [])

        print(f"\n[system_healing] ❌ HIGH_RAGE signal (intensity: {intensity:.2f})")
        print(f"  Root causes: {root_causes}")

        for cause in root_causes:
            if 'repetitive_errors' in cause or 'error_pattern' in cause:
                emit_heal_request(
                    strategy='analyze_error_pattern',
                    context={
                        'cause': cause,
                        'evidence': evidence,
                        'intensity': intensity
                    },
                    priority='high' if intensity > 0.85 else 'normal'
                )

            elif 'task_failures' in cause or 'blocked_actions' in cause:
                emit_heal_request(
                    strategy='restart_stuck_service',
                    context={
                        'cause': cause,
                        'evidence': evidence,
                        'intensity': intensity
                    },
                    priority='high'
                )

            elif 'resource_strain' in cause:
                emit_heal_request(
                    strategy='clear_cache',
                    context={
                        'cause': cause,
                        'evidence': evidence
                    },
                    priority='normal'
                )

    except Exception as e:
        print(f"[system_healing] Error handling HIGH_RAGE: {e}")
        import traceback
        traceback.print_exc()


def handle_resource_strain(msg: dict):
    """
    Handle AFFECT_RESOURCE_STRAIN signal.

    Resource strain indicates memory/CPU/context pressure.
    Emit HEAL_REQUEST signals for resource optimization.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[system_healing] ⏸️  Emergency brake active, skipping healing")
        return

    try:
        facts = msg.get('facts', {})

        emit_heal_request(
            strategy='optimize_resources',
            context={
                'resource_type': facts.get('resource_type', 'unknown'),
                'usage_level': facts.get('level', 0.0),
                'evidence': facts.get('evidence', [])
            },
            priority='normal'
        )

    except Exception as e:
        print(f"[system_healing] Error handling RESOURCE_STRAIN: {e}")
        import traceback
        traceback.print_exc()


def handle_repetitive_error(msg: dict):
    """
    Handle AFFECT_REPETITIVE_ERROR signal.

    Repetitive errors indicate stuck patterns - emit HEAL_REQUEST for
    error analysis and pattern detection.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[system_healing] ⏸️  Emergency brake active, skipping healing")
        return

    try:
        facts = msg.get('facts', {})

        emit_heal_request(
            strategy='analyze_error_pattern',
            context={
                'error_count': facts.get('error_count', 0),
                'error_type': facts.get('error_type', 'unknown'),
                'evidence': facts.get('evidence', [])
            },
            priority='high'
        )

    except Exception as e:
        print(f"[system_healing] Error handling REPETITIVE_ERROR: {e}")
        import traceback
        traceback.print_exc()


def run_daemon():
    """
    Run system healing subscriber daemon.

    Subscribes to affective signals and triggers HealExecutor playbooks.
    """
    print("[system_healing] Starting System Healing Subscriber")
    print("[system_healing] Tier 2: System infrastructure healing")

    try:
        from kloros.orchestration.chem_bus_v2 import ChemSub

        # Subscribe to system-level affective signals
        print("[system_healing] Subscribing to AFFECT_HIGH_RAGE...")
        rage_sub = ChemSub(
            topic="AFFECT_HIGH_RAGE",
            on_json=handle_high_rage,
            zooid_name="system_healing",
            niche="affective_actions"
        )

        print("[system_healing] Subscribing to AFFECT_RESOURCE_STRAIN...")
        resource_sub = ChemSub(
            topic="AFFECT_RESOURCE_STRAIN",
            on_json=handle_resource_strain,
            zooid_name="system_healing",
            niche="affective_actions"
        )

        print("[system_healing] Subscribing to AFFECT_REPETITIVE_ERROR...")
        repetitive_sub = ChemSub(
            topic="AFFECT_REPETITIVE_ERROR",
            on_json=handle_repetitive_error,
            zooid_name="system_healing",
            niche="affective_actions"
        )

        print("[system_healing] ✅ System Healing Subscriber ready")
        print("[system_healing] Monitoring for system-level affective signals...")
        print("[system_healing] NOTE: HealExecutor integration is placeholder only")

        # Keep daemon running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[system_healing] Daemon stopped by user")
    except Exception as e:
        print(f"[system_healing] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_daemon()
