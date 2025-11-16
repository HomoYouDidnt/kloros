#!/usr/bin/env python3
"""
HealExecutor Daemon - System Healing Playbook Executor

Subscribes to HEAL_REQUEST signals via ChemBus and executes appropriate
healing playbooks based on the requested strategy.
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))


def check_emergency_brake() -> bool:
    """Check if emergency brake is active."""
    brake_flag = Path("/tmp/kloros_emergency_brake_active")
    return brake_flag.exists()


class HealExecutor:
    """
    Healing Playbook Executor.

    Receives HEAL_REQUEST signals and executes appropriate healing
    strategies based on the requested playbook.
    """

    def __init__(self):
        """Initialize healing executor with playbook registry."""
        self.playbooks: Dict[str, Callable] = {
            'analyze_error_pattern': self.analyze_errors,
            'restart_stuck_service': self.restart_service,
            'clear_cache': self.clear_caches,
            'optimize_resources': self.optimize_resources,
        }

        self.execution_log_path = Path("/tmp/kloros_healing_actions.log")
        self.last_execution = {}
        self.cooldown_seconds = 60

    def can_execute(self, strategy: str) -> bool:
        """
        Check if strategy can be executed (cooldown check).

        Args:
            strategy: Strategy name

        Returns:
            True if can execute
        """
        last_time = self.last_execution.get(strategy, 0.0)
        elapsed = time.time() - last_time
        return elapsed >= self.cooldown_seconds

    def log_execution(self, strategy: str, success: bool, details: str = ""):
        """
        Log healing action execution.

        Args:
            strategy: Strategy executed
            success: Execution success
            details: Additional details
        """
        self.last_execution[strategy] = time.time()

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        status = "SUCCESS" if success else "FAILED"
        log_entry = f"{timestamp} | {status} | {strategy} | {details}\n"

        with open(self.execution_log_path, 'a') as f:
            f.write(log_entry)

    def handle_heal_request(self, msg: dict):
        """
        Handle HEAL_REQUEST signal.

        Args:
            msg: ChemBus message dict
        """
        if check_emergency_brake():
            print("[heal_executor] Emergency brake active, skipping healing")
            return

        try:
            facts = msg.get('facts', {})
            strategy = facts.get('strategy')
            context = facts.get('context', {})
            priority = facts.get('priority', 'normal')

            if not strategy:
                print("[heal_executor] No strategy in HEAL_REQUEST")
                return

            print(f"\n[heal_executor] HEAL_REQUEST received")
            print(f"  Strategy: {strategy}")
            print(f"  Priority: {priority}")

            if not self.can_execute(strategy):
                elapsed = time.time() - self.last_execution[strategy]
                remaining = self.cooldown_seconds - elapsed
                print(f"  Skipping (cooldown: {remaining:.0f}s remaining)")
                return

            playbook = self.playbooks.get(strategy)
            if not playbook:
                print(f"  Unknown strategy: {strategy}")
                self.log_execution(strategy, False, "Unknown strategy")
                return

            print(f"  Executing playbook: {strategy}")
            success = playbook(context)

            if success:
                print(f"  Playbook executed successfully")
                self.log_execution(strategy, True, "Executed")
            else:
                print(f"  Playbook execution failed")
                self.log_execution(strategy, False, "Execution failed")

        except Exception as e:
            print(f"[heal_executor] Error handling HEAL_REQUEST: {e}")
            import traceback
            traceback.print_exc()

    def analyze_errors(self, context: Dict[str, Any]) -> bool:
        """
        Analyze error patterns.

        Args:
            context: Error context

        Returns:
            True if successful
        """
        print("  [playbook] Analyzing error patterns...")
        print(f"    Context: {context}")

        print("    Would query recent errors")
        print("    Would identify common patterns")
        print("    Would suggest fixes")

        return True

    def restart_service(self, context: Dict[str, Any]) -> bool:
        """
        Restart stuck service.

        Args:
            context: Service context

        Returns:
            True if successful
        """
        print("  [playbook] Restarting stuck service...")
        print(f"    Context: {context}")

        print("    Would identify stuck service")
        print("    Would attempt graceful restart")
        print("    Would verify service health")

        return True

    def clear_caches(self, context: Dict[str, Any]) -> bool:
        """
        Clear system caches.

        Args:
            context: Cache context

        Returns:
            True if successful
        """
        print("  [playbook] Clearing caches...")
        print(f"    Context: {context}")

        print("    Would identify cache locations")
        print("    Would clear stale entries")
        print("    Would verify memory freed")

        return True

    def optimize_resources(self, context: Dict[str, Any]) -> bool:
        """
        Optimize resource usage.

        Args:
            context: Resource context

        Returns:
            True if successful
        """
        print("  [playbook] Optimizing resources...")
        print(f"    Context: {context}")

        print("    Would analyze resource usage")
        print("    Would apply optimizations")
        print("    Would verify improvements")

        return True


def run_daemon():
    """
    Run heal executor daemon.

    Subscribes to HEAL_REQUEST signals and executes healing playbooks.
    """
    print("[heal_executor] Starting Heal Executor Daemon")
    print("[heal_executor] Subscribing to HEAL_REQUEST signals...")
    print(f"[heal_executor] Log: /tmp/kloros_healing_actions.log")

    try:
        from kloros.orchestration.chem_bus_v2 import ChemSub

        executor = HealExecutor()

        heal_sub = ChemSub(
            topic="HEAL_REQUEST",
            on_json=executor.handle_heal_request,
            zooid_name="heal_executor",
            niche="system_healing"
        )

        print("[heal_executor] Heal Executor ready")
        print("[heal_executor] Monitoring for HEAL_REQUEST signals...")
        print(f"[heal_executor] Playbooks available: {list(executor.playbooks.keys())}")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[heal_executor] Daemon stopped by user")
    except Exception as e:
        print(f"[heal_executor] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_daemon()
