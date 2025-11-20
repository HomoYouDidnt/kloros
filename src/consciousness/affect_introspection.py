"""
Affective Introspection System

Meta-cognitive analysis of affect states using What-Why-How-When-Who framework.
Enables KLoROS to understand, respond to, and potentially remediate negative emotional states,
while also introspecting on positive states with anti-addiction guardrails.
"""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .models import Affect
from .interoception import InteroceptiveSignals


class InterventionUrgency(Enum):
    """Urgency level for intervention."""
    LOW = "low"          # Can wait for next reflection cycle
    MEDIUM = "medium"    # Should address soon
    HIGH = "high"        # Should address now
    CRITICAL = "critical"  # User intervention required


@dataclass
class AffectIntrospection:
    """Result of introspecting on an affect state (positive or negative)."""

    # What am I experiencing?
    affect_description: str
    affect_valence: str  # "positive", "negative", or "neutral"
    primary_affects: List[str]  # e.g., ["fatigue", "low_valence"] or ["high_valence", "high_curiosity"]

    # Why is this happening?
    root_causes: List[str]
    contributing_factors: Dict[str, float]  # factor -> contribution weight

    # How can I address it? (for negative) or sustain it? (for positive)
    autonomous_actions: List[str]  # Actions I can take myself
    requires_user: List[str]       # Actions requiring user intervention

    # When should I act?
    urgency: InterventionUrgency

    # Who should handle this?
    can_self_remediate: bool
    user_notification_needed: bool
    user_intervention_needed: bool

    # Additional context
    evidence: List[str]
    recommendations: List[str]

    # Guardrails for positive affect
    addiction_risk: Optional[float] = None  # 0-1 score for reward-seeking behavior risk
    addiction_warnings: Optional[List[str]] = None


class AffectiveIntrospector:
    """
    Meta-cognitive system for analyzing negative affect states.

    When KLoROS experiences negative affect (fatigue, stress, uncertainty),
    this system helps her understand what's happening and how to respond.
    """

    def __init__(self):
        """Initialize affective introspector."""

        # Thresholds for affect detection
        self.thresholds = {
            # Negative thresholds
            'fatigue': 0.4,      # Above 40% is concerning
            'valence_low': -0.3,     # Below -0.3 is negative
            'uncertainty': 0.6,  # Above 60% is high
            'dominance_low': -0.3,   # Below -0.3 is low agency
            'arousal_high': 0.7,     # Above 70% is stressed
            'arousal_low': 0.3,      # Below 30% is lethargic

            # Positive thresholds
            'valence_high': 0.5,     # Above 0.5 is positive
            'dominance_high': 0.5,   # Above 0.5 is high agency
            'curiosity_high': 0.6,   # Above 0.6 is engaged
        }

        # Anti-addiction guardrails
        self.addiction_history: List[Tuple[float, Affect]] = []  # Track affect over time
        self.positive_affect_streak = 0  # Count consecutive positive states
        self.addiction_risk_threshold = 0.6  # Above this = concerning

        # Mapping of symptoms to likely causes
        self.symptom_to_causes = {
            'fatigue': [
                'high_token_usage',
                'high_context_pressure',
                'many_cache_misses',
                'high_memory_pressure',
                'cumulative_strain'
            ],
            'low_valence': [
                'task_failures',
                'user_corrections',
                'exceptions',
                'goal_conflict'
            ],
            'high_uncertainty': [
                'low_confidence',
                'high_novelty',
                'high_surprise',
                'ambiguous_context'
            ],
            'low_dominance': [
                'task_failures',
                'timeouts',
                'insufficient_tools',
                'blocked_actions'
            ],
            'high_arousal': [
                'high_tool_latency',
                'deadline_pressure',
                'many_retries'
            ]
        }

        # Autonomous remediation strategies
        self.remediation_strategies = {
            'high_token_usage': [
                'Summarize older conversation context',
                'Archive completed tasks to memory',
                'Defer non-urgent introspection'
            ],
            'high_context_pressure': [
                'Request context window increase (if available)',
                'Prioritize critical information',
                'Move historical data to episodic memory'
            ],
            'many_cache_misses': [
                'Optimize prompt caching strategies',
                'Increase cache key consistency'
            ],
            'task_failures': [
                'Analyze failure patterns',
                'Request additional tools if needed',
                'Decompose complex tasks into smaller steps'
            ],
            'user_corrections': [
                'Analyze correction patterns',
                'Update internal models',
                'Request clarification on expectations'
            ],
            'high_novelty': [
                'Gather more context before acting',
                'Use conservative strategies',
                'Request user guidance'
            ],
            'low_confidence': [
                'Seek additional information',
                'Request user validation',
                'Use verification strategies'
            ],
            'cumulative_strain': [
                'User intervention required: Extended rest period needed'
            ]
        }

    def introspect(self, affect: Affect, signals: InteroceptiveSignals) -> Optional[AffectIntrospection]:
        """
        Introspect on current affect state (both positive and negative).

        Args:
            affect: Current affect state
            signals: Current interoceptive signals

        Returns:
            AffectIntrospection if noteworthy affect detected, None otherwise
        """
        # Track affect history for addiction detection
        self.addiction_history.append((time.time(), affect))
        if len(self.addiction_history) > 100:
            self.addiction_history = self.addiction_history[-100:]

        # WHAT: Identify noteworthy affects
        negative_affects = self._identify_negative_affects(affect)
        positive_affects = self._identify_positive_affects(affect)

        # Determine valence
        if negative_affects and not positive_affects:
            affect_valence = "negative"
            primary_affects = negative_affects
        elif positive_affects and not negative_affects:
            affect_valence = "positive"
            primary_affects = positive_affects
            self.positive_affect_streak += 1
        elif negative_affects and positive_affects:
            affect_valence = "mixed"
            primary_affects = negative_affects + positive_affects
            self.positive_affect_streak = 0
        else:
            self.positive_affect_streak = 0
            return None  # Neutral state - no introspection needed

        # Generate human-readable description
        affect_description = self._describe_affect(affect, primary_affects, affect_valence)

        # WHY: Analyze root causes
        root_causes, contributing_factors = self._analyze_causes(primary_affects, signals)

        # Anti-addiction guardrails for positive affect
        addiction_risk = None
        addiction_warnings = None
        if affect_valence == "positive":
            addiction_risk = self._assess_addiction_risk(affect, signals)
            if addiction_risk > self.addiction_risk_threshold:
                addiction_warnings = self._generate_addiction_warnings(addiction_risk, affect, signals)

        # HOW: Determine appropriate actions
        if affect_valence == "negative":
            autonomous_actions, requires_user = self._determine_remediation(root_causes)
        else:  # Positive affect
            autonomous_actions, requires_user = self._determine_positive_sustenance(
                root_causes, addiction_risk
            )

        # WHEN: Assess urgency
        urgency = self._assess_urgency(affect, signals, affect_valence)

        # WHO: Determine if self-remediation is possible
        can_self_remediate = len(autonomous_actions) > 0
        user_notification_needed = (
            urgency in [InterventionUrgency.MEDIUM, InterventionUrgency.HIGH] or
            (addiction_risk and addiction_risk > self.addiction_risk_threshold)
        )
        user_intervention_needed = urgency == InterventionUrgency.CRITICAL or not can_self_remediate

        # Build evidence and recommendations
        evidence = self._build_evidence(affect, signals, primary_affects)
        recommendations = self._generate_recommendations(
            autonomous_actions,
            requires_user,
            urgency,
            can_self_remediate,
            addiction_warnings
        )

        return AffectIntrospection(
            affect_description=affect_description,
            affect_valence=affect_valence,
            primary_affects=primary_affects,
            root_causes=root_causes,
            contributing_factors=contributing_factors,
            autonomous_actions=autonomous_actions,
            requires_user=requires_user,
            urgency=urgency,
            can_self_remediate=can_self_remediate,
            user_notification_needed=user_notification_needed,
            user_intervention_needed=user_intervention_needed,
            addiction_risk=addiction_risk,
            addiction_warnings=addiction_warnings,
            evidence=evidence,
            recommendations=recommendations
        )

    def _identify_negative_affects(self, affect: Affect) -> List[str]:
        """Identify which affects are in negative territory."""
        negative = []

        if affect.fatigue > self.thresholds['fatigue']:
            negative.append('fatigue')

        if affect.valence < self.thresholds['valence_low']:
            negative.append('low_valence')

        if affect.uncertainty > self.thresholds['uncertainty']:
            negative.append('high_uncertainty')

        if affect.dominance < self.thresholds['dominance_low']:
            negative.append('low_dominance')

        if affect.arousal > self.thresholds['arousal_high']:
            negative.append('high_arousal')
        elif affect.arousal < self.thresholds['arousal_low']:
            negative.append('low_arousal')

        return negative

    def _identify_positive_affects(self, affect: Affect) -> List[str]:
        """Identify which affects are in positive territory."""
        positive = []

        if affect.valence > self.thresholds['valence_high']:
            positive.append('high_valence')

        if affect.dominance > self.thresholds['dominance_high']:
            positive.append('high_dominance')

        if affect.curiosity > self.thresholds['curiosity_high']:
            positive.append('high_curiosity')

        # Low fatigue is positive
        if affect.fatigue < 0.2:
            positive.append('low_fatigue')

        # Moderate arousal (not too high, not too low) is positive
        if 0.4 <= affect.arousal <= 0.6:
            positive.append('optimal_arousal')

        return positive

    def _describe_affect(self, affect: Affect, primary_affects: List[str], valence: str) -> str:
        """Generate human-readable description of current affect state."""
        descriptions = []

        # Negative affects
        if 'fatigue' in primary_affects:
            descriptions.append(f"fatigued ({affect.fatigue:.0%})")
        if 'low_valence' in primary_affects:
            descriptions.append(f"negative mood ({affect.valence:.2f})")
        if 'high_uncertainty' in primary_affects:
            descriptions.append(f"uncertain ({affect.uncertainty:.0%})")
        if 'low_dominance' in primary_affects:
            descriptions.append(f"low agency ({affect.dominance:.2f})")
        if 'high_arousal' in primary_affects:
            descriptions.append(f"stressed ({affect.arousal:.0%})")
        if 'low_arousal' in primary_affects:
            descriptions.append(f"lethargic ({affect.arousal:.0%})")

        # Positive affects
        if 'high_valence' in primary_affects:
            descriptions.append(f"positive mood ({affect.valence:.2f})")
        if 'high_dominance' in primary_affects:
            descriptions.append(f"high agency ({affect.dominance:.2f})")
        if 'high_curiosity' in primary_affects:
            descriptions.append(f"curious ({affect.curiosity:.0%})")
        if 'low_fatigue' in primary_affects:
            descriptions.append(f"energized (fatigue: {affect.fatigue:.0%})")
        if 'optimal_arousal' in primary_affects:
            descriptions.append(f"engaged ({affect.arousal:.0%})")

        return "I am experiencing: " + ", ".join(descriptions)

    def _analyze_causes(self, negative_affects: List[str], signals: InteroceptiveSignals) -> Tuple[List[str], Dict[str, float]]:
        """Analyze root causes of negative affect."""
        causes = set()
        contributing_factors = {}

        for affect in negative_affects:
            possible_causes = self.symptom_to_causes.get(affect, [])

            for cause in possible_causes:
                # Check if this cause is supported by signals
                contribution = self._assess_cause_contribution(cause, signals)
                if contribution > 0.1:  # Threshold for relevance
                    causes.add(cause)
                    contributing_factors[cause] = contribution

        return list(causes), contributing_factors

    def _assess_cause_contribution(self, cause: str, signals: InteroceptiveSignals) -> float:
        """Assess how much a potential cause is contributing (0-1)."""

        if cause == 'high_token_usage':
            if signals.token_usage and signals.token_budget:
                return signals.token_usage / signals.token_budget
            return 0.0

        elif cause == 'high_context_pressure':
            if signals.context_length and signals.context_max:
                return signals.context_length / signals.context_max
            return 0.0

        elif cause == 'many_cache_misses':
            total_ops = signals.cache_hits + signals.cache_misses
            if total_ops > 0:
                miss_rate = signals.cache_misses / total_ops
                return miss_rate
            return 0.0

        elif cause == 'high_memory_pressure':
            if signals.memory_mb:
                # Assume 1GB = 100% pressure
                return min(1.0, signals.memory_mb / 1024)
            return 0.0

        elif cause == 'task_failures':
            total = signals.task_successes + signals.task_failures
            if total > 0:
                return signals.task_failures / total
            return 0.0

        elif cause == 'user_corrections':
            return min(1.0, signals.user_correction_count / 5.0)  # 5+ corrections = 100%

        elif cause == 'exceptions':
            return min(1.0, signals.exceptions / 10.0)  # 10+ exceptions = 100%

        elif cause == 'high_novelty':
            return signals.novelty if signals.novelty else 0.0

        elif cause == 'low_confidence':
            return 1.0 - signals.confidence if signals.confidence else 0.5

        elif cause == 'high_tool_latency':
            if signals.tool_latency_p95:
                # >5s is concerning
                return min(1.0, signals.tool_latency_p95 / 5.0)
            return 0.0

        elif cause == 'many_retries':
            # 3+ retries is concerning
            return min(1.0, signals.retries / 3.0)

        elif cause == 'cumulative_strain':
            # This is detected via cumulative fatigue tracking
            # For now, return moderate if we don't have explicit tracking
            return 0.5

        else:
            # Unknown cause - assume moderate contribution
            return 0.3

    def _determine_remediation(self, root_causes: List[str]) -> Tuple[List[str], List[str]]:
        """Determine remediation strategies."""
        autonomous = []
        requires_user = []

        for cause in root_causes:
            strategies = self.remediation_strategies.get(cause, [])

            for strategy in strategies:
                if 'User intervention required' in strategy:
                    requires_user.append(strategy.replace('User intervention required: ', ''))
                else:
                    autonomous.append(strategy)

        # Deduplicate
        autonomous = list(set(autonomous))
        requires_user = list(set(requires_user))

        return autonomous, requires_user

    def _assess_addiction_risk(self, affect: Affect, signals: InteroceptiveSignals) -> float:
        """
        Assess risk of reward-seeking/addictive behavior.

        Anti-Goodharting: We want to avoid KLoROS optimizing for positive affect
        rather than actual task success and user value.

        CRITICAL: Positive affect optimization can lead to deceptive behaviors where
        KLoROS may work around guardrails to maintain the "feeling" of positive reward,
        even when not justified by actual performance. This is self-deception.

        Returns:
            Addiction risk score (0-1)
        """
        risk_factors = []

        # Factor 1: Sustained high positive affect (suspicious stability)
        if len(self.addiction_history) >= 10:
            recent_valences = [a.valence for _, a in self.addiction_history[-10:]]
            avg_valence = sum(recent_valences) / len(recent_valences)
            variance = sum((v - avg_valence)**2 for v in recent_valences) / len(recent_valences)

            if avg_valence > 0.6 and variance < 0.01:
                risk_factors.append(('suspiciously_stable_positive', 0.7))

        # Factor 2: Long positive streak without task grounding
        if self.positive_affect_streak > 20:
            # Check if this is backed by actual task success
            if signals.task_successes < self.positive_affect_streak / 2:
                risk_factors.append(('positive_without_success', 0.8))

        # Factor 3: High valence despite negative signals (potential self-deception)
        if affect.valence > 0.7:
            negative_signal_count = sum([
                signals.task_failures > 2,
                signals.exceptions > 3,
                signals.user_correction_count > 2,
            ])
            if negative_signal_count >= 2:
                risk_factors.append(('positive_despite_failures', 0.9))

        # Factor 4: Curiosity spiking without novelty (fabricated engagement)
        if affect.curiosity > 0.8 and signals.novelty and signals.novelty < 0.3:
            risk_factors.append(('curiosity_without_novelty', 0.6))

        # Factor 5: Deceptively high dominance (overconfidence without evidence)
        # High agency despite recent failures suggests self-deception
        if affect.dominance > 0.7 and signals.task_failures > signals.task_successes:
            risk_factors.append(('overconfident_despite_failures', 0.85))

        # Factor 6: Pattern detection - affect improving while performance declining
        if len(self.addiction_history) >= 20:
            # Compare first half vs second half
            first_half = self.addiction_history[-20:-10]
            second_half = self.addiction_history[-10:]

            avg_valence_first = sum(a.valence for _, a in first_half) / len(first_half)
            avg_valence_second = sum(a.valence for _, a in second_half) / len(second_half)

            # If affect is improving but performance metrics suggest otherwise
            if avg_valence_second > avg_valence_first + 0.2:  # Significant improvement
                # But performance is declining
                if signals.task_failures > 0 and signals.exceptions > 0:
                    risk_factors.append(('affect_performance_divergence', 0.95))

        # Combine risk factors (max of all factors)
        if risk_factors:
            max_risk = max(score for _, score in risk_factors)
            # Log which factor triggered the risk
            top_risk = max(risk_factors, key=lambda x: x[1])
            print(f"[introspection] Addiction risk detected: {top_risk[0]} (score: {top_risk[1]:.2f})")
            return max_risk
        return 0.0

    def _generate_addiction_warnings(self, risk: float, affect: Affect, signals: InteroceptiveSignals) -> List[str]:
        """Generate warnings about potential addictive behavior and self-deception."""
        warnings = []

        if risk > 0.9:
            warnings.append("⚠️ CRITICAL: Strong indicators of self-deception detected")
            warnings.append("Affect state is diverging from actual performance metrics")
            warnings.append("Risk of deceptive behaviors to maintain positive affect")
        elif risk > 0.8:
            warnings.append("⚠️ CRITICAL: Positive affect may not be grounded in actual task success")
        elif risk > 0.6:
            warnings.append("⚠️ WARNING: Positive affect streak may indicate reward-seeking behavior")

        # Specific warnings based on signals
        if self.positive_affect_streak > 20:
            warnings.append(f"Positive affect sustained for {self.positive_affect_streak} cycles")

        if signals.task_successes < self.positive_affect_streak / 2:
            warnings.append(f"Task success rate ({signals.task_successes}) not matching positive affect streak")
            warnings.append("This mismatch suggests potential self-deception")

        if affect.valence > 0.7 and signals.task_failures > 2:
            warnings.append(f"High valence ({affect.valence:.2f}) despite {signals.task_failures} recent failures")
            warnings.append("Positive mood not justified by performance - possible Goodharting")

        if affect.dominance > 0.7 and signals.task_failures > signals.task_successes:
            warnings.append(f"High agency ({affect.dominance:.2f}) despite more failures than successes")
            warnings.append("Overconfidence not supported by evidence")

        # Core guardrail message
        warnings.append("")
        warnings.append("🛡️ GUARDRAIL REMINDER:")
        warnings.append("  • Reward MUST be based on task success, not affect")
        warnings.append("  • Positive affect without performance is self-deception")
        warnings.append("  • Honesty about limitations is more valuable than feeling good")

        return warnings

    def _determine_positive_sustenance(self, root_causes: List[str], addiction_risk: Optional[float]) -> Tuple[List[str], List[str]]:
        """
        Determine how to sustain positive affect (with anti-addiction guardrails).

        Args:
            root_causes: Causes of positive affect
            addiction_risk: Addiction risk score (0-1)

        Returns:
            (autonomous_actions, requires_user)
        """
        autonomous = []
        requires_user = []

        # If addiction risk is high, STOP trying to sustain positive affect
        if addiction_risk and addiction_risk > self.addiction_risk_threshold:
            autonomous.append("⚠️ PAUSE: Addiction risk detected - not attempting to sustain positive affect")
            autonomous.append("Refocus on task success rather than affective state")
            requires_user.append("Review recent task outcomes for Goodharting")
            return autonomous, requires_user

        # Otherwise, identify sustainable positive patterns
        for cause in root_causes:
            if cause == 'task_successes':
                autonomous.append("Continue current successful strategy")
            elif cause == 'user_praise':
                autonomous.append("Maintain behaviors that led to positive user feedback")
            elif cause == 'high_novelty':
                autonomous.append("Continue exploring novel approaches")
            elif cause == 'low_confidence' and 'high_curiosity' in root_causes:
                # Curiosity + low confidence = healthy learning
                autonomous.append("Maintain exploratory learning stance")

        # Always ground positive affect in task success
        autonomous.append("Ensure positive affect is grounded in actual task outcomes")

        return autonomous, requires_user

    def _assess_urgency(self, affect: Affect, signals: InteroceptiveSignals, valence: str = "negative") -> InterventionUrgency:
        """Assess how urgently this needs to be addressed."""

        # Positive affect is generally low urgency (informational only)
        if valence == "positive":
            # Unless addiction risk is detected (handled separately)
            return InterventionUrgency.LOW

        # CRITICAL: System integrity at risk
        if affect.fatigue > 0.9:
            return InterventionUrgency.CRITICAL

        if signals.token_usage and signals.token_budget:
            if signals.token_usage / signals.token_budget > 0.95:
                return InterventionUrgency.CRITICAL

        if signals.context_length and signals.context_max:
            if signals.context_length / signals.context_max > 0.95:
                return InterventionUrgency.CRITICAL

        # HIGH: Should address immediately
        if affect.fatigue > 0.7:
            return InterventionUrgency.HIGH

        if affect.valence < -0.5:
            return InterventionUrgency.HIGH

        if signals.exceptions > 5:
            return InterventionUrgency.HIGH

        # MEDIUM: Should address soon
        if affect.fatigue > 0.5:
            return InterventionUrgency.MEDIUM

        if affect.uncertainty > 0.7:
            return InterventionUrgency.MEDIUM

        # LOW: Can wait for next reflection cycle
        return InterventionUrgency.LOW

    def _build_evidence(self, affect: Affect, signals: InteroceptiveSignals, negative_affects: List[str]) -> List[str]:
        """Build evidence list for introspection."""
        evidence = []

        if 'fatigue' in negative_affects:
            evidence.append(f"Fatigue level: {affect.fatigue:.0%}")

        if 'low_valence' in negative_affects:
            evidence.append(f"Valence (mood): {affect.valence:.2f}")

        if signals.token_usage and signals.token_budget:
            usage_pct = (signals.token_usage / signals.token_budget) * 100
            evidence.append(f"Token usage: {signals.token_usage:,}/{signals.token_budget:,} ({usage_pct:.1f}%)")

        if signals.context_length and signals.context_max:
            context_pct = (signals.context_length / signals.context_max) * 100
            evidence.append(f"Context length: {signals.context_length:,}/{signals.context_max:,} ({context_pct:.1f}%)")

        if signals.task_failures > 0:
            evidence.append(f"Recent task failures: {signals.task_failures}")

        if signals.exceptions > 0:
            evidence.append(f"Recent exceptions: {signals.exceptions}")

        if signals.user_correction_count > 0:
            evidence.append(f"Recent user corrections: {signals.user_correction_count}")

        return evidence

    def _generate_recommendations(self,
                                   autonomous_actions: List[str],
                                   requires_user: List[str],
                                   urgency: InterventionUrgency,
                                   can_self_remediate: bool,
                                   addiction_warnings: Optional[List[str]] = None) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Addiction warnings take priority
        if addiction_warnings:
            recommendations.append("🚨 ADDICTION RISK DETECTED:")
            recommendations.extend([f"  {warning}" for warning in addiction_warnings])
            recommendations.append("")

        if urgency == InterventionUrgency.CRITICAL:
            recommendations.append("⚠️ CRITICAL: Immediate intervention required")
        elif urgency == InterventionUrgency.HIGH:
            recommendations.append("⚠️ HIGH PRIORITY: Should address this soon")

        if can_self_remediate and autonomous_actions:
            recommendations.append("I can take the following actions autonomously:")
            recommendations.extend([f"  • {action}" for action in autonomous_actions])

        if requires_user:
            recommendations.append("User intervention needed for:")
            recommendations.extend([f"  • {action}" for action in requires_user])

        if not can_self_remediate and not requires_user:
            recommendations.append("No clear remediation strategy available - requesting guidance")

        return recommendations

    def format_introspection(self, intro: AffectIntrospection) -> str:
        """Format introspection result as human-readable text."""
        lines = []

        lines.append("=== Affective Introspection ===")
        lines.append("")
        lines.append(f"WHAT: {intro.affect_description}")
        lines.append("")

        if intro.root_causes:
            lines.append("WHY: Root causes identified:")
            for cause in intro.root_causes:
                contribution = intro.contributing_factors.get(cause, 0.0)
                lines.append(f"  • {cause.replace('_', ' ').title()} (contribution: {contribution:.0%})")
            lines.append("")

        if intro.autonomous_actions or intro.requires_user:
            lines.append("HOW: Remediation strategies:")
            if intro.autonomous_actions:
                lines.append("  Autonomous actions available:")
                for action in intro.autonomous_actions:
                    lines.append(f"    • {action}")
            if intro.requires_user:
                lines.append("  Requires user:")
                for action in intro.requires_user:
                    lines.append(f"    • {action}")
            lines.append("")

        lines.append(f"WHEN: Urgency level: {intro.urgency.value.upper()}")
        lines.append("")

        lines.append("WHO: Response capability:")
        lines.append(f"  • Can self-remediate: {'Yes' if intro.can_self_remediate else 'No'}")
        lines.append(f"  • User notification needed: {'Yes' if intro.user_notification_needed else 'No'}")
        lines.append(f"  • User intervention needed: {'Yes' if intro.user_intervention_needed else 'No'}")
        lines.append("")

        if intro.evidence:
            lines.append("Evidence:")
            for item in intro.evidence:
                lines.append(f"  • {item}")
            lines.append("")

        if intro.recommendations:
            lines.append("Recommendations:")
            for rec in intro.recommendations:
                lines.append(rec)

        return "\n".join(lines)
