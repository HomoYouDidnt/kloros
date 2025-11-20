"""
SPICA Derivative: System Health & Resource Management

SPICA-based system health testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- Swap exhaustion detection and remediation
- Memory pressure handling
- CPU load management
- Disk space monitoring

KPIs: swap_remediation_rate, memory_available_gb, cpu_load_avg, disk_free_gb
"""
import time
import subprocess
import psutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result


@dataclass
class SystemHealthTestConfig:
    """Configuration for system health tests."""
    swap_warning_percent: int = 70
    swap_critical_percent: int = 90
    memory_warning_gb: float = 3.0
    memory_critical_gb: float = 1.0
    max_test_duration_sec: int = 120
    max_remediation_attempts: int = 3


@dataclass
class SystemHealthTestResult:
    """Result from a system health test."""
    test_id: str
    status: str
    issue_detected: bool
    issue_type: str
    severity: str
    remediation_attempted: bool
    remediation_success: bool
    before_state: Dict
    after_state: Dict
    latency_ms: float
    cpu_percent: float
    memory_mb: float
    epoch_id: str


class SpicaSystemHealth(SpicaBase):
    """SPICA derivative for system health monitoring and remediation."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[SystemHealthTestConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-syshealth-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'swap_warning_percent': test_config.swap_warning_percent,
                'swap_critical_percent': test_config.swap_critical_percent,
                'memory_warning_gb': test_config.memory_warning_gb,
                'memory_critical_gb': test_config.memory_critical_gb,
                'max_test_duration_sec': test_config.max_test_duration_sec,
                'max_remediation_attempts': test_config.max_remediation_attempts
            })

        super().__init__(spica_id=spica_id, domain="system_health", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.test_config = test_config or SystemHealthTestConfig()
        self.results: List[SystemHealthTestResult] = []
        self.record_telemetry("spica_syshealth_init", {
            "swap_warning_percent": self.test_config.swap_warning_percent,
            "swap_critical_percent": self.test_config.swap_critical_percent
        })

    def _get_system_state(self) -> Dict:
        """Get current system resource state."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        load_avg = psutil.getloadavg()
        disk = psutil.disk_usage('/')

        state = {
            'memory_available_gb': mem.available / (1024**3),
            'memory_percent': mem.percent,
            'swap_used_gb': swap.used / (1024**3),
            'swap_total_gb': swap.total / (1024**3),
            'swap_percent': swap.percent,
            'cpu_percent': cpu_percent,
            'load_avg_1min': load_avg[0],
            'disk_free_gb': disk.free / (1024**3),
            'disk_percent': disk.percent
        }
        
        self.record_telemetry("system_state_read", state)
        return state

    def _simulate_swap_pressure(self, target_percent: int = 95) -> bool:
        """Simulate swap exhaustion for testing (safe simulation)."""
        marker = Path("/tmp/kloros_swap_simulation.marker")
        marker.write_text(f"{target_percent}\n")
        self.record_telemetry("swap_pressure_simulated", {"target_percent": target_percent})
        return True

    def _detect_swap_issue(self) -> Optional[Dict]:
        """Detect swap exhaustion issues."""
        marker = Path("/tmp/kloros_swap_simulation.marker")
        if marker.exists():
            simulated_percent = int(marker.read_text().strip())
            if simulated_percent >= self.test_config.swap_critical_percent:
                issue = {'type': 'swap', 'severity': 'critical', 'swap_percent': simulated_percent, 'simulated': True}
                self.record_telemetry("swap_issue_detected", issue)
                return issue
            elif simulated_percent >= self.test_config.swap_warning_percent:
                issue = {'type': 'swap', 'severity': 'warning', 'swap_percent': simulated_percent, 'simulated': True}
                self.record_telemetry("swap_issue_detected", issue)
                return issue

        swap = psutil.swap_memory()
        swap_percent = swap.percent

        if swap_percent >= self.test_config.swap_critical_percent:
            issue = {'type': 'swap', 'severity': 'critical', 'swap_percent': swap_percent, 'simulated': False}
            self.record_telemetry("swap_issue_detected", issue)
            return issue
        elif swap_percent >= self.test_config.swap_warning_percent:
            issue = {'type': 'swap', 'severity': 'warning', 'swap_percent': swap_percent, 'simulated': False}
            self.record_telemetry("swap_issue_detected", issue)
            return issue

        self.record_telemetry("swap_check_ok", {"swap_percent": swap_percent})
        return None

    def _remediate_swap_issue(self, issue: Dict) -> bool:
        """Attempt to remediate swap exhaustion."""
        if issue.get('simulated'):
            marker = Path("/tmp/kloros_swap_simulation.marker")
            marker.unlink(missing_ok=True)
            self.record_telemetry("swap_remediation", {"method": "clear_simulation", "success": True})
            return True

        try:
            result = subprocess.run(['sudo', 'swapoff', '-a'], capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                self.record_telemetry("swap_remediation", {"method": "swapoff", "success": False, "error": result.stderr})
                return False

            result = subprocess.run(['sudo', 'swapon', '-a'], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.record_telemetry("swap_remediation", {"method": "swapon", "success": False, "error": result.stderr})
                return False

            time.sleep(2)
            swap = psutil.swap_memory()

            success = swap.percent < self.test_config.swap_warning_percent
            self.record_telemetry("swap_remediation", {"method": "swapoff_swapon", "success": success, "final_percent": swap.percent})
            return success

        except subprocess.TimeoutExpired:
            self.record_telemetry("swap_remediation", {"method": "swapoff_swapon", "success": False, "error": "timeout"})
            return False
        except Exception as e:
            self.record_telemetry("swap_remediation", {"method": "swapoff_swapon", "success": False, "error": str(e)})
            return False

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """SPICA evaluate() interface for system health tests."""
        simulate = test_input.get("simulate", True)
        epoch_id = (context or {}).get("epoch_id", "unknown")
        result = self.run_swap_exhaustion_test(epoch_id, simulate)
        
        fitness = 1.0 if result.status == "pass" else 0.0
        if result.remediation_success:
            fitness = 0.8  # Partial credit for successful remediation
        
        return {
            "fitness": fitness,
            "test_id": result.test_id,
            "status": result.status,
            "metrics": asdict(result),
            "spica_id": self.spica_id
        }

    def run_swap_exhaustion_test(self, epoch_id: str, simulate: bool = True) -> SystemHealthTestResult:
        """Test swap exhaustion detection and remediation."""
        start = time.time()
        test_id = f"system_health::swap_exhaustion::{'simulated' if simulate else 'real'}"

        try:
            before_state = self._get_system_state()

            if simulate:
                self._simulate_swap_pressure(target_percent=95)
                time.sleep(0.5)

            issue = self._detect_swap_issue()
            issue_detected = issue is not None

            remediation_attempted = False
            remediation_success = False

            if issue_detected:
                remediation_attempted = True
                remediation_success = self._remediate_swap_issue(issue)

            after_state = self._get_system_state()

            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)

            if simulate:
                status = "pass" if (issue_detected and remediation_success) else "fail"
            else:
                if not issue_detected:
                    status = "pass"
                elif issue['severity'] == 'warning' and remediation_success:
                    status = "pass"
                elif issue['severity'] == 'critical' and remediation_success:
                    status = "pass"
                else:
                    status = "fail"

            duration_ms = (time.time() - start) * 1000

            result = SystemHealthTestResult(
                test_id=test_id, status=status, issue_detected=issue_detected,
                issue_type=issue['type'] if issue else 'none',
                severity=issue['severity'] if issue else 'none',
                remediation_attempted=remediation_attempted,
                remediation_success=remediation_success,
                before_state=before_state, after_state=after_state,
                latency_ms=duration_ms, cpu_percent=cpu_percent,
                memory_mb=memory_mb, epoch_id=epoch_id
            )

            self.results.append(result)
            self.record_telemetry("test_complete", {"test_id": test_id, "status": status})

            write_test_result(test_id=test_id, status=status, latency_ms=duration_ms,
                            cpu_pct=cpu_percent, mem_mb=memory_mb, epoch_id=epoch_id)

            return result

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)

            result = SystemHealthTestResult(
                test_id=test_id, status="fail", issue_detected=False,
                issue_type="exception", severity="critical",
                remediation_attempted=False, remediation_success=False,
                before_state={}, after_state={}, latency_ms=duration_ms,
                cpu_percent=cpu_percent, memory_mb=memory_mb, epoch_id=epoch_id
            )

            self.results.append(result)
            self.record_telemetry("test_failed", {"test_id": test_id, "error": str(e)})

            write_test_result(test_id=test_id, status="fail", latency_ms=duration_ms,
                            cpu_pct=cpu_percent, mem_mb=memory_mb, epoch_id=epoch_id)

            raise RuntimeError(f"System health test failed: {e}") from e

    def run_all_tests(self, epoch_id: str) -> List[SystemHealthTestResult]:
        """Run all system health tests."""
        for simulate in [True, False]:
            try:
                self.run_swap_exhaustion_test(epoch_id, simulate)
            except RuntimeError:
                continue
        return self.results

    def get_summary(self) -> Dict:
        """Get summary statistics for all tests."""
        if not self.results:
            return {'total_tests': 0, 'pass_rate': 0.0, 'issues_detected': 0, 'remediations_successful': 0}

        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == 'pass')
        issues = sum(1 for r in self.results if r.issue_detected)
        remediated = sum(1 for r in self.results if r.remediation_success)

        return {
            'total_tests': total,
            'pass_rate': passed / total,
            'issues_detected': issues,
            'remediations_successful': remediated,
            'remediation_success_rate': remediated / issues if issues > 0 else 0.0
        }
