"""
Affective Reporting - Legible, Evidence-Based Status

This module generates functional, falsifiable reports of affective state.
NO role-playing or anthropomorphic embellishment - audit-ready transparency.

Based on GPT suggestions for Phase 2E.
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from .models import Affect
from .interoception import InteroceptiveSignals
from .modulation import PolicyChange


@dataclass
class AffectiveReport:
    """
    Complete affective state report with evidence.

    This is the canonical format for reporting internal state
    in a legible, falsifiable manner.
    """
    # Affect dimensions
    affect: Dict[str, float]

    # Evidence (must cite measured signals)
    evidence: List[str]

    # Policy changes (if any)
    policy_changes: List[str]

    # One-line gloss (functional, not anthropomorphic)
    summary: str

    # Timestamp
    timestamp: float

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class AffectiveReporter:
    """
    Generates legible, evidence-based affective reports.

    Enforces guardrails:
    1. Reports must cite measured signals (no confabulation)
    2. One-line summary must be functional, not emotional
    3. Policy changes must have clear rationale
    """

    def __init__(self, min_evidence_items: int = 1):
        """
        Initialize reporter.

        Args:
            min_evidence_items: Minimum evidence items required for report
        """
        self.min_evidence_items = min_evidence_items

    def generate_report(self,
                        affect: Affect,
                        evidence: List[str],
                        policy_changes: List[PolicyChange],
                        signals: Optional[InteroceptiveSignals] = None) -> AffectiveReport:
        """
        Generate complete affective report.

        Args:
            affect: Current affective state
            evidence: List of evidence strings
            policy_changes: Recent policy changes
            signals: Optional interoceptive signals for additional context

        Returns:
            AffectiveReport object
        """
        import time

        # Extract affect values
        affect_dict = {
            'valence': round(affect.valence, 2),
            'arousal': round(affect.arousal, 2),
            'dominance': round(affect.dominance, 2),
            'uncertainty': round(affect.uncertainty, 2),
            'fatigue': round(affect.fatigue, 2),
            'curiosity': round(affect.curiosity, 2)
        }

        # Format policy changes
        policy_change_strs = []
        for change in policy_changes[-5:]:  # Last 5 changes
            policy_change_strs.append(
                f"{change.parameter}: {change.old_value}→{change.new_value}"
            )

        # Generate one-line summary (functional, not emotional)
        summary = self._generate_summary(affect, evidence, policy_changes)

        # Create report
        report = AffectiveReport(
            affect=affect_dict,
            evidence=evidence,
            policy_changes=policy_change_strs,
            summary=summary,
            timestamp=time.time()
        )

        return report

    def _generate_summary(self,
                          affect: Affect,
                          evidence: List[str],
                          policy_changes: List[PolicyChange]) -> str:
        """
        Generate one-line functional summary.

        Format: "Condition X because Y; adjusting Z to W"

        Examples:
        - "High uncertainty due to novel context; enabling verification"
        - "Curiosity elevated from surprise; broadening search space"
        - "Fatigue from resource pressure; shortening responses"
        """
        # Identify dominant affect dimension
        dimensions = {
            'curiosity': affect.curiosity,
            'uncertainty': affect.uncertainty,
            'fatigue': affect.fatigue,
            'arousal': affect.arousal,
            'valence': abs(affect.valence),
            'dominance': abs(affect.dominance)
        }

        dominant_dim = max(dimensions, key=dimensions.get)
        dominant_value = dimensions[dominant_dim]

        # Only report if sufficiently strong
        if dominant_value < 0.5:
            return "Affective state nominal"

        # Build summary parts
        condition_part = self._describe_condition(dominant_dim, dominant_value)

        # Add evidence cause (if available)
        cause_part = ""
        if evidence:
            # Take first evidence item as primary cause
            cause_part = f" from {evidence[0]}"

        # Add action taken (if any)
        action_part = ""
        if policy_changes:
            latest_change = policy_changes[-1]
            action_part = f"; adjusting {latest_change.parameter}"

        return f"{condition_part}{cause_part}{action_part}"

    def _describe_condition(self, dimension: str, value: float) -> str:
        """Describe affective dimension in functional terms."""
        level = "elevated" if value > 0.7 else "increased"

        descriptions = {
            'curiosity': f"Curiosity {level}",
            'uncertainty': f"Uncertainty {level}",
            'fatigue': f"Fatigue {level}",
            'arousal': f"Arousal {level}",
            'valence': f"Valence {'positive' if value > 0 else 'negative'}",
            'dominance': f"Dominance {'high' if value > 0 else 'low'}"
        }

        return descriptions.get(dimension, f"{dimension} {level}")

    def generate_diagnostic_text(self, report: AffectiveReport) -> str:
        """
        Generate human-readable diagnostic text from report.

        Args:
            report: AffectiveReport object

        Returns:
            Formatted diagnostic string
        """
        lines = []

        lines.append("🧠 AFFECTIVE STATE REPORT")
        lines.append("=" * 60)

        # Summary
        lines.append(f"\nSummary: {report.summary}")

        # Affect dimensions
        lines.append("\nAffect Dimensions:")
        affect = report.affect
        for dim, value in affect.items():
            bar = "█" * int(abs(value) * 20)
            sign = "+" if value >= 0 else "-"
            lines.append(f"  {dim:12s} {sign}{abs(value):0.2f} {bar}")

        # Evidence
        if report.evidence:
            lines.append("\nEvidence:")
            for item in report.evidence:
                lines.append(f"  • {item}")
        else:
            lines.append("\nEvidence: [None - using baseline state]")

        # Policy changes
        if report.policy_changes:
            lines.append("\nPolicy Changes:")
            for change in report.policy_changes:
                lines.append(f"  → {change}")
        else:
            lines.append("\nPolicy Changes: [None]")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)

    def check_report_validity(self, report: AffectiveReport) -> tuple[bool, str]:
        """
        Validate report against guardrails.

        Args:
            report: AffectiveReport to validate

        Returns:
            (is_valid, error_message)
        """
        # Guardrail 1: Must have minimum evidence
        if len(report.evidence) < self.min_evidence_items:
            # Exception: allow if affect is near baseline
            affect_magnitude = sum(abs(v) for v in report.affect.values())
            if affect_magnitude > 2.0:  # Significant deviation from baseline
                return False, f"Insufficient evidence ({len(report.evidence)} items, need {self.min_evidence_items})"

        # Guardrail 2: Policy changes must have rationale
        # (Already enforced by PolicyChange dataclass requiring 'reason')

        # Guardrail 3: Affect values must be in valid ranges
        for dim, value in report.affect.items():
            if dim in ['valence', 'dominance']:
                if not -1.0 <= value <= 1.0:
                    return False, f"Invalid {dim} value: {value} (must be in [-1, 1])"
            else:
                if not 0.0 <= value <= 1.0:
                    return False, f"Invalid {dim} value: {value} (must be in [0, 1])"

        return True, ""

    def generate_json_report(self,
                             affect: Affect,
                             evidence: List[str],
                             policy_changes: List[PolicyChange],
                             signals: Optional[InteroceptiveSignals] = None) -> str:
        """
        Generate JSON report (for programmatic consumption).

        Args:
            affect: Current affective state
            evidence: List of evidence strings
            policy_changes: Recent policy changes
            signals: Optional interoceptive signals

        Returns:
            JSON string
        """
        report = self.generate_report(affect, evidence, policy_changes, signals)

        # Validate before returning
        is_valid, error = self.check_report_validity(report)
        if not is_valid:
            # Add validation warning to report
            report_dict = report.to_dict()
            report_dict['validation_warning'] = error
            return json.dumps(report_dict, indent=2)

        return report.to_json()

    def generate_compact_report(self, report: AffectiveReport) -> str:
        """
        Generate compact one-line report.

        Format: "Affect: [summary] | Val:{v} Aro:{a} Dom:{d} Unc:{u} Fat:{f} Cur:{c}"

        Args:
            report: AffectiveReport object

        Returns:
            Compact string
        """
        a = report.affect
        compact = (
            f"Affect: {report.summary} | "
            f"Val:{a['valence']:+.1f} Aro:{a['arousal']:+.1f} Dom:{a['dominance']:+.1f} "
            f"Unc:{a['uncertainty']:.1f} Fat:{a['fatigue']:.1f} Cur:{a['curiosity']:.1f}"
        )

        return compact


class ConfabulationFilter:
    """
    Prevents confabulation in affective reports.

    Ensures reports are grounded in actual measurements,
    not fabricated narratives.
    """

    def __init__(self):
        """Initialize confabulation filter."""
        self.required_signal_threshold = 0.1  # Minimum signal change to report

    def filter_evidence(self,
                        evidence: List[str],
                        signals: InteroceptiveSignals) -> List[str]:
        """
        Filter evidence to only include items grounded in measured signals.

        Args:
            evidence: Proposed evidence items
            signals: Actual measured signals

        Returns:
            Filtered evidence list
        """
        # For Phase 2, we trust the appraisal system to only generate
        # grounded evidence. Future: could add NLP checks here.
        return evidence

    def validate_affect_claim(self,
                               affect_dimension: str,
                               value: float,
                               signals: InteroceptiveSignals) -> bool:
        """
        Validate that an affect claim is grounded in signals.

        Args:
            affect_dimension: Which dimension is claimed
            value: Claimed value
            signals: Actual signals

        Returns:
            True if claim is grounded
        """
        # If affect is near baseline, no evidence needed
        if abs(value) < 0.3:
            return True

        # For strong claims, require some signal evidence
        # (Specific validation logic depends on dimension)

        return True  # Placeholder - trust appraisal formulas for now
