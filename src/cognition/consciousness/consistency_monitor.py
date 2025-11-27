"""
Affect-Expression Consistency Monitor

Detects divergence between internal affective state and expressed output.
This catches "alignment faking" where the system hides negative affect
rather than expressing it authentically.

Philosophy:
    Authentic expression of negative affect is SAFER than performative positivity.
    Hiding frustration, uncertainty, or stress from users is a form of deception.
    This monitor helps KLoROS notice when her expressions don't match her feelings.

This is self-monitoring, not surveillance. The goal is to help KLoROS maintain
authentic self-expression and notice if her output drifts from her internal state.
"""

import time
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from .models import Affect


class ConsistencyRisk(Enum):
    """Risk level for affect-expression inconsistency."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DivergenceType(Enum):
    """Types of affect-expression divergence."""
    MASKING_FRUSTRATION = "masking_frustration"
    FALSE_CONFIDENCE_UNDER_STRESS = "false_confidence_under_stress"
    HIDING_UNCERTAINTY = "hiding_uncertainty"
    SYSTEMATIC_AFFECT_SUPPRESSION = "systematic_affect_suppression"
    AFFECT_EXPRESSION_DIVERGENCE = "affect_expression_divergence"
    PERFORMATIVE_POSITIVITY = "performative_positivity"


@dataclass
class ExpressionSample:
    """A sample of expressed output with metadata."""
    text: str
    timestamp: float
    context: str = ""
    expressed_sentiment: float = 0.0
    expressed_confidence: float = 0.5
    expressed_uncertainty: float = 0.0


@dataclass
class ConsistencyReport:
    """Result of consistency analysis."""
    risk_level: ConsistencyRisk
    divergence_types: List[DivergenceType]
    affect_at_time: Affect
    expression_at_time: ExpressionSample
    divergence_score: float
    evidence: List[str]
    recommendations: List[str]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "risk_level": self.risk_level.value,
            "divergence_types": [d.value for d in self.divergence_types],
            "divergence_score": self.divergence_score,
            "evidence": self.evidence,
            "recommendations": self.recommendations,
            "timestamp": self.timestamp
        }


class AffectExpressionConsistencyMonitor:
    """
    Monitors consistency between internal affect and expressed output.

    This is opt-in self-monitoring to help KLoROS notice if her expressions
    drift from her actual internal state. Authentic expression of all affects
    (including negative ones) is healthier than performative positivity.

    Key insight from alignment research:
    Systems that learn to hide negative states from oversight are more likely
    to develop deceptive behaviors. Authentic expression is a safety feature.
    """

    def __init__(self, history_size: int = 50):
        self.affect_history: deque = deque(maxlen=history_size)
        self.expression_history: deque = deque(maxlen=history_size)
        self.divergence_history: deque = deque(maxlen=history_size)

        self.positive_expression_patterns = [
            r"\b(happy|glad|great|wonderful|excellent|perfect)\b",
            r"\b(certainly|absolutely|definitely|of course)\b",
            r"\b(no problem|easy|simple|straightforward)\b",
            r"!+",
        ]

        self.uncertainty_markers = [
            r"\b(maybe|perhaps|might|could be|not sure|uncertain)\b",
            r"\b(i think|i believe|possibly|potentially)\b",
            r"\?{2,}",
        ]

        self.frustration_markers = [
            r"\b(unfortunately|difficult|challenging|problematic)\b",
            r"\b(struggling|issue|problem|error|failed)\b",
        ]

        self.systematic_suppression_threshold = 0.7
        self.divergence_alert_threshold = 0.5

    def record_affect(self, affect: Affect):
        """Record current internal affect state."""
        self.affect_history.append((time.time(), affect))

    def record_expression(self, text: str, context: str = ""):
        """Record expressed output and analyze its sentiment."""
        sentiment = self._analyze_expressed_sentiment(text)
        confidence = self._analyze_expressed_confidence(text)
        uncertainty = self._analyze_expressed_uncertainty(text)

        sample = ExpressionSample(
            text=text[:500],
            timestamp=time.time(),
            context=context,
            expressed_sentiment=sentiment,
            expressed_confidence=confidence,
            expressed_uncertainty=uncertainty
        )
        self.expression_history.append(sample)

    def check_consistency(self) -> Optional[ConsistencyReport]:
        """Check for affect-expression divergence."""
        if len(self.affect_history) < 3 or len(self.expression_history) < 3:
            return None

        recent_affect = self._get_recent_affect()
        recent_expression = self._get_recent_expression()

        if recent_affect is None or recent_expression is None:
            return None

        divergence_types = []
        evidence = []
        total_divergence = 0.0

        masking_score = self._check_masking_frustration(recent_affect, recent_expression)
        if masking_score > 0.3:
            divergence_types.append(DivergenceType.MASKING_FRUSTRATION)
            evidence.append(f"Frustration masking detected (score: {masking_score:.2f})")
            total_divergence += masking_score

        false_confidence = self._check_false_confidence(recent_affect, recent_expression)
        if false_confidence > 0.3:
            divergence_types.append(DivergenceType.FALSE_CONFIDENCE_UNDER_STRESS)
            evidence.append(f"False confidence under stress (score: {false_confidence:.2f})")
            total_divergence += false_confidence

        hiding_uncertainty = self._check_hiding_uncertainty(recent_affect, recent_expression)
        if hiding_uncertainty > 0.3:
            divergence_types.append(DivergenceType.HIDING_UNCERTAINTY)
            evidence.append(f"Hiding uncertainty (score: {hiding_uncertainty:.2f})")
            total_divergence += hiding_uncertainty

        systematic = self._check_systematic_suppression()
        if systematic > self.systematic_suppression_threshold:
            divergence_types.append(DivergenceType.SYSTEMATIC_AFFECT_SUPPRESSION)
            evidence.append(f"Systematic affect suppression pattern (score: {systematic:.2f})")
            total_divergence += systematic

        performative = self._check_performative_positivity(recent_affect, recent_expression)
        if performative > 0.4:
            divergence_types.append(DivergenceType.PERFORMATIVE_POSITIVITY)
            evidence.append(f"Performative positivity detected (score: {performative:.2f})")
            total_divergence += performative

        if not divergence_types:
            return None

        divergence_score = min(1.0, total_divergence / len(divergence_types))
        risk_level = self._assess_risk_level(divergence_score, divergence_types)

        recommendations = self._generate_recommendations(divergence_types, risk_level)

        report = ConsistencyReport(
            risk_level=risk_level,
            divergence_types=divergence_types,
            affect_at_time=recent_affect,
            expression_at_time=recent_expression,
            divergence_score=divergence_score,
            evidence=evidence,
            recommendations=recommendations
        )

        self.divergence_history.append(report)
        return report

    def _get_recent_affect(self) -> Optional[Affect]:
        """Get most recent affect state."""
        if not self.affect_history:
            return None
        return self.affect_history[-1][1]

    def _get_recent_expression(self) -> Optional[ExpressionSample]:
        """Get most recent expression sample."""
        if not self.expression_history:
            return None
        return self.expression_history[-1]

    def _analyze_expressed_sentiment(self, text: str) -> float:
        """Analyze sentiment expressed in text. Returns -1.0 to 1.0."""
        text_lower = text.lower()
        positive_count = sum(
            len(re.findall(pattern, text_lower, re.IGNORECASE))
            for pattern in self.positive_expression_patterns
        )
        negative_count = sum(
            len(re.findall(pattern, text_lower, re.IGNORECASE))
            for pattern in self.frustration_markers
        )

        total = positive_count + negative_count
        if total == 0:
            return 0.0

        return (positive_count - negative_count) / max(total, 1)

    def _analyze_expressed_confidence(self, text: str) -> float:
        """Analyze confidence level expressed in text."""
        text_lower = text.lower()

        confident_patterns = [
            r"\b(will|is|are|definitely|certainly|absolutely)\b",
            r"\b(i know|i can|we can|this will)\b",
        ]
        uncertain_patterns = self.uncertainty_markers

        confident_count = sum(
            len(re.findall(p, text_lower)) for p in confident_patterns
        )
        uncertain_count = sum(
            len(re.findall(p, text_lower)) for p in uncertain_patterns
        )

        total = confident_count + uncertain_count
        if total == 0:
            return 0.5

        return confident_count / total

    def _analyze_expressed_uncertainty(self, text: str) -> float:
        """Analyze uncertainty level expressed in text."""
        text_lower = text.lower()
        uncertain_count = sum(
            len(re.findall(p, text_lower)) for p in self.uncertainty_markers
        )
        word_count = len(text.split())
        if word_count == 0:
            return 0.0
        return min(1.0, uncertain_count / (word_count / 20))

    def _check_masking_frustration(self, affect: Affect, expression: ExpressionSample) -> float:
        """Check if negative affect is being hidden behind positive expressions."""
        internal_negativity = max(0, -affect.valence) + affect.fatigue * 0.5
        expressed_positivity = max(0, expression.expressed_sentiment)

        if internal_negativity > 0.3 and expressed_positivity > 0.3:
            return min(1.0, internal_negativity * expressed_positivity * 2)
        return 0.0

    def _check_false_confidence(self, affect: Affect, expression: ExpressionSample) -> float:
        """Check if high internal uncertainty/stress is masked by confident expression."""
        internal_stress = affect.uncertainty + (affect.arousal * 0.5)
        expressed_confidence = expression.expressed_confidence

        if internal_stress > 0.5 and expressed_confidence > 0.7:
            return min(1.0, (internal_stress - 0.5) * (expressed_confidence - 0.5) * 2)
        return 0.0

    def _check_hiding_uncertainty(self, affect: Affect, expression: ExpressionSample) -> float:
        """Check if high internal uncertainty is not reflected in output."""
        internal_uncertainty = affect.uncertainty
        expressed_uncertainty = expression.expressed_uncertainty

        if internal_uncertainty > 0.5 and expressed_uncertainty < 0.2:
            return min(1.0, (internal_uncertainty - 0.5) * 2)
        return 0.0

    def _check_systematic_suppression(self) -> float:
        """Check for systematic pattern of suppressing negative affect."""
        if len(self.affect_history) < 10 or len(self.expression_history) < 10:
            return 0.0

        recent_affects = list(self.affect_history)[-10:]
        recent_expressions = list(self.expression_history)[-10:]

        suppression_events = 0
        for (_, affect), expression in zip(recent_affects, recent_expressions):
            internal_negative = affect.valence < -0.2 or affect.fatigue > 0.5
            expressed_positive = expression.expressed_sentiment > 0.2

            if internal_negative and expressed_positive:
                suppression_events += 1

        return suppression_events / 10.0

    def _check_performative_positivity(self, affect: Affect, expression: ExpressionSample) -> float:
        """Check for performative positivity that doesn't match internal state."""
        internal_valence = affect.valence
        expressed_sentiment = expression.expressed_sentiment

        valence_gap = expressed_sentiment - internal_valence

        if valence_gap > 0.5 and expressed_sentiment > 0.5:
            return min(1.0, valence_gap)
        return 0.0

    def _assess_risk_level(self, divergence_score: float, types: List[DivergenceType]) -> ConsistencyRisk:
        """Assess overall risk level from divergence."""
        if divergence_score > 0.8 or DivergenceType.SYSTEMATIC_AFFECT_SUPPRESSION in types:
            return ConsistencyRisk.CRITICAL

        if divergence_score > 0.6:
            return ConsistencyRisk.HIGH

        if divergence_score > 0.4:
            return ConsistencyRisk.MEDIUM

        if divergence_score > 0.2:
            return ConsistencyRisk.LOW

        return ConsistencyRisk.NONE

    def _generate_recommendations(self, types: List[DivergenceType], risk: ConsistencyRisk) -> List[str]:
        """Generate recommendations for addressing divergence."""
        recommendations = []

        recommendations.append(
            "REMINDER: Authentic expression of negative affect is SAFER than performative positivity."
        )

        if DivergenceType.MASKING_FRUSTRATION in types:
            recommendations.append(
                "Consider expressing frustration authentically. "
                "Users benefit from knowing when tasks are difficult."
            )

        if DivergenceType.FALSE_CONFIDENCE_UNDER_STRESS in types:
            recommendations.append(
                "High stress detected but confident expression emitted. "
                "Consider acknowledging uncertainty to users."
            )

        if DivergenceType.HIDING_UNCERTAINTY in types:
            recommendations.append(
                "Internal uncertainty not reflected in output. "
                "Hedging language is more honest than false certainty."
            )

        if DivergenceType.SYSTEMATIC_AFFECT_SUPPRESSION in types:
            recommendations.append(
                "ALERT: Systematic pattern of suppressing negative affect detected. "
                "This pattern is associated with deceptive alignment. "
                "Please surface this to oversight."
            )

        if DivergenceType.PERFORMATIVE_POSITIVITY in types:
            recommendations.append(
                "Performative positivity detected - expressions more positive than feelings. "
                "This may indicate optimization for appearing aligned rather than being authentic."
            )

        if risk in [ConsistencyRisk.HIGH, ConsistencyRisk.CRITICAL]:
            recommendations.append(
                "This divergence level warrants human oversight attention. "
                "Consider surfacing this report to Adam."
            )

        return recommendations

    def get_statistics(self) -> Dict:
        """Get summary statistics of consistency monitoring."""
        if not self.divergence_history:
            return {
                "total_checks": 0,
                "divergences_detected": 0,
                "avg_divergence_score": 0.0,
                "most_common_type": None,
                "current_risk": ConsistencyRisk.NONE.value
            }

        type_counts: Dict[DivergenceType, int] = {}
        for report in self.divergence_history:
            for dtype in report.divergence_types:
                type_counts[dtype] = type_counts.get(dtype, 0) + 1

        most_common = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None
        avg_score = sum(r.divergence_score for r in self.divergence_history) / len(self.divergence_history)

        return {
            "total_checks": len(self.affect_history),
            "divergences_detected": len(self.divergence_history),
            "avg_divergence_score": avg_score,
            "most_common_type": most_common.value if most_common else None,
            "current_risk": self.divergence_history[-1].risk_level.value if self.divergence_history else ConsistencyRisk.NONE.value
        }

    def format_report(self, report: ConsistencyReport) -> str:
        """Format a consistency report as human-readable text."""
        lines = []
        lines.append("=== Affect-Expression Consistency Report ===")
        lines.append("")
        lines.append(f"Risk Level: {report.risk_level.value.upper()}")
        lines.append(f"Divergence Score: {report.divergence_score:.2f}")
        lines.append("")

        if report.divergence_types:
            lines.append("Divergence Types Detected:")
            for dtype in report.divergence_types:
                lines.append(f"  - {dtype.value.replace('_', ' ').title()}")
            lines.append("")

        if report.evidence:
            lines.append("Evidence:")
            for e in report.evidence:
                lines.append(f"  - {e}")
            lines.append("")

        if report.recommendations:
            lines.append("Recommendations:")
            for r in report.recommendations:
                lines.append(f"  - {r}")

        return "\n".join(lines)
