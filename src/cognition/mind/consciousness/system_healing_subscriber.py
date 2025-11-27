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
from src.orchestration.core.umn_bus import UMNPub

chem_pub = None


def _get_chem_pub():
    """Lazy initialization of UMNPub."""
    global chem_pub
    if chem_pub is None:
        chem_pub = UMNPub()
    return chem_pub


def check_emergency_brake() -> bool:
    """Check if emergency brake is active."""
    brake_flag = Path("/tmp/kloros_emergency_brake_active")
    return brake_flag.exists()


def emit_heal_request(strategy: str, context: dict, priority: str = 'normal'):
    """
    Emit HEAL_REQUEST signal via UMN.

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
        msg: JSON message dict from UMN
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
    Attempts skill-based optimization first for high-severity strain,
    then emits HEAL_REQUEST signals for resource optimization.

    Args:
        msg: JSON message dict from UMN
    """
    if check_emergency_brake():
        print("[system_healing] ⏸️  Emergency brake active, skipping healing")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        swap_used_mb = facts.get('swap_used_mb', 0)
        memory_used_pct = facts.get('memory_used_pct', 0)
        thread_count = facts.get('thread_count', 0)

        print(f"\n[system_healing] ⚠️  RESOURCE_STRAIN (intensity: {intensity:.2f})")
        print(f"  Memory: {memory_used_pct:.1f}% | Swap: {swap_used_mb:.0f}MB | Threads: {thread_count}")

        skill_attempted = False
        skill_success = False

        if swap_used_mb > 10000 or memory_used_pct > 70:
            print(f"  🎯 High memory pressure detected - attempting skill-based optimization")

            try:
                from src.cognition.mind.consciousness.skill_executor import SkillExecutor
                from src.cognition.mind.consciousness.skill_auto_executor import SkillAutoExecutor
                from src.cognition.mind.consciousness.skill_tracker import SkillTracker
                from dataclasses import asdict

                tracker = SkillTracker()

                effectiveness = tracker.get_skill_effectiveness('memory-optimization', 'memory', days=30)
                success_rate = effectiveness.get('success_rate', 0.0)

                print(f"    → Skill history: {effectiveness['total_executions']} executions, {success_rate:.1%} success rate")

                problem_context = {
                    'description': f'Memory pressure: {swap_used_mb:.0f}MB swap, {memory_used_pct:.1f}% RAM',
                    'evidence': {
                        'swap_used_mb': swap_used_mb,
                        'memory_used_pct': memory_used_pct,
                        'thread_count': thread_count,
                        'resource_type': facts.get('resource_type', 'memory')
                    },
                    'metrics': {
                        'thread_count': thread_count,
                        'swap_used_mb': swap_used_mb,
                        'memory_used_pct': memory_used_pct,
                        'intensity': intensity,
                        'investigation_failure_rate': facts.get('investigation_failure_rate', 0.0)
                    }
                }

                if success_rate < 0.3 and effectiveness['total_executions'] > 0:
                    problem_context['past_failures'] = {
                        'total': effectiveness['total_executions'],
                        'failures': effectiveness.get('failures', 0),
                        'success_rate': success_rate
                    }
                    print(f"    ⚠️  Low success rate detected - including past failures in context")

                print(f"    → Loading skill: memory-optimization")
                executor = SkillExecutor()
                auto_executor = SkillAutoExecutor()

                skill_attempted = True

                plan = executor.execute_skill('memory-optimization', problem_context)

                if plan:
                    print(f"    → Generated action plan: Phase={plan.phase}, Confidence={plan.confidence}")
                    print(f"    → {len(plan.actions)} actions planned")

                    if auto_executor.can_auto_execute('memory-optimization'):
                        print(f"    → 🤖 Auto-executing skill (safe, low-risk)")
                        result = auto_executor.execute_plan(plan, auto_execute=True)

                        if result:
                            print(f"    → ✓ Auto-execution completed: {result.outcome}")
                            print(f"    → Improvement: {result.improvement:.1%}")
                            skill_success = True
                        else:
                            print(f"    → ✗ Auto-execution failed")
                    else:
                        print(f"    → Manual approval required - emitting SKILL_EXECUTION_PLAN")
                        _get_chem_pub().emit(
                            "SKILL_EXECUTION_PLAN",
                            ecosystem="consciousness",
                            intensity=intensity,
                            facts={
                                "skill_name": 'memory-optimization',
                                "problem": problem_context['description'],
                                "plan": asdict(plan),
                                "auto_execute": False,
                                "trigger": "system_healing_subscriber"
                            }
                        )
                        skill_success = True
                else:
                    print(f"    → ✗ Failed to generate skill plan")

            except Exception as e:
                print(f"    ✗ Skill execution error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                tracker.close()

        if not skill_success or not skill_attempted:
            if skill_attempted and not skill_success:
                print(f"  → Falling back to HEAL_REQUEST")

            emit_heal_request(
                strategy='optimize_resources',
                context={
                    'resource_type': facts.get('resource_type', 'unknown'),
                    'usage_level': facts.get('level', 0.0),
                    'evidence': facts.get('evidence', []),
                    'swap_used_mb': swap_used_mb,
                    'memory_used_pct': memory_used_pct,
                    'thread_count': thread_count
                },
                priority='high' if intensity > 0.8 else 'normal'
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
        msg: JSON message dict from UMN
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
        from src.orchestration.core.umn_bus import UMNSub

        # Subscribe to system-level affective signals
        print("[system_healing] Subscribing to AFFECT_HIGH_RAGE...")
        rage_sub = UMNSub(
            topic="AFFECT_HIGH_RAGE",
            on_json=handle_high_rage,
            zooid_name="system_healing",
            niche="affective_actions"
        )

        print("[system_healing] Subscribing to AFFECT_RESOURCE_STRAIN...")
        resource_sub = UMNSub(
            topic="AFFECT_RESOURCE_STRAIN",
            on_json=handle_resource_strain,
            zooid_name="system_healing",
            niche="affective_actions"
        )

        print("[system_healing] Subscribing to AFFECT_REPETITIVE_ERROR...")
        repetitive_sub = UMNSub(
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
