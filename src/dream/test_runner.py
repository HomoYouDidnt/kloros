"""
Direct Test Runner for D-REAM tournaments.

Runs pytest directly on SPICA instances without PHASE overhead.
Much faster than HTC approach - suitable for bracket tournament evaluation.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import subprocess
import re
import time
import logging

logger = logging.getLogger(__name__)


class DirectTestRunner:
    """
    Run SPICA tests directly without PHASE overhead.

    Executes pytest suite for a single instance and returns fitness.
    Much faster than PHASE's HTC approach (~2.5s vs 20 minutes for batch).
    """

    def __init__(self, timeout: int = 30):
        """
        Args:
            timeout: Maximum seconds to wait for tests to complete
        """
        self.timeout = timeout

    def run_test(self, instance_path: Path | str, verbose: bool = False) -> Dict[str, Any]:
        """
        Run tests for a single SPICA instance.

        Args:
            instance_path: Path to SPICA instance (e.g., "/home/kloros/experiments/spica/instances/spica-abc123")
            verbose: If True, include full pytest output in result

        Returns:
            {
                "passed": 64,
                "failed": 0,
                "skipped": 3,
                "total": 67,
                "duration_ms": 2500,
                "pass_rate": 0.95,
                "fitness": 0.95,
                "exit_code": 0,
                "output": "..." (if verbose=True)
            }
        """
        instance_path = Path(instance_path)
        test_dir = instance_path / "tests"

        if not test_dir.exists():
            logger.error(f"Test directory not found: {test_dir}")
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "duration_ms": 0,
                "pass_rate": 0.0,
                "fitness": 0.0,
                "exit_code": -1,
                "error": f"Test directory not found: {test_dir}"
            }

        start = time.time()

        template_venv_python = Path("/home/kloros/experiments/spica/template/.venv/bin/python")

        if not template_venv_python.exists():
            logger.error(f"Template venv not found: {template_venv_python}")
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "duration_ms": 0,
                "pass_rate": 0.0,
                "fitness": 0.0,
                "exit_code": -1,
                "error": f"Template venv missing: {template_venv_python}"
            }

        try:
            result = subprocess.run(
                [
                    str(template_venv_python),
                    "-m",
                    "pytest",
                    str(test_dir),
                    "-v",
                    "--tb=short",
                    "-q",
                    "-o", "addopts="
                ],
                capture_output=True,
                timeout=self.timeout,
                cwd=instance_path,
                text=True
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start) * 1000
            logger.error(f"Tests timed out after {self.timeout}s for {instance_path.name}")
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "duration_ms": duration_ms,
                "pass_rate": 0.0,
                "fitness": 0.0,
                "exit_code": -1,
                "error": f"Timeout after {self.timeout}s"
            }

        duration_ms = (time.time() - start) * 1000

        passed, failed, skipped = self._parse_pytest_output(result.stdout)
        total = passed + failed
        pass_rate = passed / max(1, total)

        result_dict = {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total": total,
            "duration_ms": duration_ms,
            "pass_rate": pass_rate,
            "fitness": pass_rate,
            "exit_code": result.returncode
        }

        if verbose:
            result_dict["output"] = result.stdout

        logger.info(
            f"[TEST] {instance_path.name}: {passed}/{total} passed "
            f"({pass_rate:.1%}) in {duration_ms:.0f}ms"
        )

        return result_dict

    def _parse_pytest_output(self, output: str) -> tuple[int, int, int]:
        """
        Parse pytest output to extract pass/fail/skip counts.

        Looks for patterns like:
        - "64 passed, 3 skipped in 2.34s"
        - "60 passed, 4 failed in 3.12s"
        - "= 64 passed, 3 skipped in 2.34s ="

        Args:
            output: pytest stdout

        Returns:
            (passed, failed, skipped) counts
        """
        passed = 0
        failed = 0
        skipped = 0

        passed_match = re.search(r'(\d+)\s+passed', output)
        if passed_match:
            passed = int(passed_match.group(1))

        failed_match = re.search(r'(\d+)\s+failed', output)
        if failed_match:
            failed = int(failed_match.group(1))

        skipped_match = re.search(r'(\d+)\s+skipped', output)
        if skipped_match:
            skipped = int(skipped_match.group(1))

        return passed, failed, skipped
