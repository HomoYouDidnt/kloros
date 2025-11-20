"""Runtime system health monitoring and auto-healing."""

import time
import psutil
import threading
from typing import Optional, Dict, Any, List
from .events import HealEvent, mk_event
from .playbook_dsl import load_playbooks, find_matching_playbooks, Playbook
from .executor import HealExecutor
from .policy import Guardrails
from .health import HealthProbes


class SystemHealthMonitor:
    """Active monitor for system resource health."""

    def __init__(
        self,
        kloros_instance,
        check_interval_seconds: int = 60,
        swap_warning_threshold: int = 70,
        swap_critical_threshold: int = 90,
        memory_critical_gb: float = 1.0
    ):
        """Initialize system health monitor.

        Args:
            kloros_instance: KLoROS instance to monitor
            check_interval_seconds: How often to check system health
            swap_warning_threshold: Swap usage % to trigger warning
            swap_critical_threshold: Swap usage % to trigger critical healing
            memory_critical_gb: Available memory threshold (GB)
        """
        self.kloros = kloros_instance
        self.check_interval = check_interval_seconds
        self.swap_warning = swap_warning_threshold
        self.swap_critical = swap_critical_threshold
        self.memory_critical = memory_critical_gb * (1024**3)

        self.playbooks: List[Playbook] = load_playbooks("/home/kloros/self_heal_playbooks.yaml")
        self.health_probes = HealthProbes(kloros_instance)
        self.guardrails = Guardrails()
        self.executor = HealExecutor(self.guardrails, self.health_probes)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_check_time = 0
        self._events_triggered = []

        print("[system-monitor] Initialized with active system health monitoring")

    def start(self):
        """Start the monitoring thread."""
        if self._running:
            print("[system-monitor] Already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"[system-monitor] Started (checking every {self.check_interval}s)")

    def stop(self):
        """Stop the monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[system-monitor] Stopped")

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                self._check_and_heal()
            except Exception as e:
                print(f"[system-monitor] Error in monitoring loop: {e}")

            time.sleep(self.check_interval)

    def _check_and_heal(self):
        """Check system health and trigger healing if needed."""
        self._last_check_time = time.time()

        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            if swap.percent >= self.swap_critical:
                self._trigger_healing(
                    kind="swap_exhaustion",
                    severity="critical",
                    context={
                        "swap_percent": swap.percent,
                        "swap_used_gb": swap.used / (1024**3),
                        "memory_available_gb": mem.available / (1024**3)
                    }
                )

            elif swap.percent >= self.swap_warning:
                self._trigger_healing(
                    kind="swap_exhaustion",
                    severity="warning",
                    context={
                        "swap_percent": swap.percent,
                        "swap_used_gb": swap.used / (1024**3)
                    }
                )

            if mem.available < self.memory_critical:
                self._check_duplicate_processes()

            stuck_count = self._check_stuck_processes()
            if stuck_count > 3:
                self._trigger_healing(
                    kind="stuck_processes",
                    severity="warning",
                    context={"stuck_count": stuck_count}
                )

        except Exception as e:
            print(f"[system-monitor] Health check failed: {e}")

    def _check_duplicate_processes(self):
        """Check for duplicate kloros_voice processes."""
        try:
            kloros_procs = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'kloros_voice' in cmdline:
                        kloros_procs.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if len(kloros_procs) > 1:
                print(f"[system-monitor] Found {len(kloros_procs)} kloros_voice processes")
                self._trigger_healing(
                    kind="duplicate_process",
                    severity="warning",
                    context={"process_count": len(kloros_procs)}
                )

        except Exception as e:
            print(f"[system-monitor] Duplicate process check failed: {e}")

    def _check_stuck_processes(self) -> int:
        """Check for processes stuck in D state.

        Returns:
            Number of stuck processes found
        """
        stuck_count = 0
        try:
            for proc in psutil.process_iter(['status', 'name']):
                try:
                    if proc.info['status'] == psutil.STATUS_DISK_SLEEP:
                        stuck_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            print(f"[system-monitor] Stuck process check failed: {e}")

        return stuck_count

    def _trigger_healing(self, kind: str, severity: str, context: Dict[str, Any]):
        """Trigger healing for a detected issue.

        Args:
            kind: Issue kind (e.g., 'swap_exhaustion')
            severity: Severity level ('warning', 'critical')
            context: Additional context about the issue
        """
        event_key = f"{kind}:{severity}"
        if event_key in self._events_triggered:
            return

        print(f"[system-monitor] Detected {severity} {kind}: {context}")

        event = mk_event(
            source="system_health",
            kind=kind,
            severity=severity,
            **context
        )

        matching_playbooks = find_matching_playbooks(event, self.playbooks)

        if matching_playbooks:
            playbook = matching_playbooks[0]
            print(f"[system-monitor] Executing playbook: {playbook.name}")

            success = self.executor.execute_playbook(playbook, event, self.kloros)

            if success:
                print(f"[system-monitor] ✓ Healing successful for {kind}")
                self._events_triggered.append(event_key)
            else:
                print(f"[system-monitor] ✗ Healing failed for {kind}")
        else:
            print(f"[system-monitor] No playbook found for {kind}")

    def get_status(self) -> Dict[str, Any]:
        """Get monitor status.

        Returns:
            Dict with status information
        """
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return {
            "running": self._running,
            "check_interval": self.check_interval,
            "last_check": self._last_check_time,
            "events_triggered": len(self._events_triggered),
            "current_state": {
                "swap_percent": swap.percent,
                "memory_available_gb": mem.available / (1024**3),
                "memory_percent": mem.percent
            }
        }
