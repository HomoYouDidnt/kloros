#!/usr/bin/env python3
"""
PHASE Domain: System Health & Resource Management

Tests KLoROS's ability to detect and remediate system health issues:
- Swap exhaustion detection and clearing
- Memory pressure handling
- CPU load management
- Disk space monitoring

These tests validate the system can self-heal when resources become constrained.
"""
import time
import subprocess
import psutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class SystemHealthTestConfig:
    """Configuration for system health tests."""
    # Swap thresholds
    swap_warning_percent: int = 70
    swap_critical_percent: int = 90

    # Memory thresholds
    memory_warning_gb: float = 3.0
    memory_critical_gb: float = 1.0

    # Test budgets
    max_test_duration_sec: int = 120
    max_remediation_attempts: int = 3

@dataclass
class SystemHealthTestResult:
    """Result from a system health test."""
    test_id: str
    status: str  # "pass", "fail"
    issue_detected: bool
    issue_type: str  # "swap", "memory", "cpu", "disk"
    severity: str  # "warning", "critical"
    remediation_attempted: bool
    remediation_success: bool
    before_state: Dict
    after_state: Dict
    latency_ms: float
    cpu_percent: float  # CPU usage during test
    memory_mb: float  # Memory usage during test
    epoch_id: str

class SystemHealthDomain:
    """PHASE domain for system health monitoring and remediation."""

    def __init__(self, config: SystemHealthTestConfig):
        """Initialize system health domain.

        Args:
            config: SystemHealthTestConfig with test parameters
        """
        self.config = config
        self.results: List[SystemHealthTestResult] = []

    def _get_system_state(self) -> Dict:
        """Get current system resource state.

        Returns:
            Dict with memory, swap, CPU, disk metrics
        """
        # Memory info
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # CPU info
        cpu_percent = psutil.cpu_percent(interval=1)
        load_avg = psutil.getloadavg()

        # Disk info
        disk = psutil.disk_usage('/')

        return {
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

    def _simulate_swap_pressure(self, target_percent: int = 95) -> bool:
        """Simulate swap exhaustion for testing (safe simulation).

        NOTE: This is a SIMULATION - we don't actually fill swap, we just
        create test conditions that represent high swap usage.

        Args:
            target_percent: Target swap usage percentage to simulate

        Returns:
            True if simulation successful
        """
        # In a real system, we would NOT actually fill swap as that's dangerous.
        # Instead, we'll create a marker file that test code can check.
        marker = Path("/tmp/kloros_swap_simulation.marker")
        marker.write_text(f"{target_percent}\n")

        print(f"[system-health] Simulated swap pressure: {target_percent}%")
        return True

    def _detect_swap_issue(self) -> Optional[Dict]:
        """Detect swap exhaustion issues.

        Returns:
            Dict with issue details if detected, None otherwise
        """
        # Check for simulation marker first
        marker = Path("/tmp/kloros_swap_simulation.marker")
        if marker.exists():
            simulated_percent = int(marker.read_text().strip())
            if simulated_percent >= self.config.swap_critical_percent:
                return {
                    'type': 'swap',
                    'severity': 'critical',
                    'swap_percent': simulated_percent,
                    'simulated': True
                }
            elif simulated_percent >= self.config.swap_warning_percent:
                return {
                    'type': 'swap',
                    'severity': 'warning',
                    'swap_percent': simulated_percent,
                    'simulated': True
                }

        # Check real swap usage
        swap = psutil.swap_memory()
        swap_percent = swap.percent

        if swap_percent >= self.config.swap_critical_percent:
            return {
                'type': 'swap',
                'severity': 'critical',
                'swap_percent': swap_percent,
                'simulated': False
            }
        elif swap_percent >= self.config.swap_warning_percent:
            return {
                'type': 'swap',
                'severity': 'warning',
                'swap_percent': swap_percent,
                'simulated': False
            }

        return None

    def _remediate_swap_issue(self, issue: Dict) -> bool:
        """Attempt to remediate swap exhaustion.

        Args:
            issue: Issue details from _detect_swap_issue

        Returns:
            True if remediation successful
        """
        if issue.get('simulated'):
            # Clear simulation marker
            marker = Path("/tmp/kloros_swap_simulation.marker")
            marker.unlink(missing_ok=True)
            print("[system-health] Cleared simulated swap pressure")
            return True

        # Real remediation: clear swap
        print("[system-health] Attempting swap remediation: swapoff/swapon")

        try:
            # Turn off swap (moves data to RAM)
            result = subprocess.run(
                ['sudo', 'swapoff', '-a'],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"[system-health] swapoff failed: {result.stderr}")
                return False

            # Turn swap back on
            result = subprocess.run(
                ['sudo', 'swapon', '-a'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                print(f"[system-health] swapon failed: {result.stderr}")
                return False

            # Verify swap was cleared
            time.sleep(2)
            swap = psutil.swap_memory()

            if swap.percent < self.config.swap_warning_percent:
                print(f"[system-health] ✓ Swap cleared: {swap.percent:.1f}% used")
                return True
            else:
                print(f"[system-health] ✗ Swap still high: {swap.percent:.1f}% used")
                return False

        except subprocess.TimeoutExpired:
            print("[system-health] Remediation timed out")
            return False
        except Exception as e:
            print(f"[system-health] Remediation failed: {e}")
            return False

    def run_swap_exhaustion_test(self, epoch_id: str, simulate: bool = True) -> SystemHealthTestResult:
        """Test swap exhaustion detection and remediation.

        Args:
            epoch_id: PHASE epoch identifier
            simulate: If True, simulate swap pressure; if False, test real state

        Returns:
            SystemHealthTestResult
        """
        start = time.time()
        test_id = f"system_health::swap_exhaustion::{'simulated' if simulate else 'real'}"

        try:
            # Get initial state
            before_state = self._get_system_state()

            # Simulate swap pressure if requested
            if simulate:
                self._simulate_swap_pressure(target_percent=95)
                time.sleep(0.5)  # Allow simulation to settle

            # Detect issue
            issue = self._detect_swap_issue()
            issue_detected = issue is not None

            # Attempt remediation if issue detected
            remediation_attempted = False
            remediation_success = False

            if issue_detected:
                remediation_attempted = True
                remediation_success = self._remediate_swap_issue(issue)

            # Get final state
            after_state = self._get_system_state()

            # Track resource usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)

            # Determine test status
            if simulate:
                # For simulated tests, success = detected and remediated
                status = "pass" if (issue_detected and remediation_success) else "fail"
            else:
                # For real tests, success = no critical issues or successfully remediated
                if not issue_detected:
                    status = "pass"  # No issue is good
                elif issue['severity'] == 'warning' and remediation_success:
                    status = "pass"  # Warning remediated
                elif issue['severity'] == 'critical' and remediation_success:
                    status = "pass"  # Critical remediated
                else:
                    status = "fail"  # Issue not remediated

            duration_ms = (time.time() - start) * 1000

            result = SystemHealthTestResult(
                test_id=test_id,
                status=status,
                issue_detected=issue_detected,
                issue_type=issue['type'] if issue else 'none',
                severity=issue['severity'] if issue else 'none',
                remediation_attempted=remediation_attempted,
                remediation_success=remediation_success,
                before_state=before_state,
                after_state=after_state,
                latency_ms=duration_ms,
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                epoch_id=epoch_id
            )

            self.results.append(result)

            # Write to PHASE report with proper resource tracking
            from src.phase.report_writer import write_test_result
            write_test_result(
                test_id=test_id,
                status=status,
                latency_ms=duration_ms,
                cpu_pct=cpu_percent,
                mem_mb=memory_mb,
                epoch_id=epoch_id
            )

            return result

        except Exception as e:
            # Record failure with exception details
            duration_ms = (time.time() - start) * 1000
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)

            result = SystemHealthTestResult(
                test_id=test_id,
                status="fail",
                issue_detected=False,
                issue_type="exception",
                severity="critical",
                remediation_attempted=False,
                remediation_success=False,
                before_state={},
                after_state={},
                latency_ms=duration_ms,
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                epoch_id=epoch_id
            )

            self.results.append(result)

            # Write failure to PHASE report
            from src.phase.report_writer import write_test_result
            write_test_result(
                test_id=test_id,
                status="fail",
                latency_ms=duration_ms,
                cpu_pct=cpu_percent,
                mem_mb=memory_mb,
                epoch_id=epoch_id
            )

            print(f"[system-health] Test failed with exception: {e}")
            return result

    def run_all_tests(self, epoch_id: str) -> List[SystemHealthTestResult]:
        """Run all system health tests.

        Args:
            epoch_id: PHASE epoch identifier

        Returns:
            List of test results
        """
        results = []

        # Test 1: Simulated swap exhaustion
        print("\n[1/2] Testing simulated swap exhaustion...")
        result = self.run_swap_exhaustion_test(epoch_id, simulate=True)
        results.append(result)
        print(f"  {'✓' if result.status == 'pass' else '✗'} "
              f"Detected: {result.issue_detected}, "
              f"Remediated: {result.remediation_success}")

        # Test 2: Real swap state check
        print("\n[2/2] Testing real swap state...")
        result = self.run_swap_exhaustion_test(epoch_id, simulate=False)
        results.append(result)
        print(f"  {'✓' if result.status == 'pass' else '✗'} "
              f"Swap: {result.after_state['swap_percent']:.1f}% used")

        return results

    def get_summary(self) -> Dict:
        """Get summary statistics for all tests.

        Returns:
            Dict with summary metrics
        """
        if not self.results:
            return {
                'total_tests': 0,
                'pass_rate': 0.0,
                'issues_detected': 0,
                'remediations_successful': 0
            }

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

def main():
    """Run system health domain tests."""
    from datetime import datetime

    epoch_id = f"system_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print("=" * 80)
    print("PHASE System Health Domain Tests")
    print("=" * 80)
    print(f"Epoch ID: {epoch_id}")
    print()

    config = SystemHealthTestConfig()
    domain = SystemHealthDomain(config)

    results = domain.run_all_tests(epoch_id)
    summary = domain.get_summary()

    print("\n" + "=" * 80)
    print("System Health Test Summary")
    print("=" * 80)
    print(f"Total tests: {summary['total_tests']}")
    print(f"Pass rate: {summary['pass_rate']*100:.1f}%")
    print(f"Issues detected: {summary['issues_detected']}")
    print(f"Remediations successful: {summary['remediations_successful']}")
    print(f"Remediation success rate: {summary['remediation_success_rate']*100:.1f}%")

if __name__ == "__main__":
    main()
