"""
Test Result Monitor - pytest execution result tracking.

Monitors pytest test execution results and detects failures.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from .base_types import (
    CuriosityQuestion,
    QuestionStatus,
    ActionClass,
)

logger = logging.getLogger(__name__)


class TestResultMonitor:
    """
    Monitors pytest test execution results and detects failures.

    Purpose:
        Enable KLoROS to detect test failures from scheduled test runs
        and generate questions about fixing those failures

    Outcomes:
        - Scans pytest JSON reports
        - Detects collection errors, test failures, and environment issues
        - Generates test-failure-based curiosity questions
    """

    def __init__(
        self,
        pytest_json_path: Path = Path("/home/kloros/logs/pytest_latest.json"),
        test_log_path: Path = Path("/home/kloros/logs/spica-phase-test.log")
    ):
        """Initialize test result monitor."""
        self.pytest_json_path = pytest_json_path
        self.test_log_path = test_log_path

    def scan_test_results(self) -> Dict[str, Any]:
        """Scan most recent pytest results."""
        result = {
            "has_results": False,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "collection_errors": [],
            "test_failures": [],
            "last_run": None
        }

        if not self.pytest_json_path.exists():
            logger.debug(f"[test_monitor] No pytest JSON report found at {self.pytest_json_path}")
            return result

        try:
            with open(self.pytest_json_path, 'r') as f:
                data = json.load(f)

            result["has_results"] = True
            result["last_run"] = data.get("created", None)

            summary = data.get("summary", {})
            result["total"] = summary.get("total", 0)
            result["passed"] = summary.get("passed", 0)
            result["failed"] = summary.get("failed", 0)
            result["errors"] = summary.get("error", 0)
            result["skipped"] = summary.get("skipped", 0)

            collectors = data.get("collectors", [])
            for collector in collectors:
                if collector.get("outcome") == "failed":
                    longrepr = collector.get("longrepr", "")
                    result["collection_errors"].append({
                        "nodeid": collector.get("nodeid", "unknown"),
                        "error": longrepr
                    })

            tests = data.get("tests", [])
            for test in tests:
                if test.get("outcome") in ["failed", "error"]:
                    result["test_failures"].append({
                        "nodeid": test.get("nodeid", "unknown"),
                        "outcome": test.get("outcome"),
                        "call": test.get("call", {})
                    })

        except Exception as e:
            logger.error(f"[test_monitor] Failed to parse pytest JSON: {e}")

        return result

    def generate_test_questions(self) -> List[CuriosityQuestion]:
        """Generate curiosity questions from test failures."""
        questions = []
        results = self.scan_test_results()

        if not results["has_results"]:
            return questions

        if results["collection_errors"]:
            for error_info in results["collection_errors"][:3]:
                nodeid = error_info["nodeid"]
                error = error_info["error"]

                error_type = "collection_error"
                if "ValueError" in error:
                    error_type = "value_error"
                elif "ModuleNotFoundError" in error or "ImportError" in error:
                    error_type = "import_error"
                elif "NameError" in error:
                    error_type = "name_error"

                error_summary = error.split('\n')[-1] if '\n' in error else error[:200]

                q = CuriosityQuestion(
                    id=f"test.{error_type}.{hashlib.md5(nodeid.encode()).hexdigest()[:8]}",
                    hypothesis=f"TEST_COLLECTION_ERROR_{error_type.upper()}",
                    question=f"Why is test collection failing in {nodeid}? Error: {error_summary}",
                    evidence=[
                        f"test:{nodeid}",
                        f"error_type:{error_type}",
                        f"error:{error_summary}"
                    ],
                    action_class=ActionClass.PROPOSE_FIX,
                    autonomy=3,
                    value_estimate=0.8,
                    cost=0.3,
                    capability_key=f"test.{nodeid}"
                )
                questions.append(q)

        if results["failed"] > 0:
            if results["failed"] <= 3:
                for failure in results["test_failures"][:3]:
                    nodeid = failure["nodeid"]
                    call_info = failure.get("call", {})
                    crash_info = call_info.get("crash", {})

                    q = CuriosityQuestion(
                        id=f"test.failure.{hashlib.md5(nodeid.encode()).hexdigest()[:8]}",
                        hypothesis="TEST_FAILURE",
                        question=f"Why is test {nodeid} failing?",
                        evidence=[
                            f"test:{nodeid}",
                            f"outcome:{failure['outcome']}",
                            f"crash:{crash_info.get('message', 'unknown')}"
                        ],
                        action_class=ActionClass.INVESTIGATE,
                        autonomy=3,
                        value_estimate=0.7,
                        cost=0.4,
                        capability_key=f"test.{nodeid}"
                    )
                    questions.append(q)
            else:
                q = CuriosityQuestion(
                    id="test.multiple_failures",
                    hypothesis="MULTIPLE_TEST_FAILURES",
                    question=f"Why are {results['failed']} tests failing? This may indicate a systemic issue.",
                    evidence=[
                        f"failed_count:{results['failed']}",
                        f"total_count:{results['total']}",
                        f"pass_rate:{results['passed']/results['total'] if results['total'] > 0 else 0:.2%}"
                    ],
                    action_class=ActionClass.INVESTIGATE,
                    autonomy=3,
                    value_estimate=0.9,
                    cost=0.5,
                    capability_key="test.suite"
                )
                questions.append(q)

        return questions
