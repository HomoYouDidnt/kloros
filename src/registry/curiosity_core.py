#!/usr/bin/env python3
"""
Curiosity Core - Automatic Question Generator from Capability Gaps

Analyzes capability matrix and generates questions to guide self-directed learning.

Governance:
- Tool-Integrity: Self-contained, testable, complete docstrings
- D-REAM-Allowed-Stack: Uses JSON, no unbounded loops
- Autonomy Level 2: Proposes questions, user decides actions

Purpose:
    Transform capability gaps into concrete, actionable questions that drive curiosity

Outcomes:
    - Generates questions from missing/degraded capabilities
    - Estimates value, cost, and autonomy level for each question
    - Provides hypotheses and evidence for each question
    - Enables "what's the minimal substitute?" type reasoning
"""

import json
import logging
import hashlib
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from collections import defaultdict

# Import semantic evidence store
try:
    from .semantic_evidence import SemanticEvidenceStore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from semantic_evidence import SemanticEvidenceStore

try:
    from .question_prioritizer import QuestionPrioritizer
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from question_prioritizer import QuestionPrioritizer

try:
    from src.kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub
except ImportError:
    try:
        from kloros.orchestration.chem_bus_v2 import ChemPub, ChemSub
    except ImportError:
        ChemPub = None
        ChemSub = None

import psutil
import subprocess

try:
    from .capability_evaluator import CapabilityMatrix, CapabilityState, CapabilityRecord
except ImportError:
    # Standalone execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from capability_evaluator import CapabilityMatrix, CapabilityState, CapabilityRecord

logger = logging.getLogger(__name__)

MAX_FOLLOWUP_QUESTIONS_PER_CYCLE = 10


class QuestionStatus(Enum):
    """Status of a curiosity question."""
    READY = "ready"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    BLOCKED = "blocked"


class ActionClass(Enum):
    """Type of action suggested by question."""
    EXPLAIN_AND_SOFT_FALLBACK = "explain_and_soft_fallback"
    INVESTIGATE = "investigate"
    PROPOSE_FIX = "propose_fix"
    REQUEST_USER_ACTION = "request_user_action"
    FIND_SUBSTITUTE = "find_substitute"
    EXPERIMENT = "experiment"  # Run controlled experiments to test hypotheses
    EXPLORE = "explore"  # Open-ended exploration of new possibilities


@dataclass
class CuriosityQuestion:
    """A single curiosity question generated from capability analysis."""
    id: str
    hypothesis: str
    question: str
    evidence: List[str] = field(default_factory=list)
    evidence_hash: Optional[str] = None
    action_class: ActionClass = ActionClass.EXPLAIN_AND_SOFT_FALLBACK
    autonomy: int = 3  # Autonomy level (1=notify, 2=propose, 3=execute)
    value_estimate: float = 0.5  # Expected value (0.0-1.0)
    cost: float = 0.2  # Expected cost/risk (0.0-1.0)
    status: QuestionStatus = QuestionStatus.READY
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    capability_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "hypothesis": self.hypothesis,
            "question": self.question,
            "evidence": self.evidence,
            "evidence_hash": self.evidence_hash,
            "action_class": self.action_class.value,
            "autonomy": self.autonomy,
            "value_estimate": self.value_estimate,
            "cost": self.cost,
            "status": self.status.value,
            "created_at": self.created_at,
            "capability_key": self.capability_key,
            "metadata": self.metadata
        }


@dataclass
class CuriosityFeed:
    """Collection of curiosity questions."""
    questions: List[CuriosityQuestion] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "questions": [q.to_dict() for q in self.questions],
            "generated_at": self.generated_at,
            "count": len(self.questions)
        }


@dataclass
class PerformanceTrend:
    """Performance trend data for a D-REAM experiment."""
    experiment: str
    recent_summaries: List[Dict[str, Any]] = field(default_factory=list)
    pass_rate_trend: List[float] = field(default_factory=list)
    latency_trend: List[float] = field(default_factory=list)
    accuracy_trend: List[float] = field(default_factory=list)

    def detect_degradation(self) -> Optional[str]:
        """
        Detect performance degradation patterns.

        Returns:
            String describing degradation, or None if performance is stable/improving
        """
        if len(self.pass_rate_trend) < 2:
            return None

        # Check pass rate degradation
        if len(self.pass_rate_trend) >= 3:
            recent_avg = sum(self.pass_rate_trend[-3:]) / 3
            if recent_avg < 0.7 and self.pass_rate_trend[0] > 0.85:
                drop_pct = (self.pass_rate_trend[0] - recent_avg) * 100
                return f"pass_rate_drop:{drop_pct:.1f}%"

        # Check latency increase
        if len(self.latency_trend) >= 3:
            recent_avg = sum(self.latency_trend[-3:]) / 3
            baseline_avg = sum(self.latency_trend[:3]) / len(self.latency_trend[:3])
            if recent_avg > baseline_avg * 1.5:  # 50% slower
                increase_pct = ((recent_avg - baseline_avg) / baseline_avg) * 100
                return f"latency_increase:{increase_pct:.1f}%"

        # Check accuracy degradation
        if len(self.accuracy_trend) >= 3:
            recent_avg = sum(self.accuracy_trend[-3:]) / 3
            if recent_avg < 0.8 and self.accuracy_trend[0] > 0.95:
                drop_pct = (self.accuracy_trend[0] - recent_avg) * 100
                return f"accuracy_drop:{drop_pct:.1f}%"

        return None


class PerformanceMonitor:
    """
    Monitors D-REAM experiment performance from summary.json files.

    Purpose:
        Enable KLoROS to detect performance degradation trends and generate
        questions about optimization opportunities

    Outcomes:
        - Scans recent D-REAM summaries
        - Detects pass rate drops, latency increases, accuracy degradation
        - Generates performance-based curiosity questions
    """

    def __init__(self, artifacts_dir: Path = Path("/home/kloros/artifacts/dream")):
        """
        Initialize performance monitor.

        Parameters:
            artifacts_dir: Root directory containing D-REAM artifacts
        """
        self.artifacts_dir = artifacts_dir

    def scan_experiment_summaries(
        self,
        experiment: str,
        max_summaries: int = 10
    ) -> PerformanceTrend:
        """
        Scan recent summaries for a specific experiment.

        Parameters:
            experiment: Experiment name (e.g., "spica_cognitive_variants")
            max_summaries: Maximum number of recent summaries to load

        Returns:
            PerformanceTrend with loaded data
        """
        trend = PerformanceTrend(experiment=experiment)

        # Find experiment directory
        exp_dir = self.artifacts_dir / experiment
        if not exp_dir.exists():
            logger.warning(f"[performance_monitor] Experiment directory not found: {exp_dir}")
            return trend

        # Find all summary.json files, sorted by timestamp (directory name)
        summary_files = []
        for ts_dir in exp_dir.iterdir():
            if ts_dir.is_dir():
                summary_path = ts_dir / "summary.json"
                if summary_path.exists():
                    try:
                        ts = int(ts_dir.name)
                        summary_files.append((ts, summary_path))
                    except ValueError:
                        continue

        # Sort by timestamp (most recent first) and take max_summaries
        summary_files.sort(reverse=True)
        summary_files = summary_files[:max_summaries]

        # Load summaries and extract trends
        for ts, summary_path in reversed(summary_files):  # Reverse to get chronological order
            try:
                with open(summary_path, 'r') as f:
                    summary = json.load(f)

                trend.recent_summaries.append(summary)

                # Extract pass rate (handle null best_metrics)
                best_metrics = summary.get("best_metrics")
                if best_metrics and isinstance(best_metrics, dict):
                    if "tournament" in best_metrics:
                        tournament = best_metrics["tournament"]
                        if isinstance(tournament, dict) and "results" in tournament:
                            results = tournament["results"]
                            total = results.get("total_replicas", 0)
                            passed = results.get("passed", 0)
                            if total > 0:
                                pass_rate = passed / total
                                trend.pass_rate_trend.append(pass_rate)

                    # Extract latency
                    latency = best_metrics.get("latency_p50_ms", 0)
                    if latency > 0:
                        trend.latency_trend.append(latency)

                    # Extract accuracy
                    accuracy = best_metrics.get("exact_match_mean", 0)
                    if accuracy > 0:
                        trend.accuracy_trend.append(accuracy)

            except Exception as e:
                logger.error(f"[performance_monitor] Failed to load {summary_path}: {e}")
                continue

        return trend

    def generate_performance_questions(
        self,
        experiments: Optional[List[str]] = None
    ) -> List[CuriosityQuestion]:
        """
        Generate curiosity questions from performance trends.

        Parameters:
            experiments: List of experiment names to monitor. If None, scans all experiments.

        Returns:
            List of CuriosityQuestion objects
        """
        questions = []

        # If no experiments specified, scan all experiment directories
        if experiments is None:
            experiments = []
            if self.artifacts_dir.exists():
                for exp_dir in self.artifacts_dir.iterdir():
                    if exp_dir.is_dir():
                        # Check if this experiment has any summary.json files
                        has_summaries = any(
                            (ts_dir / "summary.json").exists()
                            for ts_dir in exp_dir.iterdir()
                            if ts_dir.is_dir()
                        )
                        if has_summaries:
                            experiments.append(exp_dir.name)

        # Scan each experiment
        for experiment in experiments:
            trend = self.scan_experiment_summaries(experiment)

            if not trend.recent_summaries:
                continue

            # Detect degradation
            degradation = trend.detect_degradation()
            if degradation:
                q = self._question_for_performance_degradation(experiment, degradation, trend)
                if q:
                    questions.append(q)

        return questions

    def _question_for_performance_degradation(
        self,
        experiment: str,
        degradation: str,
        trend: PerformanceTrend
    ) -> Optional[CuriosityQuestion]:
        """
        Generate question for detected performance degradation.

        Parameters:
            experiment: Experiment name
            degradation: Degradation type and amount (e.g., "pass_rate_drop:15.2%")
            trend: PerformanceTrend with full data

        Returns:
            CuriosityQuestion or None
        """
        degradation_type, amount = degradation.split(":", 1)

        # Get most recent summary for params
        latest_summary = trend.recent_summaries[-1]
        best_params = latest_summary.get("best_params", {})

        if degradation_type == "pass_rate_drop":
            hypothesis = f"{experiment.upper()}_PASS_RATE_DEGRADATION"
            question = (
                f"Why did {experiment} pass rate drop by {amount}? "
                f"Current params: {best_params}. Should I spawn a remediation experiment?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.9  # High priority
            cost = 0.5  # Medium cost (requires spawning experiments)

        elif degradation_type == "latency_increase":
            hypothesis = f"{experiment.upper()}_LATENCY_REGRESSION"
            question = (
                f"Why did {experiment} latency increase by {amount}? "
                f"Can adjusting {list(best_params.keys())} improve performance?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.7
            cost = 0.4

        elif degradation_type == "accuracy_drop":
            hypothesis = f"{experiment.upper()}_ACCURACY_DEGRADATION"
            question = (
                f"Why did {experiment} accuracy drop by {amount}? "
                f"Is this a data quality issue or parameter drift?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.8
            cost = 0.3

        else:
            return None

        # Build evidence list
        evidence = [
            f"experiment:{experiment}",
            f"degradation:{degradation}",
            f"recent_runs:{len(trend.recent_summaries)}",
            f"params:{','.join(best_params.keys())}"
        ]

        if trend.pass_rate_trend:
            evidence.append(f"pass_rate_recent:{trend.pass_rate_trend[-1]:.2f}")
        if trend.latency_trend:
            evidence.append(f"latency_recent:{trend.latency_trend[-1]:.2f}ms")
        if trend.accuracy_trend:
            evidence.append(f"accuracy_recent:{trend.accuracy_trend[-1]:.2f}")

        return CuriosityQuestion(
            id=f"performance.{experiment}.{degradation_type}",
            hypothesis=hypothesis,
            question=question,
            evidence=evidence,
            action_class=action_class,
            autonomy=3,  # Execute autonomously
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=f"dream.{experiment}"
        )


@dataclass
class SystemResourceSnapshot:
    """Snapshot of system resource usage."""
    timestamp: datetime
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    swap_percent: float
    swap_used_gb: float
    cpu_percent: float
    load_avg_1min: float
    load_avg_5min: float
    disk_usage_percent: float
    gpu_utilization: Optional[float] = None
    gpu_memory_percent: Optional[float] = None


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
        """
        Initialize test result monitor.

        Parameters:
            pytest_json_path: Path to pytest JSON report
            test_log_path: Path to test log file for additional context
        """
        self.pytest_json_path = pytest_json_path
        self.test_log_path = test_log_path

    def scan_test_results(self) -> Dict[str, Any]:
        """
        Scan most recent pytest results.

        Returns:
            Dict with test summary data including failures and errors
        """
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

            # Extract summary
            summary = data.get("summary", {})
            result["total"] = summary.get("total", 0)
            result["passed"] = summary.get("passed", 0)
            result["failed"] = summary.get("failed", 0)
            result["errors"] = summary.get("error", 0)
            result["skipped"] = summary.get("skipped", 0)

            # Extract collection errors
            collectors = data.get("collectors", [])
            for collector in collectors:
                if collector.get("outcome") == "failed":
                    longrepr = collector.get("longrepr", "")
                    result["collection_errors"].append({
                        "nodeid": collector.get("nodeid", "unknown"),
                        "error": longrepr
                    })

            # Extract test failures
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
        """
        Generate curiosity questions from test failures.

        Returns:
            List of CuriosityQuestion objects
        """
        questions = []
        results = self.scan_test_results()

        if not results["has_results"]:
            return questions

        # Generate question for collection errors
        if results["collection_errors"]:
            for error_info in results["collection_errors"][:3]:  # Limit to first 3
                nodeid = error_info["nodeid"]
                error = error_info["error"]

                # Parse error type
                error_type = "collection_error"
                if "ValueError" in error:
                    error_type = "value_error"
                elif "ModuleNotFoundError" in error or "ImportError" in error:
                    error_type = "import_error"
                elif "NameError" in error:
                    error_type = "name_error"

                # Extract key info from error
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
                    value_estimate=0.8,  # High value - blocks tests
                    cost=0.3,
                    capability_key=f"test.{nodeid}"
                )
                questions.append(q)

        # Generate question for test failures (aggregate if many)
        if results["failed"] > 0:
            if results["failed"] <= 3:
                # Individual questions for small number of failures
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
                # Aggregate question for many failures
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
                    value_estimate=0.9,  # Very high - systemic issue
                    cost=0.5,
                    capability_key="test.suite"
                )
                questions.append(q)

        return questions


class SystemResourceMonitor:
    """
    Monitors system resource usage and detects anomalies.

    Purpose:
        Detect resource exhaustion, memory leaks, stuck processes before
        they impact D-REAM experiments or system stability

    Outcomes:
        - Monitors RAM, swap, CPU, GPU, disk usage
        - Detects sudden spikes or sustained high usage
        - Generates resource-based curiosity questions
    """

    def __init__(
        self,
        memory_threshold: float = 0.85,
        swap_threshold: float = 0.50,
        cpu_threshold: float = 0.90,
        disk_threshold: float = 0.90,
        gpu_threshold: float = 0.95,
        consciousness=None
    ):
        """
        Initialize system resource monitor.

        Parameters:
            memory_threshold: Alert when memory exceeds this % (default: 85%)
            swap_threshold: Alert when swap exceeds this % (default: 50%)
            cpu_threshold: Alert when CPU avg exceeds this % (default: 90%)
            disk_threshold: Alert when disk exceeds this % (default: 90%)
            gpu_threshold: Alert when GPU exceeds this % (default: 95%)
            consciousness: Optional IntegratedConsciousness instance for resource pressure events
        """
        self.memory_threshold = memory_threshold
        self.swap_threshold = swap_threshold
        self.cpu_threshold = cpu_threshold
        self.disk_threshold = disk_threshold
        self.gpu_threshold = gpu_threshold
        self.consciousness = consciousness

    def capture_snapshot(self) -> SystemResourceSnapshot:
        """
        Capture current system resource usage.

        Returns:
            SystemResourceSnapshot with current metrics
        """
        # Memory
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        load_avg = psutil.getloadavg()

        # Disk (home partition)
        disk = psutil.disk_usage("/home/kloros")

        # GPU (optional, nvidia-smi)
        gpu_util = None
        gpu_mem = None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory",
                 "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                gpu_util = float(parts[0])
                gpu_mem = float(parts[1])
        except Exception:
            pass

        return SystemResourceSnapshot(
            timestamp=datetime.now(),
            memory_percent=mem.percent / 100.0,
            memory_used_gb=mem.used / (1024**3),
            memory_total_gb=mem.total / (1024**3),
            swap_percent=swap.percent / 100.0,
            swap_used_gb=swap.used / (1024**3),
            cpu_percent=cpu_percent / 100.0,
            load_avg_1min=load_avg[0],
            load_avg_5min=load_avg[1],
            disk_usage_percent=disk.percent / 100.0,
            gpu_utilization=gpu_util / 100.0 if gpu_util is not None else None,
            gpu_memory_percent=gpu_mem / 100.0 if gpu_mem is not None else None
        )

    def detect_resource_issues(self, snapshot: SystemResourceSnapshot) -> List[str]:
        """
        Detect resource issues from snapshot.

        Parameters:
            snapshot: SystemResourceSnapshot to analyze

        Returns:
            List of issue descriptions
        """
        issues = []

        # Memory pressure
        if snapshot.memory_percent > self.memory_threshold:
            issues.append(f"memory_high:{snapshot.memory_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="memory",
                        level=snapshot.memory_percent,
                        evidence=[f"Memory usage: {snapshot.memory_used_gb:.1f}GB/{snapshot.memory_total_gb:.1f}GB ({snapshot.memory_percent*100:.1f}%)"]
                    )
                except Exception as e:
                    pass

        # Swap usage (sign of memory pressure)
        if snapshot.swap_percent > self.swap_threshold:
            issues.append(f"swap_high:{snapshot.swap_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="memory",
                        level=min(1.0, snapshot.swap_percent * 2),
                        evidence=[f"Swap usage: {snapshot.swap_used_gb:.1f}GB ({snapshot.swap_percent*100:.1f}%) - indicates memory pressure"]
                    )
                except Exception as e:
                    pass

        # CPU saturation
        if snapshot.cpu_percent > self.cpu_threshold:
            issues.append(f"cpu_saturated:{snapshot.cpu_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="cpu",
                        level=snapshot.cpu_percent,
                        evidence=[f"CPU usage: {snapshot.cpu_percent*100:.1f}%", f"Load average: {snapshot.load_avg_1min:.1f}"]
                    )
                except Exception as e:
                    pass

        # Load average high (more processes than cores)
        cpu_count = psutil.cpu_count()
        if snapshot.load_avg_5min > cpu_count * 1.5:
            issues.append(f"load_avg_high:{snapshot.load_avg_5min:.1f}")

        # Disk space low
        if snapshot.disk_usage_percent > self.disk_threshold:
            issues.append(f"disk_low:{snapshot.disk_usage_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="context",
                        level=snapshot.disk_usage_percent,
                        evidence=[f"Disk usage: {snapshot.disk_usage_percent*100:.1f}%"]
                    )
                except Exception as e:
                    pass

        # GPU saturation
        if snapshot.gpu_utilization and snapshot.gpu_utilization > self.gpu_threshold:
            issues.append(f"gpu_saturated:{snapshot.gpu_utilization*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="cpu",
                        level=snapshot.gpu_utilization,
                        evidence=[f"GPU utilization: {snapshot.gpu_utilization*100:.1f}%"]
                    )
                except Exception as e:
                    pass

        if snapshot.gpu_memory_percent and snapshot.gpu_memory_percent > self.gpu_threshold:
            issues.append(f"gpu_memory_high:{snapshot.gpu_memory_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="memory",
                        level=snapshot.gpu_memory_percent,
                        evidence=[f"GPU memory: {snapshot.gpu_memory_percent*100:.1f}%"]
                    )
                except Exception as e:
                    pass

        return issues

    def generate_resource_questions(self) -> List[CuriosityQuestion]:
        """
        Generate curiosity questions from current resource state.

        Returns:
            List of CuriosityQuestion objects
        """
        questions = []

        # Capture current snapshot
        snapshot = self.capture_snapshot()
        issues = self.detect_resource_issues(snapshot)

        for issue in issues:
            issue_type, amount = issue.split(":", 1)
            q = self._question_for_resource_issue(issue_type, amount, snapshot)
            if q:
                questions.append(q)

        return questions

    def _question_for_resource_issue(
        self,
        issue_type: str,
        amount: str,
        snapshot: SystemResourceSnapshot
    ) -> Optional[CuriosityQuestion]:
        """
        Generate question for detected resource issue.

        Parameters:
            issue_type: Type of issue (memory_high, cpu_saturated, etc.)
            amount: Amount/severity
            snapshot: Full resource snapshot

        Returns:
            CuriosityQuestion or None
        """
        if issue_type == "memory_high":
            hypothesis = "SYSTEM_MEMORY_PRESSURE"
            question = (
                f"Why is memory usage at {amount}? "
                f"Used: {snapshot.memory_used_gb:.1f}GB/{snapshot.memory_total_gb:.1f}GB. "
                f"Should I enable aggressive garbage collection or restart memory-intensive services?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.8
            cost = 0.3

        elif issue_type == "swap_high":
            hypothesis = "SYSTEM_SWAP_PRESSURE"
            question = (
                f"Why is swap usage at {amount}? "
                f"Used: {snapshot.swap_used_gb:.1f}GB. "
                f"Is there a memory leak in a long-running process?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.9  # High priority - swap usage indicates memory leak
            cost = 0.4

        elif issue_type == "cpu_saturated":
            hypothesis = "SYSTEM_CPU_SATURATION"
            question = (
                f"Why is CPU usage at {amount}? "
                f"Load avg: {snapshot.load_avg_1min:.1f}. "
                f"Are D-REAM experiments running with proper CPU affinity?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.7
            cost = 0.3

        elif issue_type == "load_avg_high":
            hypothesis = "SYSTEM_LOAD_EXCESSIVE"
            question = (
                f"Why is load average {amount} (CPU cores: {psutil.cpu_count()})? "
                f"Are there too many concurrent experiments?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.7
            cost = 0.3

        elif issue_type == "disk_low":
            hypothesis = "SYSTEM_DISK_PRESSURE"
            question = (
                f"Why is disk usage at {amount}? "
                f"Should I clean up old D-REAM artifacts or PHASE test outputs?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.6
            cost = 0.2

        elif issue_type == "gpu_saturated":
            hypothesis = "GPU_SATURATION"
            question = (
                f"Why is GPU utilization at {amount}? "
                f"Is a model training stuck or is OLLAMA overloaded?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.7
            cost = 0.3

        elif issue_type == "gpu_memory_high":
            hypothesis = "GPU_MEMORY_PRESSURE"
            question = (
                f"Why is GPU memory at {amount}? "
                f"Should I restart OLLAMA services to free GPU memory?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.7
            cost = 0.3

        else:
            return None

        # Build evidence
        evidence = [
            f"issue:{issue_type}",
            f"severity:{amount}",
            f"memory:{snapshot.memory_percent*100:.1f}%",
            f"cpu:{snapshot.cpu_percent*100:.1f}%",
            f"load_avg:{snapshot.load_avg_1min:.1f}",
            f"swap:{snapshot.swap_percent*100:.1f}%"
        ]

        if snapshot.gpu_utilization:
            evidence.append(f"gpu:{snapshot.gpu_utilization*100:.1f}%")

        return CuriosityQuestion(
            id=f"resource.{issue_type}",
            hypothesis=hypothesis,
            question=question,
            evidence=evidence,
            action_class=action_class,
            autonomy=3,  # Execute autonomously
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=f"system.{issue_type}"
        )


class ModuleDiscoveryMonitor:
    """
    Proactively scans /home/kloros/src for modules and compares against capability registry.

    Generates questions about:
    - Modules that exist but aren't in the registry
    - Modules with __init__.py suggesting they're complete
    - Modules with recent activity (mtime)
    - Knowledge base documents describing capabilities
    """

    def __init__(
        self,
        src_path: Path = Path("/home/kloros/src"),
        knowledge_base_path: Path = Path("/home/kloros/knowledge_base"),
        capability_yaml: Path = Path("/home/kloros/src/registry/capabilities.yaml")
    ):
        self.src_path = src_path
        self.knowledge_base_path = knowledge_base_path
        self.capability_yaml = capability_yaml
        self.semantic_store = SemanticEvidenceStore()

        if ChemPub is not None:
            self.chem_pub = ChemPub()
            self.prioritizer = QuestionPrioritizer(self.chem_pub)
            logger.info("[module_discovery] Using QuestionPrioritizer for question emission")
        else:
            self.prioritizer = None

        # Load known capabilities from registry
        self.known_capabilities = self._load_known_capabilities()

    def _load_known_capabilities(self) -> set:
        """Extract known capability keys from YAML."""
        known = set()
        try:
            import yaml
            with open(self.capability_yaml) as f:
                capabilities = yaml.safe_load(f)
                if capabilities:
                    # Add top-level keys (memory, tools, tts, etc.)
                    for key in capabilities.keys():
                        known.add(key)
                        # Also add module paths if they exist
                        cap = capabilities[key]
                        if isinstance(cap, dict) and 'module' in cap:
                            # Extract module name (e.g., kloros_memory from 'kloros_memory')
                            module_name = cap['module'].split('.')[-1]
                            known.add(module_name)
        except Exception as e:
            logger.warning(f"[module_discovery] Failed to load capability registry: {e}")
        return known

    def scan_undiscovered_modules(self) -> List[Dict[str, Any]]:
        """
        Scan /home/kloros/src for modules not in capability registry.

        Returns list of undiscovered modules with metadata.
        """
        undiscovered = []

        if not self.src_path.exists():
            return undiscovered

        # Scan top-level directories in src/
        for module_dir in self.src_path.iterdir():
            if not module_dir.is_dir():
                continue

            # Skip special directories
            if module_dir.name.startswith('.') or module_dir.name in ['__pycache__', 'tests']:
                continue

            module_name = module_dir.name

            # Check if module is in capability registry
            # Try various key patterns: module_name, category.module_name
            potential_keys = [
                module_name,
                f"module.{module_name}",
                f"tools.{module_name}",
                f"agent.{module_name}",
                f"reasoning.{module_name}",
                f"service.{module_name}"
            ]

            if not any(key in self.known_capabilities for key in potential_keys):
                # Module not in registry - gather metadata
                init_file = module_dir / "__init__.py"
                has_init = init_file.exists()

                # Get modification time
                try:
                    mtime = module_dir.stat().st_mtime
                except:
                    mtime = 0

                # Count Python files
                py_files = list(module_dir.glob("*.py"))
                py_count = len(py_files)

                # Check if there's documentation
                has_docs = (module_dir / "README.md").exists()

                # Only report modules that look "real" (not empty experiments)
                if has_init or py_count >= 2 or has_docs:
                    undiscovered.append({
                        "module_name": module_name,
                        "path": str(module_dir),
                        "has_init": has_init,
                        "py_file_count": py_count,
                        "has_docs": has_docs,
                        "mtime": mtime
                    })

        return undiscovered

    def scan_knowledge_base_gaps(self) -> List[Dict[str, Any]]:
        """
        Scan knowledge base for documentation about capabilities not in registry.
        """
        gaps = []

        if not self.knowledge_base_path.exists():
            return gaps

        # Scan markdown files in knowledge base
        for md_file in self.knowledge_base_path.rglob("*.md"):
            # Extract topics/capabilities mentioned
            try:
                content = md_file.read_text()
                # Simple heuristic: look for capability-like patterns
                # This is rough but better than nothing
                if "capability" in content.lower() or "module" in content.lower():
                    gaps.append({
                        "doc_file": str(md_file.relative_to(self.knowledge_base_path)),
                        "path": str(md_file),
                        "mtime": md_file.stat().st_mtime
                    })
            except Exception as e:
                logger.debug(f"[module_discovery] Failed to read {md_file}: {e}")

        return gaps

    def generate_discovery_questions(self) -> List[CuriosityQuestion]:
        """
        Generate curiosity questions about undiscovered modules.
        Emits via QuestionPrioritizer instead of returning list.
        """
        undiscovered = self.scan_undiscovered_modules()

        logger.info(f"[module_discovery] Found {len(undiscovered)} undiscovered modules in /src")

        candidate_questions = []

        for module_info in undiscovered:
            module_name = module_info["module_name"]

            value = 0.5

            if module_info["has_init"]:
                value += 0.1
            if module_info["has_docs"]:
                value += 0.1
            if module_info["py_file_count"] >= 3:
                value += 0.1

            import time
            age_days = (time.time() - module_info["mtime"]) / 86400
            if age_days < 30:
                value += 0.15

            if value < 0.6:
                continue

            hypothesis = f"UNDISCOVERED_MODULE_{module_name.upper()}"

            question = (
                f"I found an undiscovered module '{module_name}' in /src with "
                f"{module_info['py_file_count']} Python files. "
                f"What does it do, and should it be added to my capability registry?"
            )

            static_evidence = [
                f"path:{module_info['path']}",
                f"has_init:{module_info['has_init']}",
                f"py_files:{module_info['py_file_count']}",
                f"has_docs:{module_info['has_docs']}",
                f"age_days:{int(age_days)}"
            ]

            semantic_evidence = self.semantic_store.to_evidence_list(module_name)

            evidence = static_evidence + semantic_evidence

            q = CuriosityQuestion(
                id=f"discover.module.{module_name}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=ActionClass.INVESTIGATE,
                autonomy=3,
                value_estimate=min(value, 0.95),
                cost=0.15,
                status=QuestionStatus.READY,
                capability_key=f"undiscovered.{module_name}"
            )

            candidate_questions.append(q)

        candidate_questions.sort(key=lambda q: q.value_estimate, reverse=True)
        top_questions = candidate_questions[:5]

        emitted_count = 0
        if self.prioritizer is not None:
            for q in top_questions:
                self.prioritizer.prioritize_and_emit(q)
                emitted_count += 1

        logger.info(f"[module_discovery] Emitted {emitted_count} discovery questions via prioritizer")

        return []


class ChaosLabMonitor:
    """
    Monitors Chaos Lab results and generates curiosity questions about poor self-healing.

    Purpose:
        Detect repeated healing failures and spawn D-REAM experiments
        to improve self-healing capabilities

    Outcomes:
        - Identifies components with low healing scores (<70%)
        - Detects high MTTR scenarios (>5s)
        - Generates questions about systematic healing failures
    """

    def __init__(
        self,
        history_path: Path = Path("/home/kloros/.kloros/chaos_history.jsonl"),
        metrics_path: Path = Path("/home/kloros/.kloros/dream_chaos_metrics.jsonl")
    ):
        self.history_path = history_path
        self.metrics_path = metrics_path
        self.lookback_experiments = 20
        self.signals_skipped_disabled = 0

        if ChemPub is not None:
            self.chem_pub = ChemPub()
            self.prioritizer = QuestionPrioritizer(self.chem_pub)
            logger.info("[chaos_monitor] Using QuestionPrioritizer for question emission")
        else:
            self.prioritizer = None

    def _is_target_disabled(self, target: str) -> bool:
        """
        Check if a chaos scenario target is for a disabled system.

        Args:
            target: Target system (e.g., "rag.synthesis", "dream.domain:cpu", "tts")

        Returns:
            True if target system is disabled, False otherwise
        """
        import os

        if any(keyword in target.lower() for keyword in ['dream', 'rag']):
            dream_enabled = os.getenv('KLR_ENABLE_DREAM_EVOLUTION', '1') == '1'
            if not dream_enabled:
                return True

        if any(keyword in target.lower() for keyword in ['tts', 'audio']):
            return True

        return False

    def scan_healing_failures(self) -> Dict[str, List[Dict]]:
        """
        Scan recent chaos experiments for systematic healing failures.

        Returns:
            Dict mapping scenario_id to list of failure data
        """
        failures_by_scenario = defaultdict(list)

        if not self.history_path.exists():
            return failures_by_scenario

        try:
            # Read recent experiments
            with open(self.history_path, 'r') as f:
                experiments = [json.loads(line) for line in f if line.strip()]

            # Group by scenario, take last N per scenario
            by_scenario = defaultdict(list)
            for exp in experiments:
                spec_id = exp.get("spec_id")
                by_scenario[spec_id].append(exp)

            # Analyze each scenario
            for spec_id, exps in by_scenario.items():
                recent = exps[-self.lookback_experiments:]

                # Calculate healing rate
                healed_count = sum(1 for e in recent if e.get("outcome", {}).get("healed"))
                healing_rate = healed_count / len(recent) if recent else 0

                # Calculate average score
                avg_score = sum(e.get("score", 0) for e in recent) / len(recent) if recent else 0

                # Flag if poor performance (healing rate < 30% OR avg score < 50)
                if healing_rate < 0.3 or avg_score < 50:
                    failures_by_scenario[spec_id].extend(recent)

        except Exception as e:
            logger.error(f"[chaos_monitor] Failed to scan failures: {e}")

        return dict(failures_by_scenario)

    def generate_chaos_questions(self) -> List[CuriosityQuestion]:
        """Generate curiosity questions from chaos lab failures.
        Emits via QuestionPrioritizer instead of returning list.
        """
        failures = self.scan_healing_failures()

        emitted_count = 0
        for spec_id, experiments in failures.items():
            if len(experiments) < 3:
                continue

            healed_count = sum(1 for e in experiments if e.get("outcome", {}).get("healed"))
            healing_rate = healed_count / len(experiments)
            avg_score = sum(e.get("score", 0) for e in experiments) / len(experiments)

            mttrs = [e.get("outcome", {}).get("duration_s", 0) for e in experiments]
            avg_mttr = sum(mttrs) / len(mttrs) if mttrs else 0

            target = experiments[0].get("target", "unknown")
            mode = experiments[0].get("mode", "unknown")

            if self._is_target_disabled(target):
                logger.info(
                    f"[chaos_monitor] Healing failure expected for disabled system: "
                    f"{spec_id} (target={target}, rate={healing_rate:.1%}, score={avg_score:.1f})"
                )
                self.signals_skipped_disabled += 1
                continue

            hypothesis = f"POOR_SELF_HEALING_{spec_id.upper().replace('-', '_')}"
            question = (
                f"Why is self-healing failing for {spec_id} ({target}/{mode})? "
                f"Healing rate: {healing_rate:.1%}, avg score: {avg_score:.0f}/100, "
                f"avg MTTR: {avg_mttr:.1f}s over {len(experiments)} experiments. "
                f"How can I improve recovery mechanisms?"
            )

            evidence = [
                f"scenario:{spec_id}",
                f"target:{target}",
                f"mode:{mode}"
            ]

            if healing_rate < 0.1 or avg_score < 30:
                value = 0.95
            elif healing_rate < 0.3 or avg_score < 50:
                value = 0.85
            else:
                value = 0.70

            q = CuriosityQuestion(
                id=f"chaos.healing_failure.{spec_id}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=ActionClass.PROPOSE_FIX,
                autonomy=3,
                value_estimate=value,
                cost=0.5,
                status=QuestionStatus.READY,
                capability_key=f"self_healing.{target}"
            )

            if self.prioritizer is not None:
                self.prioritizer.prioritize_and_emit(q)
                emitted_count += 1

        logger.info(f"[chaos_monitor] Emitted {emitted_count} chaos questions via prioritizer")

        return []


class MetricQualityMonitor:
    """
    Detects fake/placeholder metrics in tournament results.

    Generates questions when:
    - All tournament candidates have identical metrics
    - Results contain placeholder values (0.95, 150.0, etc.)
    - Zero variance across candidates (no actual comparison)
    - Investigations complete but produce no actionable insights
    """

    def __init__(
        self,
        orchestrator_log_path: Path = Path("/home/kloros/logs/orchestrator")
    ):
        self.orchestrator_log_path = orchestrator_log_path
        self.lookback_minutes = 60

        # Known placeholder values that indicate fake metrics
        self.placeholder_patterns = {
            0.95,  # Common "good enough" exact match
            150.0,  # Common placeholder latency p50
            300.0,  # Common placeholder latency p95
            512.0,  # Common placeholder memory
            25.0,   # Common placeholder CPU
            100     # Common placeholder query count
        }

    def scan_recent_experiments(self) -> List[Dict[str, Any]]:
        """
        Scan orchestrator logs for completed experiments with suspicious metrics.
        """
        suspicious_experiments = []

        if not self.orchestrator_log_path.exists():
            return suspicious_experiments

        # Read curiosity experiments log
        experiments_log = self.orchestrator_log_path / "curiosity_experiments.jsonl"
        if not experiments_log.exists():
            return suspicious_experiments

        import time
        cutoff_time = time.time() - (self.lookback_minutes * 60)

        try:
            with open(experiments_log, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        entry = json.loads(line)

                        # Only look at recent completed experiments
                        ts_str = entry.get("ts", "")
                        if not ts_str:
                            continue

                        # Parse ISO timestamp
                        from datetime import datetime
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).timestamp()

                        if ts < cutoff_time:
                            continue

                        # Check if experiment completed with tournament
                        intent = entry.get("intent", {})
                        data = intent.get("data", {})
                        result = data.get("experiment_result", {})

                        if result.get("status") != "complete":
                            continue

                        if result.get("mode") != "tournament":
                            continue

                        # Analyze tournament metrics
                        artifacts = result.get("artifacts", {})
                        tournament = artifacts.get("tournament", {})
                        results = tournament.get("results", {})

                        if not results:
                            continue

                        # Check aggregated metrics by instance
                        aggregated = results.get("aggregated_by_instance", {})

                        if self._has_suspicious_metrics(aggregated, data):
                            suspicious_experiments.append({
                                "question_id": data.get("question_id", "unknown"),
                                "hypothesis": data.get("hypothesis", "unknown"),
                                "timestamp": ts,
                                "total_candidates": result.get("total_candidates", 0),
                                "aggregated_metrics": aggregated,
                                "reason": self._classify_suspicion(aggregated)
                            })

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.debug(f"[metric_quality] Failed to parse experiment entry: {e}")
                        continue

        except Exception as e:
            logger.warning(f"[metric_quality] Failed to scan experiments log: {e}")

        return suspicious_experiments

    def _has_suspicious_metrics(self, aggregated: Dict[str, Any], question_data: Dict[str, Any]) -> bool:
        """Check if aggregated metrics look fake/placeholder."""
        if not aggregated:
            return False

        # Extract metric values from all candidates
        all_metrics = []
        for instance_id, metrics in aggregated.items():
            if not isinstance(metrics, dict):
                continue

            # Collect numeric metrics
            all_metrics.append({
                "pass_rate": metrics.get("pass_rate"),
                "latency": metrics.get("avg_latency_p50_ms"),
                "exact_match": metrics.get("avg_exact_match_mean")
            })

        if len(all_metrics) < 2:
            return False

        # Check 1: All candidates have identical metrics (zero variance)
        first = all_metrics[0]
        if all(m == first for m in all_metrics):
            return True

        # Check 2: Metrics contain multiple placeholder values
        placeholder_count = 0
        for metric_dict in all_metrics:
            for value in metric_dict.values():
                if value in self.placeholder_patterns:
                    placeholder_count += 1

        # If >50% of metric values are placeholders, suspicious
        total_values = len(all_metrics) * 3  # 3 metrics per candidate
        if placeholder_count / total_values > 0.5:
            return True

        # Check 3: All candidates passed with perfect 1.0 pass_rate and identical metrics
        all_perfect = all(m.get("pass_rate") == 1.0 for m in all_metrics)
        latencies = [m.get("latency") for m in all_metrics if m.get("latency") is not None]

        if all_perfect and len(set(latencies)) == 1:  # All same latency
            return True

        return False

    def _classify_suspicion(self, aggregated: Dict[str, Any]) -> str:
        """Classify why metrics are suspicious."""
        if not aggregated:
            return "empty_results"

        all_metrics = []
        for metrics in aggregated.values():
            if isinstance(metrics, dict):
                all_metrics.append(metrics)

        if not all_metrics:
            return "no_metrics"

        # Check for identical metrics
        first = all_metrics[0]
        if all(m == first for m in all_metrics):
            return "identical_metrics_all_candidates"

        # Check for placeholder patterns
        has_placeholders = any(
            any(v in self.placeholder_patterns for v in m.values() if isinstance(v, (int, float)))
            for m in all_metrics
        )

        if has_placeholders:
            return "placeholder_values_detected"

        return "zero_variance_suspicious"

    def generate_quality_questions(self) -> List[CuriosityQuestion]:
        """Generate questions about suspicious metric quality."""
        questions = []

        suspicious = self.scan_recent_experiments()

        if not suspicious:
            return questions

        logger.info(f"[metric_quality] Found {len(suspicious)} experiments with suspicious metrics")

        # Group by reason
        by_reason = {}
        for exp in suspicious:
            reason = exp["reason"]
            if reason not in by_reason:
                by_reason[reason] = []
            by_reason[reason].append(exp)

        # Generate questions for each pattern
        for reason, experiments in by_reason.items():
            if len(experiments) < 2:  # Only care if it's a pattern
                continue

            question_ids = [e["question_id"] for e in experiments[:3]]

            if reason == "identical_metrics_all_candidates":
                hypothesis = "FAKE_TOURNAMENT_METRICS"
                question = (
                    f"I ran {len(experiments)} investigations but all tournament candidates "
                    f"produced identical metrics. Why am I not actually comparing anything? "
                    f"Examples: {', '.join(question_ids)}. "
                    f"Do I need domain-specific evaluators instead of placeholder tests?"
                )
                value = 0.95  # Very high value - wasting compute on fake tournaments
                cost = 0.2

            elif reason == "placeholder_values_detected":
                hypothesis = "PLACEHOLDER_TEST_METRICS"
                question = (
                    f"I detected placeholder values (0.95, 150ms, etc.) in {len(experiments)} "
                    f"tournament results. Am I running mock tests instead of real evaluations? "
                    f"Examples: {', '.join(question_ids)}."
                )
                value = 0.90
                cost = 0.2

            else:
                hypothesis = "LOW_QUALITY_METRICS"
                question = (
                    f"Tournament metrics show zero variance across candidates in {len(experiments)} "
                    f"experiments. I'm not learning anything from these investigations. "
                    f"Examples: {', '.join(question_ids)}."
                )
                value = 0.85
                cost = 0.2

            evidence = [
                f"pattern:{reason}",
                f"affected_investigations:{len(experiments)}",
                f"examples:{','.join(question_ids[:3])}"
            ]

            q = CuriosityQuestion(
                id=f"meta.metric_quality.{reason}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=ActionClass.PROPOSE_FIX,
                autonomy=3,
                value_estimate=value,
                cost=cost,
                status=QuestionStatus.READY,
                capability_key="meta.evaluation_quality"
            )

            questions.append(q)

        return questions


class ExceptionMonitor:
    """
    Monitors orchestrator/system logs and DREAM experiment logs for exceptions.

    Purpose:
        Automatically detect runtime failures and systematic errors, route to D-REAM for resolution

    Monitors:
        - ModuleNotFoundError / ImportError
        - FileNotFoundError
        - AttributeError
        - ValueError (systematic failures)
        - TypeError
        - Runtime exceptions in orchestrator logs
        - Repeated errors in DREAM experiment runs
    """

    def __init__(
        self,
        orchestrator_log_path: Path = Path("/home/kloros/logs/orchestrator"),
        dream_log_path: Path = Path("/home/kloros/logs/dream"),
        chat_log_path: Path = Path("/home/kloros/.kloros/logs")
    ):
        self.orchestrator_log_path = orchestrator_log_path
        self.dream_log_path = dream_log_path
        self.chat_log_path = chat_log_path
        self.lookback_minutes = 60  # Look back 1 hour for patterns
        self.systematic_error_threshold = 3  # Alert after 3 failures - something's broken
        self.chat_error_threshold = 2  # Alert after 2 chat issues - users are affected NOW

    def generate_exception_questions(self) -> List[CuriosityQuestion]:
        """
        Parse orchestrator and DREAM logs for exceptions and generate questions.

        Returns:
            List of CuriosityQuestion objects
        """
        questions = []

        # Read orchestrator logs for curiosity experiment errors
        if self.orchestrator_log_path.exists():
            try:
                experiments_log = self.orchestrator_log_path / "curiosity_experiments.jsonl"
                if experiments_log.exists():
                    exceptions = self._parse_jsonl_exceptions(experiments_log)
                    for exc in exceptions:
                        q = self._question_for_exception(exc)
                        if q:
                            questions.append(q)
            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to read orchestrator logs: {e}")

        # Read DREAM logs for systematic experiment failures
        if self.dream_log_path.exists():
            try:
                systematic_errors = self._scan_dream_logs_for_systematic_errors()
                for error_info in systematic_errors:
                    q = self._question_for_systematic_error(error_info)
                    if q:
                        questions.append(q)
            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to read DREAM logs: {e}")

        # Read chat logs for conversation issues
        if self.chat_log_path.exists():
            try:
                chat_issues = self._scan_chat_logs_for_issues()
                for issue_info in chat_issues:
                    q = self._question_for_chat_issue(issue_info)
                    if q:
                        questions.append(q)
                logger.info(f"[exception_monitor] Generated {len([q for q in questions if 'chat' in q.id])} chat-related questions")
            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to read chat logs: {e}")

        return questions

    def _parse_jsonl_exceptions(self, log_file: Path) -> List[Dict[str, Any]]:
        """
        Parse JSONL log file for exceptions from recent entries.

        Returns:
            List of exception dicts with type, message, module, context
        """
        exceptions = []
        cutoff_time = datetime.now().timestamp() - (self.lookback_minutes * 60)

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)

                        # Check timestamp
                        ts = entry.get("ts")
                        if isinstance(ts, str):
                            ts = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                        elif not isinstance(ts, (int, float)):
                            continue

                        if ts < cutoff_time:
                            continue

                        # Check for experiment errors
                        result = entry.get("intent", {}).get("data", {}).get("experiment_result", {})
                        if result.get("status") == "error":
                            error_msg = result.get("error", "")
                            if error_msg and ("ModuleNotFoundError" in error_msg or
                                            "ImportError" in error_msg or
                                            "No module named" in error_msg):

                                # Extract module name from error message
                                module = ""
                                if "No module named " in error_msg:
                                    parts = error_msg.split("No module named ")
                                    if len(parts) > 1:
                                        module = parts[1].strip().strip("'\"").split()[0]

                                exc = {
                                    "type": "ModuleNotFoundError" if "ModuleNotFoundError" in error_msg else "ImportError",
                                    "message": error_msg,
                                    "module": module,
                                    "context": entry.get("intent", {}).get("data", {}).get("question", ""),
                                    "timestamp": ts,
                                    "similar_modules": []
                                }

                                # Find similar modules if it's a spica_domain pattern
                                if "spica_domain" in module or module.startswith("src.phase.domains.spica"):
                                    exc["similar_modules"] = self._find_similar_modules(module)

                                exceptions.append(exc)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"[exception_monitor] Failed to parse {log_file}: {e}")

        return exceptions

    def _scan_dream_logs_for_systematic_errors(self) -> List[Dict[str, Any]]:
        """
        Scan all DREAM experiment logs for systematic repeated errors.

        Returns:
            List of error info dicts with experiment, error, count, recent
        """
        systematic_errors = []
        cutoff_time = datetime.now().timestamp() - (self.lookback_minutes * 60)

        # Scan all DREAM experiment log files
        if not self.dream_log_path.exists():
            return systematic_errors

        for log_file in self.dream_log_path.glob("*.jsonl"):
            try:
                # Count errors by type for this experiment
                error_counts = defaultdict(lambda: {"count": 0, "recent_ts": 0, "params": []})
                experiment_name = log_file.stem

                with open(log_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)

                            # Check timestamp
                            ts = entry.get("ts", 0)
                            if not isinstance(ts, (int, float)) or ts < cutoff_time:
                                continue

                            # Check for errors
                            error = entry.get("error")
                            if error:
                                # Normalize error string
                                error_key = error.split("(")[0] if "(" in error else error
                                error_counts[error_key]["count"] += 1
                                error_counts[error_key]["recent_ts"] = max(
                                    error_counts[error_key]["recent_ts"], ts
                                )
                                # Track params for debugging
                                params = entry.get("params", {})
                                if len(error_counts[error_key]["params"]) < 3:
                                    error_counts[error_key]["params"].append(params)

                        except json.JSONDecodeError:
                            continue

                # Generate systematic error reports for high-frequency errors
                for error_type, info in error_counts.items():
                    if info["count"] >= self.systematic_error_threshold:
                        systematic_errors.append({
                            "experiment": experiment_name,
                            "error_type": error_type,
                            "error_count": info["count"],
                            "recent_timestamp": info["recent_ts"],
                            "sample_params": info["params"][:3]
                        })

            except Exception as e:
                logger.warning(f"[exception_monitor] Failed to scan {log_file}: {e}")

        return systematic_errors

    def _question_for_systematic_error(self, error_info: Dict[str, Any]) -> Optional[CuriosityQuestion]:
        """
        Generate curiosity question from systematic error pattern.

        Parameters:
            error_info: Dict with experiment, error_type, error_count, sample_params

        Returns:
            CuriosityQuestion or None
        """
        experiment = error_info["experiment"]
        error_type = error_info["error_type"]
        count = error_info["error_count"]
        sample_params = error_info.get("sample_params", [])

        # Parse error type
        if "ValueError" in error_type:
            error_category = "value_error"
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"SYSTEMATIC_VALUE_ERROR_{experiment.upper()}"
        elif "TypeError" in error_type:
            error_category = "type_error"
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"SYSTEMATIC_TYPE_ERROR_{experiment.upper()}"
        elif "ModuleNotFoundError" in error_type or "ImportError" in error_type:
            error_category = "import_error"
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"SYSTEMATIC_IMPORT_ERROR_{experiment.upper()}"
        else:
            error_category = "unknown_error"
            action_class = ActionClass.INVESTIGATE
            hypothesis = f"SYSTEMATIC_ERROR_{experiment.upper()}"

        # Extract key info from error message
        error_summary = error_type[:200] if len(error_type) > 200 else error_type

        # Build evidence
        evidence = [
            f"experiment:{experiment}",
            f"error_type:{error_category}",
            f"occurrences:{count}",
            f"error:{error_summary}"
        ]

        # Add sample params if available
        if sample_params:
            evidence.append(f"sample_params:{json.dumps(sample_params[0])[:100]}")

        q = CuriosityQuestion(
            id=f"systematic.{experiment}.{error_category}.{hashlib.md5(error_type.encode()).hexdigest()[:8]}",
            hypothesis=hypothesis,
            question=(
                f"Why is {experiment} failing systematically with {error_type}? "
                f"This error occurred {count} times in the last {self.lookback_minutes} minutes. "
                f"How do I fix the root cause?"
            ),
            evidence=evidence,
            action_class=action_class,
            autonomy=3,
            value_estimate=0.9,  # Very high - blocks entire experiment domain
            cost=0.4,
            capability_key=f"experiment.{experiment}"
        )

        return q

    def _scan_chat_logs_for_issues(self) -> List[Dict[str, Any]]:
        """
        Scan chat logs for conversation issues like errors, failed tool calls, etc.

        Returns:
            List of issue dicts with type, count, examples
        """
        issues = []
        cutoff_time = datetime.now().timestamp() - (self.lookback_minutes * 60)

        # Count different issue types
        from collections import defaultdict
        issue_counts = defaultdict(lambda: {"count": 0, "examples": []})

        # Get today's log file
        today = datetime.now().strftime("%Y%m%d")
        log_file = self.chat_log_path / f"kloros-{today}.jsonl"

        if not log_file.exists():
            return issues

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)

                        # Check timestamp
                        ts_str = entry.get("ts")
                        if not ts_str:
                            continue

                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).timestamp()
                        if ts < cutoff_time:
                            continue

                        # Check for various issue types
                        level = entry.get("level", "INFO")
                        name = entry.get("name", "")

                        # Error-level events
                        if level == "ERROR":
                            issue_type = f"error_{name}" if name else "error_unknown"
                            issue_counts[issue_type]["count"] += 1
                            issue_counts[issue_type]["examples"].append(entry)

                        # Failed turns (no_voice repeated)
                        if name == "turn_done" and not entry.get("ok", True):
                            reason = entry.get("reason", "unknown")
                            if reason != "no_voice":  # Ignore silence, focus on actual failures
                                issue_type = f"turn_failed_{reason}"
                                issue_counts[issue_type]["count"] += 1
                                issue_counts[issue_type]["examples"].append(entry)

                        # Tool call failures
                        if "tool" in name and "error" in entry:
                            issue_type = "tool_call_failed"
                            issue_counts[issue_type]["count"] += 1
                            issue_counts[issue_type]["examples"].append(entry)

                        # Response generation issues
                        if name == "final_response":
                            response_text = entry.get("final_text", "")
                            # Detect error patterns in responses
                            if any(phrase in response_text.lower() for phrase in
                                   ["error", "failed", "unable", "could not", "cannot"]):
                                issue_type = "response_error_indicated"
                                issue_counts[issue_type]["count"] += 1
                                issue_counts[issue_type]["examples"].append(entry)

                    except (json.JSONDecodeError, ValueError):
                        continue

        except Exception as e:
            logger.warning(f"[chat_monitor] Error reading chat log: {e}")
            return issues

        # Filter by chat-specific threshold (lower than DREAM threshold)
        for issue_type, data in issue_counts.items():
            if data["count"] >= self.chat_error_threshold:
                issues.append({
                    "issue_type": issue_type,
                    "count": data["count"],
                    "examples": data["examples"][:3]  # Keep max 3 examples
                })

        return issues

    def _question_for_chat_issue(self, issue_info: Dict[str, Any]) -> Optional[CuriosityQuestion]:
        """
        Generate curiosity question from chat log issue pattern.

        Parameters:
            issue_info: Dict with issue_type, count, examples

        Returns:
            CuriosityQuestion or None
        """
        issue_type = issue_info["issue_type"]
        count = issue_info["count"]
        examples = issue_info.get("examples", [])

        # Determine action class and hypothesis based on issue type
        if "error" in issue_type:
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = f"CHAT_ERROR_{issue_type.upper()}"
            question = (
                f"Why are chat interactions experiencing {issue_type} errors? "
                f"This occurred {count} times in the last {self.lookback_minutes} minutes. "
                f"How can I improve conversation reliability?"
            )
            value_estimate = 0.85  # High - affects user experience
        elif "tool_call_failed" in issue_type:
            action_class = ActionClass.PROPOSE_FIX
            hypothesis = "CHAT_TOOL_FAILURE"
            question = (
                f"Why are tool calls failing in chat interactions? "
                f"Detected {count} failures in the last {self.lookback_minutes} minutes. "
                f"How can I fix tool integration issues?"
            )
            value_estimate = 0.8
        elif "turn_failed" in issue_type:
            action_class = ActionClass.INVESTIGATE
            hypothesis = f"CHAT_TURN_FAILURE_{issue_type.split('_')[-1].upper()}"
            question = (
                f"Why are conversation turns failing with reason '{issue_type.split('_')[-1]}'? "
                f"This happened {count} times recently. "
                f"What's blocking successful interactions?"
            )
            value_estimate = 0.75
        elif "response_error" in issue_type:
            action_class = ActionClass.INVESTIGATE
            hypothesis = "CHAT_RESPONSE_QUALITY"
            question = (
                f"Why are {count} recent responses indicating errors or failures? "
                f"How can I improve response quality and error handling?"
            )
            value_estimate = 0.7
        else:
            action_class = ActionClass.INVESTIGATE
            hypothesis = f"CHAT_ISSUE_{issue_type.upper()}"
            question = (
                f"What's causing repeated {issue_type} issues in chat? "
                f"Detected {count} occurrences. "
                f"How should I address this pattern?"
            )
            value_estimate = 0.65

        # Build evidence
        evidence = [
            f"issue_type:{issue_type}",
            f"occurrences:{count}",
            f"timeframe:{self.lookback_minutes}min"
        ]

        # Add sample from examples
        if examples:
            first_example = examples[0]
            if "final_text" in first_example:
                evidence.append(f"example_response:{first_example['final_text'][:100]}")
            elif "reason" in first_example:
                evidence.append(f"example_reason:{first_example['reason']}")

        q = CuriosityQuestion(
            id=f"chat.{issue_type}.{hashlib.md5(issue_type.encode()).hexdigest()[:8]}",
            hypothesis=hypothesis,
            question=question,
            evidence=evidence,
            action_class=action_class,
            autonomy=3,
            value_estimate=value_estimate,
            cost=0.3,
            capability_key="conversation.quality"
        )

        return q

    def _find_similar_modules(self, missing_module: str) -> List[str]:
        """Find similar existing modules that could serve as templates."""
        similar = []

        if "spica_domain" in missing_module:
            # Look for spica_* modules in phase/domains
            domains_path = Path("/home/kloros/src/phase/domains")
            if domains_path.exists():
                spica_modules = list(domains_path.glob("spica_*.py"))
                # Return top 3 most relevant
                similar = [m.stem for m in spica_modules[:3]]

        return similar

    def _question_for_exception(self, exc: Dict[str, Any]) -> Optional[CuriosityQuestion]:
        """
        Generate curiosity question from exception details.

        Parameters:
            exc: Exception dict with type, message, module, context

        Returns:
            CuriosityQuestion or None
        """
        if exc["type"] == "ModuleNotFoundError":
            module = exc["module"]
            similar = exc["similar_modules"]

            hypothesis = f"MISSING_MODULE_{module.replace('.', '_').upper()}"

            if similar:
                question = (
                    f"How do I generate {module}.py using patterns from existing modules "
                    f"like {', '.join(similar)}?"
                )
                action_class = ActionClass.PROPOSE_FIX
                value = 0.9  # High value - blocking tournament execution
                cost = 0.4   # Code generation moderate cost
            else:
                question = f"What module or package provides {module}?"
                action_class = ActionClass.FIND_SUBSTITUTE
                value = 0.7
                cost = 0.3

            evidence = [
                f"error:{exc['type']}",
                f"module:{module}",
                f"context:{exc.get('context', 'unknown')}"
            ]

            if similar:
                evidence.append(f"similar_modules:{','.join(similar)}")

            return CuriosityQuestion(
                id=f"codegen.{module.replace('.', '_')}",
                hypothesis=hypothesis,
                question=question,
                evidence=evidence,
                action_class=action_class,
                autonomy=3,
                value_estimate=value,
                cost=cost,
                status=QuestionStatus.READY,
                capability_key=f"module.{module}"
            )

        elif exc["type"] == "ImportError":
            hypothesis = "IMPORT_ERROR"
            question = f"What dependency or configuration is missing? {exc['message']}"

            return CuriosityQuestion(
                id=f"import.{abs(hash(exc['message'])) % 100000}",
                hypothesis=hypothesis,
                question=question,
                evidence=[f"error:{exc['type']}", f"message:{exc['message']}"],
                action_class=ActionClass.INVESTIGATE,
                autonomy=3,
                value_estimate=0.6,
                cost=0.2,
                status=QuestionStatus.READY,
                capability_key="system.imports"
            )

        return None


class CuriosityCore:
    """
    Generates curiosity questions from capability matrix analysis.

    Purpose:
        Enable KLoROS to form concrete questions about missing/degraded capabilities

    Outcomes:
        - Analyzes capability matrix for gaps and contradictions
        - Generates questions with hypotheses and evidence
        - Estimates value and cost for each question
        - Writes curiosity_feed.json for consumption by picker/scheduler
    """

    _instance: Optional['CuriosityCore'] = None
    _daemon_subs_initialized: bool = False

    def __new__(cls, feed_path: Optional[Path] = None, enable_daemon_subscriptions: bool = False):
        """
        Enforce singleton pattern to prevent thread/memory leaks.

        Returns the same instance on subsequent calls to prevent:
        - Repeated SemanticEvidenceStore creation
        - Duplicate daemon subscription threads
        - Memory leaks from abandoned instances
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, feed_path: Optional[Path] = None, enable_daemon_subscriptions: bool = False):
        """
        Initialize curiosity core.

        Parameters:
            feed_path: Path to write curiosity_feed.json
        """
        if self._initialized:
            return

        if feed_path is None:
            feed_path = Path("/home/kloros/.kloros/curiosity_feed.json")

        self.feed_path = feed_path
        self.feed: Optional[CuriosityFeed] = None

        self.semantic_store: Optional[SemanticEvidenceStore] = None
        try:
            self.semantic_store = SemanticEvidenceStore()
            logger.debug("[curiosity_core] Initialized SemanticEvidenceStore for suppression tracking")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to initialize SemanticEvidenceStore: {e}, suppression checks disabled")

        self.daemon_questions: List[CuriosityQuestion] = []
        self.chem_subs: List[Any] = []  # Multiple subscriptions, one per daemon

        # Initialize daemon subscriptions only once at class level
        if enable_daemon_subscriptions and not CuriosityCore._daemon_subs_initialized:
            self.subscribe_to_daemon_questions()
            CuriosityCore._daemon_subs_initialized = True
            logger.info("[curiosity_core] Daemon subscriptions initialized")

        self._initialized = True
        logger.debug("[curiosity_core] CuriosityCore singleton initialized")

    def should_generate_followup(self, parent_question: Dict[str, Any], investigation_result: Dict[str, Any]) -> bool:
        """
        Decide if followup generation is productive.

        Avoid infinite loops where questions can't be answered with available evidence.
        Pattern: followup of followup with low confidence and insufficient evidence
        indicates the question is unresolvable.

        Args:
            parent_question: The parent question dict with 'id' field
            investigation_result: Investigation result with 'confidence' and 'evidence' fields

        Returns:
            True if followup should be generated, False if question is unresolvable
        """
        parent_id = parent_question.get('id', '')

        if parent_id.endswith('.followup'):
            confidence = investigation_result.get('confidence', 0)
            evidence_list = investigation_result.get('evidence', [])
            evidence_count = len(evidence_list) if evidence_list else 0

            if confidence < 0.6 and evidence_count < 2:
                logger.info(f"[curiosity_core] Parent question {parent_id} unresolvable "
                           f"(low confidence={confidence:.2f}, insufficient evidence={evidence_count})")
                return False

        return True

    def _convert_daemon_message_to_questions(self, message: Dict[str, Any]) -> List[CuriosityQuestion]:
        """
        Convert a ChemBus daemon message to CuriosityQuestion objects.

        Parameters:
            message: ChemBus message payload with facts containing question data

        Returns:
            List of CuriosityQuestion objects (empty if message is malformed)
        """
        questions = []

        try:
            facts = message.get('facts', {})

            question_id = facts.get('question_id')
            question_text = facts.get('question')
            hypothesis = facts.get('hypothesis')

            if not question_id or not question_text:
                logger.warning("[curiosity_core] Daemon message missing required fields (question_id, question)")
                return questions

            evidence = facts.get('evidence', [])
            severity = facts.get('severity', 'medium')
            source = facts.get('source', 'daemon')

            evidence_hash = None
            if evidence:
                evidence_str = '|'.join(sorted(evidence))
                evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()[:16]

            action_class = ActionClass.INVESTIGATE
            if severity == 'critical':
                action_class = ActionClass.PROPOSE_FIX
            elif severity == 'high':
                action_class = ActionClass.INVESTIGATE

            metadata = {
                'severity': severity,
                'source': source,
            }
            if 'metadata' in facts:
                metadata.update(facts['metadata'])

            q = CuriosityQuestion(
                id=question_id,
                hypothesis=hypothesis or question_text,
                question=question_text,
                evidence=evidence,
                evidence_hash=evidence_hash,
                action_class=action_class,
                autonomy=2,
                value_estimate=0.8 if severity in ['critical', 'high'] else 0.6,
                cost=0.5,
                status=QuestionStatus.READY,
                created_at=datetime.now().isoformat(),
                metadata=metadata
            )

            questions.append(q)
            logger.info(f"[curiosity_core] Received 1 integration question from daemon: {question_id}")

        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to convert daemon message: {e}")

        return questions

    def _on_daemon_question(self, message: Dict[str, Any]):
        """
        ChemBus callback for daemon question messages.

        Parameters:
            message: ChemBus message payload
        """
        new_questions = self._convert_daemon_message_to_questions(message)
        self.daemon_questions.extend(new_questions)

    def subscribe_to_daemon_questions(self):
        """
        Subscribe to all daemon question streams via ChemBus.

        Sets up subscriptions to all 4 daemon signals:
        - curiosity.integration_question (IntegrationMonitorDaemon)
        - curiosity.capability_question (CapabilityDiscoveryDaemon)
        - curiosity.exploration_question (ExplorationScannerDaemon)
        - curiosity.knowledge_question (KnowledgeDiscoveryScannerDaemon)
        """
        if ChemSub is None:
            logger.warning("[curiosity_core] ChemSub not available, daemon subscription disabled")
            return

        daemon_signals = [
            "curiosity.integration_question",
            "curiosity.capability_question",
            "curiosity.exploration_question",
            "curiosity.knowledge_question"
        ]

        for signal in daemon_signals:
            try:
                sub = ChemSub(
                    topic=signal,
                    on_json=self._on_daemon_question,
                    zooid_name="curiosity_core",
                    niche="curiosity"
                )
                self.chem_subs.append(sub)
                logger.info(f"[curiosity_core] Subscribed to {signal}")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to subscribe to {signal}: {e}")

        logger.info(f"[curiosity_core] Successfully subscribed to {len(self.chem_subs)}/4 daemon signals")

    def _get_daemon_questions(self) -> List[CuriosityQuestion]:
        """
        Retrieve and clear accumulated daemon questions.

        Returns:
            List of CuriosityQuestion objects from daemon subscriptions
        """
        questions = self.daemon_questions.copy()
        self.daemon_questions.clear()

        if questions:
            logger.info(f"[curiosity_core] Retrieved {len(questions)} integration questions from daemon")

        return questions

    def generate_questions_from_matrix(
        self,
        matrix: CapabilityMatrix,
        include_performance: bool = True,
        include_resources: bool = True,
        include_exceptions: bool = True
    ) -> CuriosityFeed:
        """
        Generate curiosity questions from capability matrix, performance trends, system resources, runtime exceptions, and test failures.

        Question generation rules:
            1. Missing capability → "What exact step enables <capability>?"
            2. Degraded capability for > N minutes → "Which mitigation improved it last time?"
            3. Affordance needed but capability missing → "What's the minimal substitute?"
            4. Precondition unmet → Specific question about the precondition
            5. Performance degradation → "Why did {metric} drop in {experiment}?"
            6. Resource pressure → "Why is {resource} at {threshold}?"
            7. Runtime exception → "How do I fix/generate missing module/dependency?"
            8. Test failure → "Why is test {test_name} failing?"

        Parameters:
            matrix: CapabilityMatrix with evaluated capabilities
            include_performance: If True, add performance-based questions from D-REAM
            include_resources: If True, add resource-based questions from system state
            include_exceptions: If True, add exception-based questions from orchestrator logs

        Returns:
            CuriosityFeed with generated questions
        """
        questions = []

        # Generate capability-based questions
        for cap in matrix.capabilities:
            # Rule 1: Missing capability
            if cap.state == CapabilityState.MISSING:
                q = self._question_for_missing_capability(cap)
                if q:
                    questions.append(q)

            # Rule 2: Degraded capability
            elif cap.state == CapabilityState.DEGRADED:
                q = self._question_for_degraded_capability(cap)
                if q:
                    questions.append(q)

        # Generate performance-based questions from D-REAM
        if include_performance:
            try:
                perf_monitor = PerformanceMonitor()
                # Monitor key experiments
                experiments = [
                    "spica_cognitive_variants",
                    "audio_latency_trim",
                    "conv_quality_tune",
                    "rag_opt_baseline",
                    "tool_evolution"
                ]
                perf_questions = perf_monitor.generate_performance_questions(experiments)
                questions.extend(perf_questions)
                logger.info(f"[curiosity_core] Generated {len(perf_questions)} performance questions")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to generate performance questions: {e}")

        # Generate resource-based questions from system state
        if include_resources:
            try:
                resource_monitor = SystemResourceMonitor()
                resource_questions = resource_monitor.generate_resource_questions()
                questions.extend(resource_questions)
                logger.info(f"[curiosity_core] Generated {len(resource_questions)} resource questions")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to generate resource questions: {e}")

        # Generate exception-based questions from orchestrator logs
        if include_exceptions:
            try:
                exception_monitor = ExceptionMonitor()
                exception_questions = exception_monitor.generate_exception_questions()
                questions.extend(exception_questions)
                logger.info(f"[curiosity_core] Generated {len(exception_questions)} exception questions")
            except Exception as e:
                logger.warning(f"[curiosity_core] Failed to generate exception questions: {e}")

        # Generate test-failure-based questions from pytest results
        try:
            test_monitor = TestResultMonitor()
            test_questions = test_monitor.generate_test_questions()
            questions.extend(test_questions)
            logger.info(f"[curiosity_core] Generated {len(test_questions)} test-failure questions")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to generate test questions: {e}")

        # MODULE DISCOVERY: Now handled by CapabilityDiscoveryMonitorDaemon
        # The old ModuleDiscoveryMonitor caused OOM by scanning entire /src every 60s
        # Now handled by: /home/kloros/src/kloros/daemons/capability_discovery_daemon.py (systemd service)
        # Questions received via ChemBus signal: curiosity.capability_question
        logger.debug("[curiosity_core] Module discovery now provided by CapabilityDiscoveryDaemon")

        # META-COGNITION: Check if my own investigations are producing meaningful results
        try:
            quality_monitor = MetricQualityMonitor()
            quality_questions = quality_monitor.generate_quality_questions()
            questions.extend(quality_questions)
            logger.info(f"[curiosity_core] Generated {len(quality_questions)} metric quality questions")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to generate quality questions: {e}")

        # CHAOS LAB MONITORING: Detect poor self-healing performance
        try:
            chaos_monitor = ChaosLabMonitor()
            chaos_questions = chaos_monitor.generate_chaos_questions()
            questions.extend(chaos_questions)
            logger.info(f"[curiosity_core] Generated {len(chaos_questions)} chaos lab questions")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to generate chaos questions: {e}")

        # INTEGRATION ANALYSIS: Replaced by IntegrationMonitorDaemon (streaming daemon)
        # The old IntegrationFlowMonitor caused memory leaks (150MB/min growth from parsing 500+ files every 60s)
        # Now handled by: /home/kloros/src/kloros/daemons/integration_monitor_daemon.py (systemd service)
        # Questions received via ChemBus signal: curiosity.integration_question
        logger.debug("[curiosity_core] Integration questions now provided by IntegrationMonitorDaemon")

        # CAPABILITY DISCOVERY: Replaced by CapabilityDiscoveryMonitorDaemon (streaming daemon)
        # The old CapabilityDiscoveryMonitor caused heavy filesystem scanning every 60s
        # Now handled by: /home/kloros/src/kloros/daemons/capability_discovery_daemon.py (systemd service)
        # Questions received via ChemBus signal: curiosity.capability_question
        # Includes semantic analysis to prevent phantom capability discoveries
        logger.debug("[curiosity_core] Capability questions now provided by CapabilityDiscoveryDaemon")

        # EXPLORATION: Replaced by ExplorationScannerDaemon (streaming daemon)
        # The old ExplorationScanner caused heavy system scanning every 60s
        # Now handled by: /home/kloros/src/kloros/daemons/exploration_scanner_daemon.py (systemd service)
        # Questions received via ChemBus signal: curiosity.exploration_question
        # Timer-based (300s interval) instead of file-watching, scans GPU/hardware state
        logger.debug("[curiosity_core] Exploration questions now provided by ExplorationScannerDaemon")

        # KNOWLEDGE DISCOVERY: Replaced by KnowledgeDiscoveryScannerDaemon (streaming daemon)
        # The old KnowledgeDiscoveryScanner caused filesystem scanning and memory accumulation
        # Now handled by: /home/kloros/src/kloros/daemons/knowledge_discovery_daemon.py (systemd service)
        # Questions received via ChemBus signal: curiosity.knowledge_question
        # Watches docs/ and src/ for unindexed documentation, missing docstrings, stale files
        logger.debug("[curiosity_core] Knowledge questions now provided by KnowledgeDiscoveryDaemon")

        # STREAMING DAEMON QUESTIONS: Receive questions from event-driven daemons
        try:
            daemon_questions = self._get_daemon_questions()
            questions.extend(daemon_questions)
            if daemon_questions:
                logger.info(f"[curiosity_core] Received {len(daemon_questions)} integration questions from daemon")
        except Exception as e:
            logger.warning(f"[curiosity_core] Failed to retrieve daemon questions: {e}")

        # EARLY FILTER: Remove questions still in cooldown BEFORE expensive reasoning
        # This prevents wasted LLM processing on recently-processed questions
        pre_reasoning_count = len(questions)
        try:
            from src.registry.processed_question_filter import ProcessedQuestionFilter

            question_filter = ProcessedQuestionFilter()
            questions = question_filter.filter_questions(questions)
            filtered_before_reasoning = pre_reasoning_count - len(questions)

            if filtered_before_reasoning > 0:
                logger.info(f"[curiosity_core] Early filter: removed {filtered_before_reasoning} "
                           f"questions in cooldown (saved expensive reasoning on {filtered_before_reasoning} questions)")
        except Exception as e:
            logger.warning(f"[curiosity_core] Early filtering failed, continuing: {e}")

        # FILTER: Skip questions for intentionally disabled services/components (Layer 1)
        pre_disabled_filter_count = len(questions)
        filtered_questions = []
        for q in questions:
            if q.metadata.get("intentionally_disabled"):
                logger.debug(f"[curiosity_core] Skipping intentionally disabled: {q.id}")
                continue
            filtered_questions.append(q)
        questions = filtered_questions
        filtered_disabled = pre_disabled_filter_count - len(questions)
        if filtered_disabled > 0:
            logger.info(f"[curiosity_core] Filtered {filtered_disabled} questions for intentionally disabled services")

        # FILTER: Skip questions for suppressed capabilities from evidence learning (Layer 2)
        pre_suppression_filter_count = len(questions)
        filtered_questions = []
        suppressed_count = 0
        for q in questions:
            capability_key = q.capability_key
            if capability_key and self.semantic_store:
                try:
                    if self.semantic_store.is_suppressed(capability_key):
                        suppression_info = self.semantic_store.get_suppression_info(capability_key)
                        reason = suppression_info.get("reason", "unknown reason")
                        logger.debug(f"[curiosity_core] Skipping suppressed capability: {capability_key} ({reason})")
                        suppressed_count += 1
                        continue
                except Exception as e:
                    logger.error(f"[curiosity_core] Error checking suppression for {capability_key}: {e}, assuming not suppressed")
            filtered_questions.append(q)
        questions = filtered_questions
        if suppressed_count > 0:
            logger.info(f"[curiosity_core] Filtered {suppressed_count} questions for suppressed capabilities")

        class StreamingBuffer:
            """Bounded buffer for streaming VOI-based ranking."""

            def __init__(self, capacity: int = 20):
                self.capacity = capacity
                self.buffer: List = []

            def add(self, item):
                """Add item to buffer. Returns top-10 by VOI when full, else None."""
                self.buffer.append(item)
                if len(self.buffer) >= self.capacity:
                    return self.flush()
                return None

            def flush(self):
                """Sort by VOI, return top-10, clear buffer."""
                self.buffer.sort(key=lambda x: x.voi_score, reverse=True)
                top_10 = self.buffer[:10]
                self.buffer.clear()
                return top_10

            def get_remaining(self):
                """Get remaining questions sorted by VOI."""
                if not self.buffer:
                    return []
                self.buffer.sort(key=lambda x: x.voi_score, reverse=True)
                return self.buffer[:10]

        # BRAINMODS REASONING: Apply advanced reasoning to questions
        # Use ToT/Debate/VOI to explore hypotheses and re-rank by value
        try:
            from src.registry.curiosity_reasoning import get_curiosity_reasoning

            reasoning = get_curiosity_reasoning()

            # Separate discovery questions to ensure they're always included
            discovery_questions = [q for q in questions if "UNDISCOVERED_MODULE" in q.hypothesis]
            other_questions = [q for q in questions if "UNDISCOVERED_MODULE" not in q.hypothesis]

            logger.info(f"[curiosity_core] Applying brainmods reasoning to {len(other_questions)} questions (preserving {len(discovery_questions)} discovery questions)...")

            buffer = StreamingBuffer(capacity=20)
            follow_up_count = 0
            all_reasoned = []

            logger.info(f"[curiosity_core] Streaming {len(other_questions)} questions through reasoning...")

            for reasoned_q in reasoning.stream_reason(other_questions):
                top_batch = buffer.add(reasoned_q)
                all_reasoned.append(reasoned_q)

                if top_batch:
                    logger.info(f"[curiosity_core] Processing top-10 batch from buffer (total followups: {follow_up_count})")

                    for rq in top_batch:
                        if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                            logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                            break

                        investigation_result = {
                            'confidence': rq.confidence,
                            'evidence': rq.follow_up_questions if rq.follow_up_questions else []
                        }

                        if not self.should_generate_followup({'id': rq.original_question.id}, investigation_result):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (unresolvable)")
                            continue

                        # Check metadata flag
                        if hasattr(rq.original_question, 'metadata') and rq.original_question.metadata.get('intentionally_disabled'):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (intentionally disabled)")
                            continue

                        # Check if original question's capability is suppressed
                        if hasattr(rq.original_question, 'capability_key') and rq.original_question.capability_key:
                            if self.semantic_store:
                                try:
                                    if self.semantic_store.is_suppressed(rq.original_question.capability_key):
                                        suppression_info = self.semantic_store.get_suppression_info(rq.original_question.capability_key)
                                        reason = suppression_info.get("reason", "unknown reason")
                                        logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (capability suppressed: {rq.original_question.capability_key}, {reason})")
                                        continue
                                except Exception as e:
                                    logger.error(f"[curiosity_core] Error checking suppression for {rq.original_question.capability_key}: {e}, proceeding with followup")

                        # Fallback: Check if question ID contains orphaned_queue and service is disabled
                        if 'orphaned_queue' in rq.original_question.id:
                            from registry.systemd_helpers import is_service_intentionally_disabled
                            if is_service_intentionally_disabled('kloros-dream.service'):
                                logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (D-REAM disabled)")
                                continue

                        if rq.follow_up_questions:
                            logger.info(f"[curiosity_core] Generating {len(rq.follow_up_questions)} "
                                      f"follow-up questions for {rq.original_question.id}")

                            for follow_up_dict in rq.follow_up_questions[:3]:
                                if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                                    logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                                    break

                                action_class_str = follow_up_dict.get('action_class', 'investigate')
                                try:
                                    action_class_enum = ActionClass(action_class_str)
                                except ValueError:
                                    action_class_enum = ActionClass.INVESTIGATE

                                follow_up_q = CuriosityQuestion(
                                    id=f"{rq.original_question.id}.followup.{follow_up_count}",
                                    hypothesis=follow_up_dict.get('hypothesis', 'UNKNOWN'),
                                    question=follow_up_dict.get('question', 'Unknown follow-up question'),
                                    evidence=[f"parent_question:{rq.original_question.id}",
                                            f"reason:{follow_up_dict.get('reason', 'Evidence gap detected')}",
                                            f"evidence_type:{follow_up_dict.get('evidence_type', 'unknown')}"],
                                    action_class=action_class_enum,
                                    value_estimate=rq.voi_score * 0.7,
                                    cost=0.2,
                                    capability_key=rq.original_question.capability_key if hasattr(rq.original_question, 'capability_key') else None
                                )
                                questions.append(follow_up_q)
                                follow_up_count += 1

                    if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                        break

            if follow_up_count < MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                remaining = buffer.get_remaining()
                if remaining:
                    logger.info(f"[curiosity_core] Processing {len(remaining)} remaining questions from buffer")

                    for rq in remaining:
                        if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                            logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                            break

                        investigation_result = {
                            'confidence': rq.confidence,
                            'evidence': rq.follow_up_questions if rq.follow_up_questions else []
                        }

                        if not self.should_generate_followup({'id': rq.original_question.id}, investigation_result):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (unresolvable)")
                            continue

                        # Check metadata flag
                        if hasattr(rq.original_question, 'metadata') and rq.original_question.metadata.get('intentionally_disabled'):
                            logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (intentionally disabled)")
                            continue

                        # Check if original question's capability is suppressed
                        if hasattr(rq.original_question, 'capability_key') and rq.original_question.capability_key:
                            if self.semantic_store:
                                try:
                                    if self.semantic_store.is_suppressed(rq.original_question.capability_key):
                                        suppression_info = self.semantic_store.get_suppression_info(rq.original_question.capability_key)
                                        reason = suppression_info.get("reason", "unknown reason")
                                        logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (capability suppressed: {rq.original_question.capability_key}, {reason})")
                                        continue
                                except Exception as e:
                                    logger.error(f"[curiosity_core] Error checking suppression for {rq.original_question.capability_key}: {e}, proceeding with followup")

                        # Fallback: Check if question ID contains orphaned_queue and service is disabled
                        if 'orphaned_queue' in rq.original_question.id:
                            from registry.systemd_helpers import is_service_intentionally_disabled
                            if is_service_intentionally_disabled('kloros-dream.service'):
                                logger.debug(f"[curiosity_core] Skipping followup generation for {rq.original_question.id} (D-REAM disabled)")
                                continue

                        if rq.follow_up_questions:
                            logger.info(f"[curiosity_core] Generating {len(rq.follow_up_questions)} "
                                      f"follow-up questions for {rq.original_question.id}")

                            for follow_up_dict in rq.follow_up_questions[:3]:
                                if follow_up_count >= MAX_FOLLOWUP_QUESTIONS_PER_CYCLE:
                                    logger.info(f"Reached followup limit ({MAX_FOLLOWUP_QUESTIONS_PER_CYCLE}), stopping generation")
                                    break

                                action_class_str = follow_up_dict.get('action_class', 'investigate')
                                try:
                                    action_class_enum = ActionClass(action_class_str)
                                except ValueError:
                                    action_class_enum = ActionClass.INVESTIGATE

                                follow_up_q = CuriosityQuestion(
                                    id=f"{rq.original_question.id}.followup.{follow_up_count}",
                                    hypothesis=follow_up_dict.get('hypothesis', 'UNKNOWN'),
                                    question=follow_up_dict.get('question', 'Unknown follow-up question'),
                                    evidence=[f"parent_question:{rq.original_question.id}",
                                            f"reason:{follow_up_dict.get('reason', 'Evidence gap detected')}",
                                            f"evidence_type:{follow_up_dict.get('evidence_type', 'unknown')}"],
                                    action_class=action_class_enum,
                                    value_estimate=rq.voi_score * 0.7,
                                    cost=0.2,
                                    capability_key=rq.original_question.capability_key if hasattr(rq.original_question, 'capability_key') else None
                                )
                                questions.append(follow_up_q)
                                follow_up_count += 1

            for rq in all_reasoned:
                if hasattr(rq.original_question, 'value_estimate'):
                    rq.original_question.value_estimate = rq.voi_score

            for dq in discovery_questions:
                dq.value_estimate = 0.95

            questions = discovery_questions + [rq.original_question for rq in all_reasoned]

            if follow_up_count > 0:
                logger.info(f"[curiosity_core] Added {follow_up_count} follow-up questions to feed")

            if questions:
                logger.info(f"[curiosity_core] Questions re-ranked by VOI, top question: "
                          f"{questions[0].id} (VOI: {questions[0].value_estimate:.2f})")
            else:
                logger.info(f"[curiosity_core] Questions re-ranked by VOI, top question: none")

        except Exception as e:
            logger.warning(f"[curiosity_core] Brainmods reasoning failed, continuing without: {e}")
            # Continue with original questions if reasoning fails

        # SAFETY FILTER: Double-check cooldown after reasoning (defense in depth)
        # Follow-up questions generated during reasoning aren't pre-filtered, so catch them here
        try:
            from src.registry.processed_question_filter import ProcessedQuestionFilter

            question_filter = ProcessedQuestionFilter()
            original_count = len(questions)
            questions = question_filter.filter_questions(questions)
            filtered_count = original_count - len(questions)

            if filtered_count > 0:
                logger.info(f"[curiosity_core] Safety filter: removed {filtered_count} questions "
                           f"in cooldown (mostly follow-ups, kept {len(questions)})")
        except Exception as e:
            logger.warning(f"[curiosity_core] Question filtering failed, "
                          f"continuing with unfiltered questions: {e}")
            # Fail-open: if filtering breaks, use all questions

        self.feed = CuriosityFeed(questions=questions)
        return self.feed

    def _question_for_missing_capability(self, cap: CapabilityRecord) -> Optional[CuriosityQuestion]:
        """
        Generate question for missing capability.

        Strategy:
            - Parse "why" to identify specific failure
            - Propose investigation or soft fallback
            - Estimate value based on capability kind and provides
        """
        # Extract specific failure reason
        why = cap.why.lower()

        # Determine hypothesis
        if "not in group" in why:
            hypothesis = f"{cap.key.upper()}_PERMISSION"
            question = f"Can I prove {cap.key} works by adding user to the required group, or is there a permission-free substitute?"
            action_class = ActionClass.REQUEST_USER_ACTION
            value = 0.7
            cost = 0.2
        elif "not found" in why or "does not exist" in why:
            hypothesis = f"{cap.key.upper()}_INSTALLATION"
            question = f"What exact step installs {cap.key}, or what existing capability can substitute for it?"
            action_class = ActionClass.FIND_SUBSTITUTE
            value = 0.6
            cost = 0.3
        elif "not readable" in why or "not writable" in why:
            hypothesis = f"{cap.key.upper()}_ACCESS"
            question = f"What file permission change enables {cap.key}, and is it safe to apply at autonomy level 2?"
            action_class = ActionClass.PROPOSE_FIX
            value = 0.7
            cost = 0.2
        elif "not set" in why:
            hypothesis = f"{cap.key.upper()}_CONFIGURATION"
            question = f"What value should be set for the missing configuration, and what are the safe defaults?"
            action_class = ActionClass.INVESTIGATE
            value = 0.6
            cost = 0.1
        elif "not available" in why or "not in path" in why:
            hypothesis = f"{cap.key.upper()}_DEPENDENCY"
            question = f"Can I verify {cap.key} installation, or identify an alternative dependency?"
            action_class = ActionClass.FIND_SUBSTITUTE
            value = 0.5
            cost = 0.3
        elif "disabled in config" in why:
            hypothesis = f"{cap.key.upper()}_DISABLED"
            question = f"Why is {cap.key} disabled? Is it safe to enable, or should I use an alternative?"
            action_class = ActionClass.INVESTIGATE
            value = 0.4
            cost = 0.1
        else:
            hypothesis = f"{cap.key.upper()}_PRECONDITION"
            question = f"What unmet precondition blocks {cap.key}, and how can I work around it?"
            action_class = ActionClass.EXPLAIN_AND_SOFT_FALLBACK
            value = 0.5
            cost = 0.2

        # Boost value for high-impact capabilities
        if cap.kind in ["service", "reasoning"]:
            value += 0.1
        if cap.provides and len(cap.provides) > 2:
            value += 0.1
        value = min(1.0, value)

        return CuriosityQuestion(
            id=f"enable.{cap.key}",
            hypothesis=hypothesis,
            question=question,
            evidence=[
                f"capability:{cap.key}",
                f"state:{cap.state.value}",
                f"why:{cap.why}",
                f"provides:{','.join(cap.provides)}"
            ],
            action_class=action_class,
            autonomy=3,
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=cap.key
        )

    def _question_for_degraded_capability(self, cap: CapabilityRecord) -> Optional[CuriosityQuestion]:
        """
        Generate question for degraded capability.

        Strategy:
            - Capability exists but health check fails
            - Propose investigation or stabilization
            - Higher urgency than missing capabilities
        """
        hypothesis = f"{cap.key.upper()}_DEGRADED"
        question = f"What caused {cap.key} to degrade ({cap.why}), and which past mitigation worked best?"
        action_class = ActionClass.PROPOSE_FIX
        value = 0.8  # Degraded capabilities are high priority
        cost = 0.3

        return CuriosityQuestion(
            id=f"stabilize.{cap.key}",
            hypothesis=hypothesis,
            question=question,
            evidence=[
                f"capability:{cap.key}",
                f"state:{cap.state.value}",
                f"why:{cap.why}",
                f"provides:{','.join(cap.provides)}"
            ],
            action_class=action_class,
            autonomy=3,
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=cap.key
        )

    def write_feed_json(self) -> bool:
        """
        Write curiosity_feed.json to disk.

        Returns:
            True if successful, False otherwise
        """
        if not self.feed:
            logger.error("[curiosity_core] No feed to write (call generate_questions_from_matrix first)")
            return False

        try:
            # Ensure directory exists
            self.feed_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON
            with open(self.feed_path, 'w') as f:
                json.dump(self.feed.to_dict(), f, indent=2)

            logger.info(f"[curiosity_core] Wrote {len(self.feed.questions)} questions to {self.feed_path}")
            return True

        except Exception as e:
            logger.error(f"[curiosity_core] Failed to write feed: {e}")
            return False

    def load_feed_from_disk(self) -> bool:
        """
        Load curiosity_feed.json from disk into self.feed.

        Returns:
            True if successful, False otherwise
        """
        if not self.feed_path.exists():
            logger.warning(f"[curiosity_core] Feed file not found: {self.feed_path}")
            return False

        try:
            with open(self.feed_path, 'r') as f:
                data = json.load(f)

            # Reconstruct CuriosityQuestion objects
            questions = []
            for q_dict in data.get("questions", []):
                # Convert action_class string back to enum
                action_class_str = q_dict.get("action_class", "explain_and_soft_fallback")
                try:
                    action_class = ActionClass(action_class_str)
                except ValueError:
                    action_class = ActionClass.EXPLAIN_AND_SOFT_FALLBACK

                # Convert status string back to enum
                status_str = q_dict.get("status", "ready")
                try:
                    status = QuestionStatus(status_str)
                except ValueError:
                    status = QuestionStatus.READY

                question = CuriosityQuestion(
                    id=q_dict["id"],
                    hypothesis=q_dict["hypothesis"],
                    question=q_dict["question"],
                    evidence=q_dict.get("evidence", []),
                    action_class=action_class,
                    autonomy=q_dict.get("autonomy", 2),
                    value_estimate=q_dict.get("value_estimate", 0.5),
                    cost=q_dict.get("cost", 0.2),
                    status=status,
                    created_at=q_dict.get("created_at", datetime.now().isoformat()),
                    capability_key=q_dict.get("capability_key")
                )
                questions.append(question)

            # Create CuriosityFeed
            self.feed = CuriosityFeed(
                questions=questions,
                generated_at=data.get("generated_at", datetime.now().isoformat())
            )

            logger.debug(f"[curiosity_core] Loaded {len(questions)} questions from {self.feed_path}")
            return True

        except Exception as e:
            logger.error(f"[curiosity_core] Failed to load feed from disk: {e}")
            return False

    def get_top_questions(self, n: int = 5) -> List[CuriosityQuestion]:
        """
        Get top N questions sorted by value/cost ratio.

        Parameters:
            n: Number of questions to return

        Returns:
            List of top questions
        """
        if not self.feed:
            return []

        # Sort by value/cost ratio (higher is better)
        sorted_questions = sorted(
            self.feed.questions,
            key=lambda q: q.value_estimate / max(q.cost, 0.01),
            reverse=True
        )

        return sorted_questions[:n]

    def get_summary_text(self) -> str:
        """
        Generate human-readable summary of curiosity feed.

        Returns:
            Formatted string for display
        """
        if not self.feed:
            return "No curiosity feed available"

        lines = []
        lines.append("CURIOSITY FEED")
        lines.append("=" * 60)
        lines.append(f"Total questions: {len(self.feed.questions)}")
        lines.append("")

        top_questions = self.get_top_questions(n=5)
        if top_questions:
            lines.append("TOP 5 QUESTIONS (by value/cost ratio):")
            for i, q in enumerate(top_questions, 1):
                ratio = q.value_estimate / max(q.cost, 0.01)
                lines.append(f"{i}. [{ratio:.1f}] {q.question}")
                lines.append(f"   Hypothesis: {q.hypothesis}")
                lines.append(f"   Action: {q.action_class.value}")
                lines.append("")

        return "\n".join(lines)


def main():
    """Self-test and demonstration."""
    print("=== Curiosity Core Self-Test ===\n")

    # Load capability matrix
    try:
        from .capability_evaluator import CapabilityEvaluator
    except ImportError:
        from capability_evaluator import CapabilityEvaluator

    evaluator = CapabilityEvaluator()
    matrix = evaluator.evaluate_all()

    # Generate questions
    curiosity = CuriosityCore()
    feed = curiosity.generate_questions_from_matrix(matrix)

    print(curiosity.get_summary_text())

    # Write feed file
    if curiosity.write_feed_json():
        print(f"✓ Wrote feed to {curiosity.feed_path}")
    else:
        print(f"✗ Failed to write feed")

    return feed


if __name__ == "__main__":
    main()
