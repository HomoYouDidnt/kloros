#!/usr/bin/env python3
"""
HealExecutor Daemon - System Healing Playbook Executor

Subscribes to HEAL_REQUEST signals via UMN and executes appropriate
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
        import os
        self.dry_run = os.environ.get('KLR_HEAL_DRY_RUN', '0') == '1'

        self.playbooks: Dict[str, Callable] = {
            'analyze_error_pattern': self.analyze_errors,
            'restart_stuck_service': self.restart_service,
            'clear_cache': self.clear_caches,
            'optimize_resources': self.optimize_resources,
        }

        self.execution_log_path = Path("/tmp/kloros_healing_actions.log")
        self.last_execution = {}
        self.cooldown_seconds = 60

        self.memory_store = None
        self._memory_store_initialized = False

        if self.dry_run:
            print("[heal_executor] 🔬 DRY-RUN MODE ENABLED - No destructive operations will be performed")

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
            msg: UMN message dict
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

    def _initialize_memory_store(self) -> None:
        """Initialize MemoryStore for querying error patterns (lazy-loaded)."""
        if self._memory_store_initialized:
            return

        self._memory_store_initialized = True
        try:
            from src.cognition.mind.memory.storage import MemoryStore
            self.memory_store = MemoryStore()
            print("[heal_executor] Initialized MemoryStore (lazy-loaded)")
        except ImportError:
            try:
                from src.memory.storage import MemoryStore
                self.memory_store = MemoryStore()
                print("[heal_executor] Initialized MemoryStore (lazy-loaded)")
            except Exception as e:
                print(f"[heal_executor] Warning: Could not initialize MemoryStore: {e}")
                self.memory_store = None
        except Exception as e:
            print(f"[heal_executor] Warning: Could not initialize MemoryStore: {e}")
            self.memory_store = None

    def _query_error_events(self, days: int = 7) -> list:
        """Query recent error events from MemoryStore."""
        if not self.memory_store:
            return []

        try:
            cutoff_time = time.time() - (days * 24 * 3600)
            conn = self.memory_store._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, timestamp, content, metadata
                FROM events
                WHERE event_type = 'error_occurred'
                AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (cutoff_time,))

            rows = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'timestamp': row[1],
                    'content': row[2],
                    'metadata': row[3]
                }
                for row in rows
            ]
        except Exception as e:
            print(f"    Warning: Error querying events: {e}")
            return []

    def analyze_errors(self, context: Dict[str, Any]) -> bool:
        """
        Analyze error patterns.

        Args:
            context: Error context (with optional 'days' parameter)

        Returns:
            True if successful, False if failed
        """
        print("  [playbook] Analyzing error patterns...")
        print(f"    Context: {context}")

        # Lazy-load MemoryStore only when actually needed
        if not self._memory_store_initialized:
            self._initialize_memory_store()

        if not self.memory_store:
            print("    Error: MemoryStore not available")
            return False

        days = context.get('days', 7)
        error_events = self._query_error_events(days)

        if not error_events:
            print(f"    No error events found in last {days} days")
            return True

        print(f"    Found {len(error_events)} error events")

        error_types = {}
        for event in error_events:
            error_content = event.get('content', 'unknown')
            error_types[error_content] = error_types.get(error_content, 0) + 1

        print("    Error pattern analysis:")
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"      - {error_type}: {count} occurrences")

        if error_types:
            most_common = max(error_types.items(), key=lambda x: x[1])
            if most_common[1] >= 3:
                print(f"    ⚠️  High-frequency error detected: {most_common[0]} ({most_common[1]}x)")

        return True

    def restart_service(self, context: Dict[str, Any]) -> bool:
        """
        Restart stuck service.

        Args:
            context: Service context

        Returns:
            True if successful
        """
        print("  [playbook] Checking for stuck services...")
        print(f"    Context: {context}")

        service_type = context.get('service_type', 'background_processes')

        if service_type == 'background_processes':
            try:
                import subprocess
                result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                lines = result.stdout.splitlines()
                python_processes = [l for l in lines if 'python' in l.lower()]

                print(f"    Found {len(python_processes)} Python processes")

                if python_processes:
                    print("    Active processes (showing first 5):")
                    for proc in python_processes[:5]:
                        parts = proc.split()
                        if len(parts) >= 11:
                            pid = parts[1]
                            cmd = ' '.join(parts[10:])
                            print(f"      PID {pid}: {cmd[:80]}")

                return True
            except Exception as e:
                print(f"    Error checking processes: {e}")
                return False
        else:
            print(f"    Service type '{service_type}' not supported yet")
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

        scope = context.get('scope', 'python_cache')
        cleared_count = 0

        if scope == 'python_cache':
            try:
                import shutil
                for pycache_dir in Path('/home/kloros/src').rglob('__pycache__'):
                    if pycache_dir.is_dir():
                        try:
                            if self.dry_run:
                                print(f"    [DRY-RUN] Would remove: {pycache_dir}")
                                cleared_count += 1
                            else:
                                print(f"    Removing: {pycache_dir}")
                                shutil.rmtree(pycache_dir)
                                cleared_count += 1
                        except PermissionError:
                            print(f"    Skipping (permission denied): {pycache_dir}")
                        except Exception as e:
                            print(f"    Skipping (error): {pycache_dir} - {e}")

                if self.dry_run:
                    print(f"    [DRY-RUN] Would clear {cleared_count} __pycache__ directories")
                else:
                    print(f"    Cleared {cleared_count} __pycache__ directories")
                return True
            except Exception as e:
                print(f"    Warning: {e}")
                return True

        elif scope == 'temp_files':
            try:
                age_days = context.get('age_days', 7)
                cutoff_time = time.time() - (age_days * 24 * 3600)

                tmp_path = Path('/tmp')
                for tmp_file in tmp_path.glob('kloros_*'):
                    try:
                        if tmp_file.stat().st_mtime < cutoff_time:
                            if self.dry_run:
                                print(f"    [DRY-RUN] Would remove old file: {tmp_file.name}")
                                cleared_count += 1
                            else:
                                print(f"    Removing old file: {tmp_file.name}")
                                tmp_file.unlink()
                                cleared_count += 1
                    except PermissionError:
                        print(f"    Skipping (permission denied): {tmp_file.name}")
                    except Exception as e:
                        print(f"    Skipping (error): {tmp_file.name} - {e}")

                if self.dry_run:
                    print(f"    [DRY-RUN] Would clear {cleared_count} old temporary files")
                else:
                    print(f"    Cleared {cleared_count} old temporary files")
                return True
            except Exception as e:
                print(f"    Warning: {e}")
                return True

        else:
            print(f"    Unknown scope: {scope}")
            return True

    def optimize_resources(self, context: Dict[str, Any]) -> bool:
        """
        Optimize resource usage.

        Args:
            context: Resource context

        Returns:
            True if successful
        """
        print("  [playbook] Analyzing resource usage...")
        print(f"    Context: {context}")

        resource_type = context.get('resource_type', 'memory')

        if resource_type == 'memory':
            try:
                import psutil
                mem = psutil.virtual_memory()

                print(f"    Memory usage: {mem.percent}%")
                print(f"    Available: {mem.available / (1024**3):.2f} GB")
                print(f"    Used: {mem.used / (1024**3):.2f} GB")

                if mem.percent > 80:
                    print("    ⚠️  High memory usage detected")
                    print("    Recommendation: Consider triggering system_healing MEMORY_PRESSURE")
                elif mem.percent > 90:
                    print("    🚨 Critical memory usage!")
                    print("    Recommendation: Immediate memory cleanup needed")

                return True
            except ImportError:
                print("    Warning: psutil not available, using basic analysis")
                return True
            except Exception as e:
                print(f"    Error analyzing memory: {e}")
                return False

        elif resource_type == 'disk':
            try:
                import shutil
                total, used, free = shutil.disk_usage('/')

                usage_percent = (used / total) * 100
                print(f"    Disk usage: {usage_percent:.1f}%")
                print(f"    Free: {free / (1024**3):.2f} GB")

                if usage_percent > 90:
                    print("    ⚠️  High disk usage detected")

                return True
            except Exception as e:
                print(f"    Error analyzing disk: {e}")
                return False

        else:
            print(f"    Resource type '{resource_type}' analysis not implemented yet")
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
        from src.orchestration.core.umn_bus import UMNSub

        executor = HealExecutor()

        heal_sub = UMNSub(
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
