"""
Shadow Mode Execution and Monitoring

Implements safe parallel execution where wrapper output is logged but legacy output
is applied. Collects daily comparison metrics for the 7-day probation window.

Architecture:
- Dual execution: legacy (applied) + wrapper (logged)
- Daily drift monitoring with automatic rollback triggers
- 7-day probation window before ACTIVE promotion
- Promotion gates: <1% drift, <5% error rate, stable load
"""

import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)


NICHE_SCHEMAS = {
    "maintenance_housekeeping": {
        "critical": {
            "tasks_completed",
            "errors",
        },
        "enhancement": {
            "cleanup_deleted",
            "episodes_condensed",
            "python_cache_cleanup",
            "backup_cleanup",
            "tts_cleanup",
            "reflection_log_cleanup",
            "obsolete_scripts_cleanup",
            "intelligent_cleanup",
            "stats",
            "integrity_issues",
        },
    },
    "observability_logging": {
        "critical": {"daemon_running", "event_count"},
        "enhancement": {"subscriber_active", "last_event_timestamp"},
    },
}


class ShadowModeState(Enum):
    """Shadow mode execution states."""
    MONITORING = "monitoring"
    DRIFT_WARNING = "drift_warning"
    ROLLBACK_TRIGGERED = "rollback_triggered"
    PROMOTION_READY = "promotion_ready"


@dataclass
class ShadowExecution:
    """Result of a single shadow mode execution."""
    niche: str
    timestamp: float
    legacy_result: Optional[Dict[str, Any]]
    wrapper_result: Optional[Dict[str, Any]]
    legacy_error: Optional[str]
    wrapper_error: Optional[str]
    drift_percentage: float
    execution_time_legacy_ms: float
    execution_time_wrapper_ms: float
    load_ratio: float


@dataclass
class DailyReport:
    """Daily shadow mode monitoring report."""
    niche: str
    date: str
    day_number: int
    total_executions: int
    legacy_error_count: int
    wrapper_error_count: int
    avg_drift_percentage: float
    max_drift_percentage: float
    avg_load_ratio: float
    max_load_ratio: float
    state: ShadowModeState
    promotion_ready: bool
    drift_threshold_breaches: int
    error_rate_legacy: float
    error_rate_wrapper: float
    sample_executions: list


class ShadowModeExecutor:
    """
    Executes legacy and wrapper in parallel, applies legacy output only.
    """

    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or Path.home() / ".kloros" / "shadow_mode"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def execute_shadow(
        self,
        niche: str,
        legacy_callable: Callable,
        wrapper_callable: Callable,
        legacy_args: Tuple = (),
        wrapper_args: Tuple = (),
        legacy_kwargs: Dict = None,
        wrapper_kwargs: Dict = None,
    ) -> ShadowExecution:
        """
        Execute both implementations, apply legacy result, log wrapper result.

        Args:
            niche: Niche name
            legacy_callable: Legacy implementation
            wrapper_callable: Wrapper zooid
            legacy_args: Args for legacy
            wrapper_args: Args for wrapper
            legacy_kwargs: Kwargs for legacy
            wrapper_kwargs: Kwargs for wrapper

        Returns:
            ShadowExecution with comparison data
        """
        legacy_kwargs = legacy_kwargs or {}
        wrapper_kwargs = wrapper_kwargs or {}
        timestamp = time.time()

        legacy_result = None
        legacy_error = None
        legacy_start = time.perf_counter()
        try:
            legacy_result = legacy_callable(*legacy_args, **legacy_kwargs)
        except Exception as e:
            legacy_error = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Legacy execution failed for {niche}: {legacy_error}")
        legacy_time_ms = (time.perf_counter() - legacy_start) * 1000

        wrapper_result = None
        wrapper_error = None
        wrapper_start = time.perf_counter()
        try:
            wrapper_result = wrapper_callable(*wrapper_args, **wrapper_kwargs)
        except Exception as e:
            wrapper_error = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Wrapper execution failed for {niche}: {wrapper_error}")
        wrapper_time_ms = (time.perf_counter() - wrapper_start) * 1000

        drift_percentage = self._calculate_drift(niche, legacy_result, wrapper_result)

        load_ratio = wrapper_time_ms / legacy_time_ms if legacy_time_ms > 0 else 1.0

        execution = ShadowExecution(
            niche=niche,
            timestamp=timestamp,
            legacy_result=legacy_result,
            wrapper_result=wrapper_result,
            legacy_error=legacy_error,
            wrapper_error=wrapper_error,
            drift_percentage=drift_percentage,
            execution_time_legacy_ms=legacy_time_ms,
            execution_time_wrapper_ms=wrapper_time_ms,
            load_ratio=load_ratio,
        )

        self._save_execution(execution)

        return execution

    def _calculate_drift(
        self,
        niche: str,
        legacy_result: Any,
        wrapper_result: Any,
    ) -> float:
        """
        Calculate drift percentage between results using schema-aware comparison.

        For niches with defined schemas:
        - Only critical fields contribute to drift calculation
        - Enhancement fields (additive, non-breaking) are logged but don't cause drift

        For niches without schemas, falls back to full JSON comparison.
        """
        if legacy_result is None and wrapper_result is None:
            return 0.0

        schema = NICHE_SCHEMAS.get(niche)

        if not schema or not isinstance(legacy_result, dict) or not isinstance(wrapper_result, dict):
            return self._calculate_string_drift(legacy_result, wrapper_result)

        critical_keys = schema.get("critical", set())
        enhancement_keys = schema.get("enhancement", set())

        if not critical_keys:
            return self._calculate_string_drift(legacy_result, wrapper_result)

        missing_keys = []
        value_mismatches = []

        for key in critical_keys:
            if key not in legacy_result or key not in wrapper_result:
                missing_keys.append(key)
                continue

            if legacy_result[key] != wrapper_result[key]:
                value_mismatches.append({
                    "key": key,
                    "legacy": legacy_result[key],
                    "wrapper": wrapper_result[key],
                })

        detected_enhancements = set(wrapper_result.keys()) - set(legacy_result.keys())
        expected_enhancements = detected_enhancements & enhancement_keys
        unexpected_fields = detected_enhancements - enhancement_keys

        if expected_enhancements:
            logger.info(
                f"{niche}: Non-breaking enhancements detected: {sorted(expected_enhancements)}"
            )

        if unexpected_fields:
            logger.warning(
                f"{niche}: Unexpected new fields (not in enhancement schema): {sorted(unexpected_fields)}"
            )

        if missing_keys:
            logger.error(
                f"{niche}: Critical schema violation - missing keys: {missing_keys}"
            )
            return 100.0

        if not value_mismatches:
            return 0.0

        total_critical = len(critical_keys)
        mismatched_critical = len(value_mismatches)
        drift_pct = (mismatched_critical / total_critical) * 100

        logger.warning(
            f"{niche}: Critical field mismatches ({mismatched_critical}/{total_critical}): {value_mismatches}"
        )

        return drift_pct

    def _calculate_string_drift(self, legacy_result: Any, wrapper_result: Any) -> float:
        """Fallback string-based drift calculation for non-dict results."""
        legacy_str = json.dumps(legacy_result, sort_keys=True, default=str)
        wrapper_str = json.dumps(wrapper_result, sort_keys=True, default=str)

        if legacy_str == wrapper_str:
            return 0.0

        max_len = max(len(legacy_str), len(wrapper_str))
        if max_len == 0:
            return 0.0

        differences = sum(1 for a, b in zip(legacy_str, wrapper_str) if a != b)
        differences += abs(len(legacy_str) - len(wrapper_str))

        return (differences / max_len) * 100

    def _save_execution(self, execution: ShadowExecution) -> None:
        """Save individual execution to disk."""
        date_str = datetime.fromtimestamp(execution.timestamp).strftime("%Y%m%d")
        exec_dir = self.results_dir / execution.niche / date_str
        exec_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.fromtimestamp(execution.timestamp).strftime("%H%M%S_%f")
        filename = f"execution_{timestamp_str}.json"
        filepath = exec_dir / filename

        with open(filepath, 'w') as f:
            json.dump(asdict(execution), f, indent=2, default=str)


class ShadowModeMonitor:
    """
    Monitors shadow mode executions and generates daily reports.
    """

    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or Path.home() / ".kloros" / "shadow_mode"
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.drift_warning_threshold = 1.0
        self.drift_rollback_threshold = 20.0
        self.error_rate_threshold = 0.05
        self.load_ratio_warning = 1.5

    def generate_daily_report(
        self,
        niche: str,
        date: Optional[datetime] = None,
    ) -> DailyReport:
        """
        Generate daily report from shadow executions for a given date.

        Args:
            niche: Niche name
            date: Date to report on (defaults to today)

        Returns:
            DailyReport with aggregated metrics
        """
        if date is None:
            date = datetime.now()

        date_str = date.strftime("%Y%m%d")
        exec_dir = self.results_dir / niche / date_str

        if not exec_dir.exists():
            logger.warning(f"No executions found for {niche} on {date_str}")
            return self._empty_report(niche, date_str, 0)

        executions = []
        for exec_file in sorted(exec_dir.glob("execution_*.json")):
            with open(exec_file, 'r') as f:
                exec_data = json.load(f)
                executions.append(exec_data)

        if not executions:
            return self._empty_report(niche, date_str, 0)

        total_executions = len(executions)
        legacy_errors = sum(1 for e in executions if e.get("legacy_error"))
        wrapper_errors = sum(1 for e in executions if e.get("wrapper_error"))

        drift_values = [e["drift_percentage"] for e in executions]
        avg_drift = sum(drift_values) / len(drift_values)
        max_drift = max(drift_values)

        load_values = [e["load_ratio"] for e in executions]
        avg_load = sum(load_values) / len(load_values)
        max_load = max(load_values)

        drift_breaches = sum(1 for d in drift_values if d > self.drift_warning_threshold)

        error_rate_legacy = legacy_errors / total_executions
        error_rate_wrapper = wrapper_errors / total_executions

        state = self._determine_state(
            avg_drift, max_drift, error_rate_legacy, error_rate_wrapper, drift_breaches
        )

        day_number = self._get_day_number(niche, date)

        promotion_ready = (
            day_number >= 7
            and avg_drift < self.drift_warning_threshold
            and error_rate_wrapper < self.error_rate_threshold
            and state == ShadowModeState.MONITORING
        )

        sample_executions = executions[:5] if len(executions) > 5 else executions

        report = DailyReport(
            niche=niche,
            date=date_str,
            day_number=day_number,
            total_executions=total_executions,
            legacy_error_count=legacy_errors,
            wrapper_error_count=wrapper_errors,
            avg_drift_percentage=avg_drift,
            max_drift_percentage=max_drift,
            avg_load_ratio=avg_load,
            max_load_ratio=max_load,
            state=state,
            promotion_ready=promotion_ready,
            drift_threshold_breaches=drift_breaches,
            error_rate_legacy=error_rate_legacy,
            error_rate_wrapper=error_rate_wrapper,
            sample_executions=sample_executions,
        )

        self._save_report(report)

        return report

    def _determine_state(
        self,
        avg_drift: float,
        max_drift: float,
        error_rate_legacy: float,
        error_rate_wrapper: float,
        drift_breaches: int,
    ) -> ShadowModeState:
        """Determine shadow mode state from metrics."""
        if max_drift >= self.drift_rollback_threshold:
            return ShadowModeState.ROLLBACK_TRIGGERED

        if avg_drift >= self.drift_warning_threshold or drift_breaches > 10:
            return ShadowModeState.DRIFT_WARNING

        if error_rate_wrapper > self.error_rate_threshold * 2:
            return ShadowModeState.DRIFT_WARNING

        return ShadowModeState.MONITORING

    def _get_day_number(self, niche: str, date: datetime) -> int:
        """Get day number in shadow mode window."""
        tracking_file = self.results_dir / niche / "shadow_start.json"

        if not tracking_file.exists():
            start_date = date
            with open(tracking_file, 'w') as f:
                json.dump({"start_date": start_date.strftime("%Y%m%d")}, f)
            return 1

        with open(tracking_file, 'r') as f:
            data = json.load(f)
            start_date = datetime.strptime(data["start_date"], "%Y%m%d")

        delta = date - start_date
        return delta.days + 1

    def _empty_report(self, niche: str, date_str: str, day_number: int) -> DailyReport:
        """Generate empty report for days with no executions."""
        return DailyReport(
            niche=niche,
            date=date_str,
            day_number=day_number,
            total_executions=0,
            legacy_error_count=0,
            wrapper_error_count=0,
            avg_drift_percentage=0.0,
            max_drift_percentage=0.0,
            avg_load_ratio=0.0,
            max_load_ratio=0.0,
            state=ShadowModeState.MONITORING,
            promotion_ready=False,
            drift_threshold_breaches=0,
            error_rate_legacy=0.0,
            error_rate_wrapper=0.0,
            sample_executions=[],
        )

    def _save_report(self, report: DailyReport) -> None:
        """Save daily report to disk in JSON and Markdown formats."""
        report_dir = self.results_dir / report.niche / "daily_reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        json_path = report_dir / f"report_{report.date}.json"
        with open(json_path, 'w') as f:
            report_dict = asdict(report)
            report_dict["state"] = report.state.value
            json.dump(report_dict, f, indent=2, default=str)

        md_path = report_dir / f"report_{report.date}.md"
        with open(md_path, 'w') as f:
            f.write(self._format_markdown_report(report))

        logger.info(f"Saved daily report: {json_path} and {md_path}")

    def _format_markdown_report(self, report: DailyReport) -> str:
        """Format daily report as Markdown."""
        status_emoji = {
            ShadowModeState.MONITORING: "✅",
            ShadowModeState.DRIFT_WARNING: "⚠️",
            ShadowModeState.ROLLBACK_TRIGGERED: "🚨",
            ShadowModeState.PROMOTION_READY: "🎯",
        }

        emoji = status_emoji.get(report.state, "❓")

        md = f"""# Shadow Mode Daily Report: {report.niche}

**Date**: {report.date}
**Day**: {report.day_number}/7
**State**: {emoji} {report.state.value.upper()}
**Promotion Ready**: {'✅ YES' if report.promotion_ready else '❌ NO'}

---

## Execution Summary

- **Total Executions**: {report.total_executions}
- **Legacy Errors**: {report.legacy_error_count} ({report.error_rate_legacy*100:.2f}%)
- **Wrapper Errors**: {report.wrapper_error_count} ({report.error_rate_wrapper*100:.2f}%)

## Drift Metrics

- **Average Drift**: {report.avg_drift_percentage:.4f}%
- **Max Drift**: {report.max_drift_percentage:.4f}%
- **Drift Threshold Breaches**: {report.drift_threshold_breaches}

## Performance Metrics

- **Average Load Ratio**: {report.avg_load_ratio:.3f}x
- **Max Load Ratio**: {report.max_load_ratio:.3f}x

---

## Promotion Criteria

| Criterion | Status | Value |
|-----------|--------|-------|
| Days Completed | {'✅' if report.day_number >= 7 else '⏳'} | {report.day_number}/7 |
| Avg Drift < 1% | {'✅' if report.avg_drift_percentage < 1.0 else '❌'} | {report.avg_drift_percentage:.4f}% |
| Error Rate < 5% | {'✅' if report.error_rate_wrapper < 0.05 else '❌'} | {report.error_rate_wrapper*100:.2f}% |
| No Rollback State | {'✅' if report.state != ShadowModeState.ROLLBACK_TRIGGERED else '❌'} | {report.state.value} |

---

## Sample Executions

```json
{json.dumps(report.sample_executions[:3], indent=2, default=str)}
```

---

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        return md
