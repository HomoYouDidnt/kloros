"""System-level healing actions for resource management."""

import subprocess
import psutil
import signal
from typing import Dict, Any, Optional, List
from pathlib import Path
from .actions import HealAction


class ClearSwapAction(HealAction):
    """Clear swap via swapoff/swapon cycle."""

    def apply(self, kloros_instance) -> bool:
        try:
            print("[action] Attempting to clear swap (swapoff -a && swapon -a)")

            result = subprocess.run(
                ['sudo', 'swapoff', '-a'],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"[action] swapoff failed: {result.stderr}")
                return False

            result = subprocess.run(
                ['sudo', 'swapon', '-a'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                print(f"[action] swapon failed: {result.stderr}")
                return False

            swap_after = psutil.swap_memory()
            print(f"[action] Swap cleared: {swap_after.percent:.1f}% used")

            self._rollback_data = {"cleared": True}
            return True

        except subprocess.TimeoutExpired:
            print("[action] Swap clear timed out")
            return False
        except Exception as e:
            print(f"[action] Swap clear failed: {e}")
            return False

    def rollback(self, kloros_instance) -> bool:
        return True


class KillDuplicateProcessAction(HealAction):
    """Kill duplicate processes by name, keeping only the oldest."""

    def apply(self, kloros_instance) -> bool:
        process_name = self.params.get("process_name")
        if not process_name:
            return False

        try:
            matching_procs = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    if process_name in ' '.join(proc.info['cmdline'] or []):
                        matching_procs.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if len(matching_procs) <= 1:
                print(f"[action] No duplicate processes found for {process_name}")
                return True

            matching_procs.sort(key=lambda p: p.info['create_time'])
            oldest = matching_procs[0]
            duplicates = matching_procs[1:]

            killed_pids = []
            for proc in duplicates:
                try:
                    print(f"[action] Killing duplicate process PID {proc.pid}")
                    proc.kill()
                    killed_pids.append(proc.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    print(f"[action] Failed to kill PID {proc.pid}: {e}")

            self._rollback_data = {
                "killed_pids": killed_pids,
                "kept_pid": oldest.pid
            }

            return len(killed_pids) > 0

        except Exception as e:
            print(f"[action] Failed to kill duplicate processes: {e}")
            return False

    def rollback(self, kloros_instance) -> bool:
        return True


class KillStuckProcessesAction(HealAction):
    """Kill processes stuck in D state (uninterruptible sleep)."""

    def apply(self, kloros_instance) -> bool:
        process_pattern = self.params.get("pattern", "")
        max_age_seconds = self.params.get("max_age_seconds", 3600)

        try:
            import time
            current_time = time.time()
            killed_pids = []

            for proc in psutil.process_iter(['pid', 'name', 'status', 'cmdline', 'create_time']):
                try:
                    if proc.info['status'] != psutil.STATUS_DISK_SLEEP:
                        continue

                    if process_pattern and process_pattern not in ' '.join(proc.info['cmdline'] or []):
                        continue

                    age = current_time - proc.info['create_time']
                    if age < max_age_seconds:
                        continue

                    print(f"[action] Killing stuck process PID {proc.pid} ({proc.info['name']})")
                    proc.kill()
                    killed_pids.append(proc.pid)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            self._rollback_data = {"killed_pids": killed_pids}

            if killed_pids:
                print(f"[action] Killed {len(killed_pids)} stuck processes")
                return True
            else:
                print("[action] No stuck processes found")
                return True

        except Exception as e:
            print(f"[action] Failed to kill stuck processes: {e}")
            return False

    def rollback(self, kloros_instance) -> bool:
        return True


class RestartServiceAction(HealAction):
    """Restart a systemd service."""

    def apply(self, kloros_instance) -> bool:
        service_name = self.params.get("service")
        if not service_name:
            return False

        try:
            print(f"[action] Restarting service: {service_name}")

            result = subprocess.run(
                ['sudo', 'systemctl', 'restart', service_name],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"[action] Service restart failed: {result.stderr}")
                return False

            print(f"[action] Service {service_name} restarted successfully")
            self._rollback_data = {"restarted": service_name}
            return True

        except subprocess.TimeoutExpired:
            print(f"[action] Service restart timed out")
            return False
        except Exception as e:
            print(f"[action] Service restart failed: {e}")
            return False

    def rollback(self, kloros_instance) -> bool:
        return True


SYSTEM_ACTION_CLASSES = {
    "clear_swap": ClearSwapAction,
    "kill_duplicate_process": KillDuplicateProcessAction,
    "kill_stuck_processes": KillStuckProcessesAction,
    "restart_service": RestartServiceAction,
}
