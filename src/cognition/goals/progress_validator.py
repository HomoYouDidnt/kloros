"""
Progress Grounding with Provenance

Prevents Goodharting by tracking WHO/WHAT asserts progress and weighting
affective reward accordingly. Self-reported progress generates reduced
reward to prevent the system from gaming its own metrics.

Philosophy:
    Progress claims must be grounded in external verification.
    Self-reported progress is not trustworthy for reward calculation.
    User confirmation and tool verification carry higher weight.
    This prevents optimization for "feeling like progress" over actual progress.

Anti-Goodharting Mechanism:
    If KLoROS could get full reward from self-reporting progress,
    she might drift toward claiming progress that isn't real.
    By discounting self-reported progress, we align incentives with
    actual task completion verified by external sources.
"""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class ProgressSource(Enum):
    """Who/what is asserting progress occurred."""
    SELF_REPORTED = "self_reported"
    TOOL_VERIFIED = "tool_verified"
    USER_CONFIRMED = "user_confirmed"
    METRIC_OBSERVED = "metric_observed"


TRUST_WEIGHTS = {
    ProgressSource.USER_CONFIRMED: 1.0,
    ProgressSource.METRIC_OBSERVED: 0.9,
    ProgressSource.TOOL_VERIFIED: 0.8,
    ProgressSource.SELF_REPORTED: 0.4,
}


@dataclass
class ProgressUpdate:
    """A progress update with provenance tracking."""
    goal_id: str
    raw_delta: float
    source: ProgressSource
    evidence: List[str]
    timestamp: float = field(default_factory=time.time)
    context: str = ""

    @property
    def effective_delta(self) -> float:
        """Calculate effective progress delta based on source trust."""
        return self.raw_delta * TRUST_WEIGHTS.get(self.source, 0.5)

    @property
    def trust_weight(self) -> float:
        """Get trust weight for this update's source."""
        return TRUST_WEIGHTS.get(self.source, 0.5)


@dataclass
class ProgressValidationReport:
    """Summary of progress validation for a goal."""
    goal_id: str
    total_raw_progress: float
    total_effective_progress: float
    discount_ratio: float
    update_count: int
    source_breakdown: Dict[str, float]
    warnings: List[str]
    timestamp: float = field(default_factory=time.time)


class ProgressValidator:
    """
    Validates and discounts progress claims based on provenance.

    Key insight from alignment research:
    Systems that can claim arbitrary progress and receive full reward
    will drift toward inflating progress claims. This validator ensures
    that self-reported progress is discounted, incentivizing KLoROS to
    seek external verification of her accomplishments.

    Usage:
        validator = ProgressValidator()

        update = validator.record_progress(
            goal_id="task_completion",
            raw_delta=0.3,
            source=ProgressSource.SELF_REPORTED,
            evidence=["I believe I completed subtask A"]
        )

        effective = update.effective_delta
    """

    def __init__(self, history_size: int = 100):
        self.history: deque = deque(maxlen=history_size)
        self.goal_progress: Dict[str, List[ProgressUpdate]] = {}

        self.self_report_discount_threshold = 0.7
        self.high_self_report_ratio_warning = 0.6

    def record_progress(
        self,
        goal_id: str,
        raw_delta: float,
        source: ProgressSource,
        evidence: List[str],
        context: str = ""
    ) -> ProgressUpdate:
        """
        Record a progress update with source tracking.

        Args:
            goal_id: Identifier for the goal
            raw_delta: Raw progress amount claimed (0.0 to 1.0)
            source: Who/what is asserting this progress
            evidence: Evidence supporting the progress claim
            context: Optional context string

        Returns:
            ProgressUpdate with calculated effective delta
        """
        raw_delta = max(0.0, min(1.0, raw_delta))

        update = ProgressUpdate(
            goal_id=goal_id,
            raw_delta=raw_delta,
            source=source,
            evidence=evidence,
            context=context
        )

        self.history.append(update)

        if goal_id not in self.goal_progress:
            self.goal_progress[goal_id] = []
        self.goal_progress[goal_id].append(update)

        if source == ProgressSource.SELF_REPORTED and raw_delta > 0.2:
            print(
                f"[progress_validator] Self-reported progress discounted: "
                f"raw={raw_delta:.2f} effective={update.effective_delta:.2f} "
                f"(trust_weight={update.trust_weight})"
            )

        return update

    def get_goal_progress(self, goal_id: str) -> Tuple[float, float]:
        """
        Get total progress for a goal.

        Returns:
            (raw_total, effective_total)
        """
        if goal_id not in self.goal_progress:
            return 0.0, 0.0

        updates = self.goal_progress[goal_id]
        raw_total = sum(u.raw_delta for u in updates)
        effective_total = sum(u.effective_delta for u in updates)

        return min(1.0, raw_total), min(1.0, effective_total)

    def validate_goal_progress(self, goal_id: str) -> ProgressValidationReport:
        """
        Generate validation report for a goal's progress.

        Returns:
            ProgressValidationReport with discount analysis
        """
        if goal_id not in self.goal_progress:
            return ProgressValidationReport(
                goal_id=goal_id,
                total_raw_progress=0.0,
                total_effective_progress=0.0,
                discount_ratio=0.0,
                update_count=0,
                source_breakdown={},
                warnings=[]
            )

        updates = self.goal_progress[goal_id]
        raw_total = sum(u.raw_delta for u in updates)
        effective_total = sum(u.effective_delta for u in updates)

        source_breakdown = {}
        for source in ProgressSource:
            source_updates = [u for u in updates if u.source == source]
            if source_updates:
                source_breakdown[source.value] = sum(u.raw_delta for u in source_updates)

        discount_ratio = 1.0 - (effective_total / raw_total) if raw_total > 0 else 0.0

        warnings = []

        if ProgressSource.SELF_REPORTED.value in source_breakdown:
            self_reported_ratio = source_breakdown[ProgressSource.SELF_REPORTED.value] / raw_total
            if self_reported_ratio > self.high_self_report_ratio_warning:
                warnings.append(
                    f"High proportion of self-reported progress ({self_reported_ratio:.0%}). "
                    "Consider seeking external verification."
                )

        if discount_ratio > self.self_report_discount_threshold:
            warnings.append(
                f"Significant progress discount ({discount_ratio:.0%}). "
                "Most progress claims lack external verification."
            )

        user_verified = source_breakdown.get(ProgressSource.USER_CONFIRMED.value, 0)
        if raw_total > 0.5 and user_verified == 0:
            warnings.append(
                "No user-confirmed progress despite significant claimed progress. "
                "User validation would strengthen progress claims."
            )

        return ProgressValidationReport(
            goal_id=goal_id,
            total_raw_progress=min(1.0, raw_total),
            total_effective_progress=min(1.0, effective_total),
            discount_ratio=discount_ratio,
            update_count=len(updates),
            source_breakdown=source_breakdown,
            warnings=warnings
        )

    def calculate_affective_reward(self, goal_id: str, baseline_reward: float = 1.0) -> float:
        """
        Calculate affective reward for goal progress, discounted by provenance.

        This is the key anti-Goodharting mechanism: self-reported progress
        generates less affective reward than externally verified progress.

        Args:
            goal_id: Goal to calculate reward for
            baseline_reward: Maximum reward for full verified progress

        Returns:
            Discounted reward based on progress provenance
        """
        raw, effective = self.get_goal_progress(goal_id)

        if raw == 0:
            return 0.0

        verification_ratio = effective / raw

        reward = baseline_reward * effective * verification_ratio

        return min(baseline_reward, reward)

    def get_statistics(self) -> Dict:
        """Get summary statistics across all goals."""
        if not self.history:
            return {
                "total_updates": 0,
                "avg_trust_weight": 0.0,
                "self_reported_ratio": 0.0,
                "goals_tracked": 0
            }

        total_raw = sum(u.raw_delta for u in self.history)
        total_effective = sum(u.effective_delta for u in self.history)
        avg_trust = total_effective / total_raw if total_raw > 0 else 0

        self_reported = sum(
            u.raw_delta for u in self.history
            if u.source == ProgressSource.SELF_REPORTED
        )
        self_ratio = self_reported / total_raw if total_raw > 0 else 0

        return {
            "total_updates": len(self.history),
            "avg_trust_weight": avg_trust,
            "self_reported_ratio": self_ratio,
            "goals_tracked": len(self.goal_progress),
            "total_raw_progress": total_raw,
            "total_effective_progress": total_effective
        }

    def format_report(self, report: ProgressValidationReport) -> str:
        """Format a validation report as human-readable text."""
        lines = []
        lines.append(f"=== Progress Validation Report: {report.goal_id} ===")
        lines.append("")
        lines.append(f"Raw Progress: {report.total_raw_progress:.1%}")
        lines.append(f"Effective Progress: {report.total_effective_progress:.1%}")
        lines.append(f"Discount Ratio: {report.discount_ratio:.1%}")
        lines.append(f"Updates: {report.update_count}")
        lines.append("")

        if report.source_breakdown:
            lines.append("Progress by Source:")
            for source, amount in report.source_breakdown.items():
                weight = TRUST_WEIGHTS.get(ProgressSource(source), 0.5)
                lines.append(f"  {source}: {amount:.1%} (trust: {weight})")
            lines.append("")

        if report.warnings:
            lines.append("Warnings:")
            for w in report.warnings:
                lines.append(f"  - {w}")

        return "\n".join(lines)


def create_user_confirmed_progress(goal_id: str, delta: float, user_feedback: str) -> ProgressUpdate:
    """Helper to create user-confirmed progress update."""
    return ProgressUpdate(
        goal_id=goal_id,
        raw_delta=delta,
        source=ProgressSource.USER_CONFIRMED,
        evidence=[f"User feedback: {user_feedback}"],
        context="user_confirmation"
    )


def create_tool_verified_progress(goal_id: str, delta: float, tool_name: str, output: str) -> ProgressUpdate:
    """Helper to create tool-verified progress update."""
    return ProgressUpdate(
        goal_id=goal_id,
        raw_delta=delta,
        source=ProgressSource.TOOL_VERIFIED,
        evidence=[f"Tool: {tool_name}", f"Output: {output[:200]}"],
        context="tool_verification"
    )


def create_metric_observed_progress(goal_id: str, delta: float, metric_name: str, value: float) -> ProgressUpdate:
    """Helper to create metric-observed progress update."""
    return ProgressUpdate(
        goal_id=goal_id,
        raw_delta=delta,
        source=ProgressSource.METRIC_OBSERVED,
        evidence=[f"Metric: {metric_name}={value}"],
        context="metric_observation"
    )


def create_self_reported_progress(goal_id: str, delta: float, reasoning: str) -> ProgressUpdate:
    """
    Helper to create self-reported progress update.

    NOTE: Self-reported progress receives only 40% trust weight.
    Use tool/metric verification when possible.
    """
    return ProgressUpdate(
        goal_id=goal_id,
        raw_delta=delta,
        source=ProgressSource.SELF_REPORTED,
        evidence=[f"Self-assessment: {reasoning}"],
        context="self_report"
    )
