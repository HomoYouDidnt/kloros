"""
KPI tracking for coding agent performance.

Tracks:
- pass@k, repair@k
- mean time-to-green
- diff_size
- revert_rate
- flake_rate
- latency p95
"""
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
from collections import defaultdict
import statistics

@dataclass
class TaskMetrics:
    """Metrics for a single coding task."""
    task_id: str
    task_type: str  # bug_fix, feature, refactor, test_gen
    timestamp: str
    duration_ms: float

    # Attempt tracking
    attempts: int
    success: bool

    # Code changes
    diff_size: int  # Total lines changed
    files_changed: int
    insertions: int
    deletions: int

    # Validation
    tests_passed: bool
    linter_passed: bool
    type_check_passed: bool
    security_passed: bool

    # Reverted?
    reverted: bool = False
    revert_reason: Optional[str] = None

    # Flake detection
    flaky: bool = False

@dataclass
class RunMetrics:
    """Aggregated metrics for a run."""
    run_id: str
    timestamp: str
    duration_sec: float

    # Success rates
    pass_at_1: float
    pass_at_3: float
    repair_at_3: float  # For bug fixes specifically

    # Code quality
    mean_diff_size: float
    median_diff_size: float
    total_files_changed: int

    # Rates
    revert_rate: float
    flake_rate: float

    # Latency
    mean_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float

    # Task breakdown
    tasks_total: int
    tasks_succeeded: int
    tasks_failed: int

    task_metrics: List[TaskMetrics] = field(default_factory=list)

class MetricsTracker:
    """Track and aggregate coding agent metrics."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.current_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_start = time.time()

        self.task_metrics: List[TaskMetrics] = []

    def record_task(self, metrics: TaskMetrics):
        """Record metrics for a completed task."""
        self.task_metrics.append(metrics)

        # Save individual task log
        task_file = self.output_dir / f"task_{metrics.task_id}.json"
        with open(task_file, 'w') as f:
            json.dump(asdict(metrics), f, indent=2)

    def compute_run_metrics(self) -> RunMetrics:
        """Compute aggregated metrics for the run."""
        if not self.task_metrics:
            return RunMetrics(
                run_id=self.current_run_id,
                timestamp=datetime.now().isoformat(),
                duration_sec=time.time() - self.run_start,
                pass_at_1=0.0,
                pass_at_3=0.0,
                repair_at_3=0.0,
                mean_diff_size=0.0,
                median_diff_size=0.0,
                total_files_changed=0,
                revert_rate=0.0,
                flake_rate=0.0,
                mean_latency_ms=0.0,
                p95_latency_ms=0.0,
                p99_latency_ms=0.0,
                tasks_total=0,
                tasks_succeeded=0,
                tasks_failed=0
            )

        # Group by task_id to compute pass@k
        task_groups = defaultdict(list)
        for metric in self.task_metrics:
            task_groups[metric.task_id].append(metric)

        # pass@1: succeeded on first attempt
        pass_at_1_count = sum(
            1 for attempts in task_groups.values()
            if attempts[0].success
        )

        # pass@3: succeeded within 3 attempts
        pass_at_3_count = sum(
            1 for attempts in task_groups.values()
            if any(a.success for a in attempts[:3])
        )

        # repair@3: bug fixes that succeeded within 3 attempts
        bug_fix_groups = {
            tid: attempts for tid, attempts in task_groups.items()
            if attempts[0].task_type == 'bug_fix'
        }
        repair_at_3_count = sum(
            1 for attempts in bug_fix_groups.values()
            if any(a.success for a in attempts[:3])
        )

        total_tasks = len(task_groups)
        total_bug_fixes = len(bug_fix_groups)

        pass_at_1 = pass_at_1_count / total_tasks if total_tasks > 0 else 0.0
        pass_at_3 = pass_at_3_count / total_tasks if total_tasks > 0 else 0.0
        repair_at_3 = repair_at_3_count / total_bug_fixes if total_bug_fixes > 0 else 0.0

        # Diff size stats
        diff_sizes = [m.diff_size for m in self.task_metrics]
        mean_diff_size = statistics.mean(diff_sizes) if diff_sizes else 0.0
        median_diff_size = statistics.median(diff_sizes) if diff_sizes else 0.0

        # Revert and flake rates
        revert_rate = sum(m.reverted for m in self.task_metrics) / len(self.task_metrics)
        flake_rate = sum(m.flaky for m in self.task_metrics) / len(self.task_metrics)

        # Latency stats
        latencies = [m.duration_ms for m in self.task_metrics]
        mean_latency = statistics.mean(latencies) if latencies else 0.0

        sorted_latencies = sorted(latencies)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p99_idx = int(len(sorted_latencies) * 0.99)
        p95_latency = sorted_latencies[p95_idx] if sorted_latencies else 0.0
        p99_latency = sorted_latencies[p99_idx] if sorted_latencies else 0.0

        # Task counts
        tasks_succeeded = sum(m.success for m in self.task_metrics)
        tasks_failed = len(self.task_metrics) - tasks_succeeded

        # Total files changed
        total_files = sum(m.files_changed for m in self.task_metrics)

        return RunMetrics(
            run_id=self.current_run_id,
            timestamp=datetime.now().isoformat(),
            duration_sec=time.time() - self.run_start,
            pass_at_1=pass_at_1,
            pass_at_3=pass_at_3,
            repair_at_3=repair_at_3,
            mean_diff_size=mean_diff_size,
            median_diff_size=median_diff_size,
            total_files_changed=total_files,
            revert_rate=revert_rate,
            flake_rate=flake_rate,
            mean_latency_ms=mean_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            tasks_total=total_tasks,
            tasks_succeeded=tasks_succeeded,
            tasks_failed=tasks_failed,
            task_metrics=self.task_metrics
        )

    def save_run_summary(self) -> Path:
        """Save run summary to JSON."""
        metrics = self.compute_run_metrics()

        summary_file = self.output_dir / f"run_{self.current_run_id}.json"
        with open(summary_file, 'w') as f:
            # Convert to dict but exclude task_metrics (too large)
            summary_dict = asdict(metrics)
            summary_dict['task_metrics'] = [
                {"task_id": t.task_id, "success": t.success, "diff_size": t.diff_size}
                for t in metrics.task_metrics
            ]
            json.dump(summary_dict, f, indent=2)

        return summary_file

    def compare_to_baseline(self, baseline_file: Path) -> Dict[str, float]:
        """
        Compare current run to baseline metrics.

        Returns:
            Dict with delta values (positive = improvement)
        """
        with open(baseline_file, 'r') as f:
            baseline = json.load(f)

        current = asdict(self.compute_run_metrics())

        deltas = {}
        for key in ['pass_at_1', 'pass_at_3', 'repair_at_3']:
            deltas[f"{key}_delta"] = current[key] - baseline[key]

        # For diff_size, lower is better
        deltas['mean_diff_size_delta'] = baseline['mean_diff_size'] - current['mean_diff_size']

        # For rates, lower is better
        deltas['revert_rate_delta'] = baseline['revert_rate'] - current['revert_rate']
        deltas['flake_rate_delta'] = baseline['flake_rate'] - current['flake_rate']

        # For latency, lower is better
        deltas['p95_latency_delta'] = baseline['p95_latency_ms'] - current['p95_latency_ms']

        return deltas

def load_historical_metrics(output_dir: Path, days: int = 7) -> List[RunMetrics]:
    """
    Load historical metrics from the last N days.

    Args:
        output_dir: Directory containing run summaries
        days: Number of days to look back

    Returns:
        List of RunMetrics
    """
    output_dir = Path(output_dir)
    cutoff = datetime.now().timestamp() - (days * 86400)

    metrics = []
    for run_file in sorted(output_dir.glob("run_*.json")):
        try:
            with open(run_file, 'r') as f:
                data = json.load(f)

            # Parse timestamp
            timestamp = datetime.fromisoformat(data['timestamp']).timestamp()

            if timestamp >= cutoff:
                # Reconstruct RunMetrics (without full task_metrics)
                run_metrics = RunMetrics(
                    run_id=data['run_id'],
                    timestamp=data['timestamp'],
                    duration_sec=data['duration_sec'],
                    pass_at_1=data['pass_at_1'],
                    pass_at_3=data['pass_at_3'],
                    repair_at_3=data['repair_at_3'],
                    mean_diff_size=data['mean_diff_size'],
                    median_diff_size=data['median_diff_size'],
                    total_files_changed=data['total_files_changed'],
                    revert_rate=data['revert_rate'],
                    flake_rate=data['flake_rate'],
                    mean_latency_ms=data['mean_latency_ms'],
                    p95_latency_ms=data['p95_latency_ms'],
                    p99_latency_ms=data['p99_latency_ms'],
                    tasks_total=data['tasks_total'],
                    tasks_succeeded=data['tasks_succeeded'],
                    tasks_failed=data['tasks_failed']
                )
                metrics.append(run_metrics)

        except Exception as e:
            print(f"Error loading {run_file}: {e}")

    return metrics

def compute_trend(metrics_list: List[RunMetrics], key: str) -> Optional[float]:
    """
    Compute trend (slope) for a metric over time.

    Args:
        metrics_list: List of RunMetrics sorted by time
        key: Metric key to analyze

    Returns:
        Slope (positive = improving over time)
    """
    if len(metrics_list) < 2:
        return None

    try:
        values = [getattr(m, key) for m in metrics_list]

        # Simple linear regression
        n = len(values)
        x = list(range(n))
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(values)

        numerator = sum((x[i] - mean_x) * (values[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        slope = numerator / denominator
        return slope

    except Exception as e:
        print(f"Error computing trend for {key}: {e}")
        return None
