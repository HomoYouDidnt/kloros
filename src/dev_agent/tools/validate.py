"""
Code validation: tests, linters, type checking.

Fast validation pipeline:
1. ruff check (syntax, style)
2. mypy (type checking)
3. pytest (unit tests with smart filtering)
"""
import subprocess
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class ValidationResult:
    """Results from a validation run."""
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    passed: bool
    duration_ms: float

    @property
    def output(self) -> str:
        """Combined output."""
        return self.stdout + self.stderr

def run_validation(
    repo_root: Path,
    fast_filter: str = "not slow and not e2e",
    max_output: int = 4000,
    timeout_sec: int = 300
) -> List[ValidationResult]:
    """
    Run fast validation pipeline.

    Args:
        repo_root: Repository root directory
        fast_filter: Pytest marker expression for fast tests
        max_output: Maximum output chars to keep
        timeout_sec: Timeout per command

    Returns:
        List of ValidationResult objects
    """
    repo_root = Path(repo_root).resolve()

    commands = [
        ["ruff", "check", "--quiet", "."],
        ["mypy", "--hide-error-context", "--no-error-summary", "src"],
        ["pytest", "-q", "-k", fast_filter, "--maxfail=3", "--tb=short"]
    ]

    results = []

    for cmd in commands:
        import time
        start = time.perf_counter()

        try:
            proc = subprocess.run(
                cmd,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )

            duration = (time.perf_counter() - start) * 1000

            result = ValidationResult(
                command=cmd,
                returncode=proc.returncode,
                stdout=proc.stdout[-max_output:] if proc.stdout else "",
                stderr=proc.stderr[-max_output:] if proc.stderr else "",
                passed=(proc.returncode == 0),
                duration_ms=duration
            )

            results.append(result)

            # Stop on first failure for pytest
            if cmd[0] == "pytest" and not result.passed:
                break

        except subprocess.TimeoutExpired:
            duration = (time.perf_counter() - start) * 1000
            results.append(ValidationResult(
                command=cmd,
                returncode=-1,
                stdout="",
                stderr=f"TIMEOUT after {timeout_sec}s",
                passed=False,
                duration_ms=duration
            ))
            break

        except FileNotFoundError:
            # Tool not installed, skip
            results.append(ValidationResult(
                command=cmd,
                returncode=-2,
                stdout="",
                stderr=f"Tool not found: {cmd[0]}",
                passed=True,  # Don't fail if tool missing
                duration_ms=0
            ))

    return results

def run_tests_only(
    repo_root: Path,
    test_filter: Optional[str] = None,
    last_failed: bool = False,
    timeout_sec: int = 600
) -> ValidationResult:
    """
    Run pytest with specific filters.

    Args:
        repo_root: Repository root
        test_filter: Pytest -k filter expression
        last_failed: Run only last failed tests
        timeout_sec: Timeout in seconds

    Returns:
        ValidationResult
    """
    repo_root = Path(repo_root).resolve()

    cmd = ["pytest", "-q", "--tb=short"]

    if last_failed:
        cmd.append("--lf")

    if test_filter:
        cmd.extend(["-k", test_filter])

    import time
    start = time.perf_counter()

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )

        duration = (time.perf_counter() - start) * 1000

        return ValidationResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout[-4000:],
            stderr=proc.stderr[-4000:],
            passed=(proc.returncode == 0),
            duration_ms=duration
        )

    except subprocess.TimeoutExpired:
        duration = (time.perf_counter() - start) * 1000
        return ValidationResult(
            command=cmd,
            returncode=-1,
            stdout="",
            stderr=f"TIMEOUT after {timeout_sec}s",
            passed=False,
            duration_ms=duration
        )

def run_ruff_fix(repo_root: Path, files: Optional[List[str]] = None) -> ValidationResult:
    """
    Run ruff --fix to auto-fix issues.

    Args:
        repo_root: Repository root
        files: Optional list of specific files to fix

    Returns:
        ValidationResult
    """
    repo_root = Path(repo_root).resolve()

    cmd = ["ruff", "check", "--fix", "--quiet"]

    if files:
        cmd.extend(files)
    else:
        cmd.append(".")

    import time
    start = time.perf_counter()

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60
        )

        duration = (time.perf_counter() - start) * 1000

        return ValidationResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout[-2000:],
            stderr=proc.stderr[-2000:],
            passed=(proc.returncode == 0),
            duration_ms=duration
        )

    except subprocess.TimeoutExpired:
        duration = (time.perf_counter() - start) * 1000
        return ValidationResult(
            command=cmd,
            returncode=-1,
            stdout="",
            stderr="TIMEOUT after 60s",
            passed=False,
            duration_ms=duration
        )

def extract_test_failures(pytest_output: str) -> List[Dict[str, str]]:
    """
    Parse pytest output to extract failing tests.

    Returns:
        List of dicts with keys: test_name, file, reason
    """
    failures = []
    lines = pytest_output.splitlines()

    for i, line in enumerate(lines):
        if "FAILED" in line:
            parts = line.split()
            if len(parts) >= 2:
                test_path = parts[0]  # e.g., "tests/test_foo.py::test_bar"

                # Extract file and test name
                if "::" in test_path:
                    file_part, test_name = test_path.split("::", 1)
                else:
                    file_part = test_path
                    test_name = "unknown"

                # Try to find the failure reason in next few lines
                reason = ""
                for j in range(i+1, min(i+10, len(lines))):
                    if "AssertionError" in lines[j] or "Error" in lines[j]:
                        reason = lines[j].strip()
                        break

                failures.append({
                    "test_name": test_name,
                    "file": file_part,
                    "reason": reason or "Unknown failure"
                })

    return failures

def check_security(repo_root: Path) -> ValidationResult:
    """
    Run bandit security checks.

    Args:
        repo_root: Repository root

    Returns:
        ValidationResult
    """
    repo_root = Path(repo_root).resolve()

    cmd = ["bandit", "-r", "src", "-f", "json", "-q"]

    import time
    start = time.perf_counter()

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120
        )

        duration = (time.perf_counter() - start) * 1000

        # Parse bandit JSON output
        import json
        try:
            data = json.loads(proc.stdout)
            issues = len(data.get("results", []))
            passed = (issues == 0)
        except (json.JSONDecodeError, KeyError, TypeError):
            # Failed to parse bandit JSON, fall back to return code
            passed = (proc.returncode == 0)

        return ValidationResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout[-2000:],
            stderr=proc.stderr[-2000:],
            passed=passed,
            duration_ms=duration
        )

    except subprocess.TimeoutExpired:
        duration = (time.perf_counter() - start) * 1000
        return ValidationResult(
            command=cmd,
            returncode=-1,
            stdout="",
            stderr="TIMEOUT after 120s",
            passed=False,
            duration_ms=duration
        )

    except FileNotFoundError:
        # Bandit not installed
        return ValidationResult(
            command=cmd,
            returncode=-2,
            stdout="",
            stderr="bandit not found",
            passed=True,  # Don't fail if not installed
            duration_ms=0
        )
