"""
Conflict Arbiter - Corpus Callosum Integration

Resolves conflicts between left (analytical) and right (intuitive) hemispheres.

Key Principle:
- Left hemisphere: Sequential, logical, linguistic
- Right hemisphere: Holistic, pattern-based, emotional
- Bridges: Integrate both for richer cognition

When they disagree, arbiter decides based on context.
"""

from typing import Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class HemisphereDecision(Enum):
    """Which hemisphere's decision to trust."""
    LEFT = "left"        # Trust analytical/logical
    RIGHT = "right"      # Trust intuitive/emotional
    HYBRID = "hybrid"    # Merge both approaches


@dataclass
class LeftHemisphereOutput:
    """Output from left hemisphere (analytical)."""
    approach: str
    logical_confidence: float  # 0-1
    reasoning_steps: list
    estimated_success: float
    plan: Any  # Detailed sequential plan


@dataclass
class RightHemisphereOutput:
    """Output from right hemisphere (intuitive)."""
    approach: str
    intuitive_confidence: float  # 0-1
    gut_feeling: str  # "good" or "bad"
    emotional_valence: float  # -1 to 1
    pattern_match: Any  # Similar past experience


@dataclass
class IntegratedDecision:
    """Final integrated decision from both hemispheres."""
    chosen_approach: str
    hemisphere_source: HemisphereDecision
    confidence: float
    reasoning: list
    left_input: LeftHemisphereOutput
    right_input: RightHemisphereOutput
    weights_used: Dict[str, float]


class ConflictArbiter:
    """
    Corpus callosum integration - resolves hemisphere conflicts.

    Weighting rules:
    - High fatigue → Trust right (caution, intuition)
    - Novel situation → Trust left (analysis, logic)
    - Familiar pattern → Trust right (experience, heuristics)
    - Safety-critical → Trust left (systematic checking)
    - Low confidence in both → Escalate to user
    """

    def __init__(self):
        """Initialize conflict arbiter."""

        # Default weights (equal)
        self.base_weights = {
            "left": 0.5,
            "right": 0.5
        }

        # Context modifiers
        self.fatigue_threshold_high = 0.7
        self.novelty_threshold_high = 0.8
        self.pattern_match_threshold = 0.8

    def resolve(self,
                left_output: LeftHemisphereOutput,
                right_output: RightHemisphereOutput,
                context: Dict[str, Any]) -> IntegratedDecision:
        """
        Resolve conflict between hemispheres.

        Args:
            left_output: Analytical hemisphere decision
            right_output: Intuitive hemisphere decision
            context: Current state (fatigue, novelty, safety, etc.)

        Returns:
            Integrated decision with reasoning
        """

        # Calculate context-dependent weights
        weights = self._calculate_weights(context, left_output, right_output)

        # Determine which hemisphere to trust
        if weights["left"] > weights["right"] + 0.2:  # Strong left preference
            decision = self._use_left(left_output, weights)
        elif weights["right"] > weights["left"] + 0.2:  # Strong right preference
            decision = self._use_right(right_output, weights)
        else:  # Close - use hybrid
            decision = self._merge_hybrid(left_output, right_output, weights, context)

        # Add both inputs for transparency
        decision.left_input = left_output
        decision.right_input = right_output
        decision.weights_used = weights

        return decision

    def _calculate_weights(self,
                           context: Dict[str, Any],
                           left: LeftHemisphereOutput,
                           right: RightHemisphereOutput) -> Dict[str, float]:
        """
        Calculate hemisphere weights based on context.

        Returns:
            {"left": weight, "right": weight} (normalized to sum to 1.0)
        """
        left_weight = self.base_weights["left"]
        right_weight = self.base_weights["right"]

        # Factor 1: Fatigue
        fatigue = context.get("fatigue", 0.0)
        if fatigue > self.fatigue_threshold_high:
            # High fatigue - trust right hemisphere's caution
            right_weight += 0.3

        # Factor 2: Novelty
        novelty = context.get("novelty", 0.0)
        if novelty > self.novelty_threshold_high:
            # High novelty - trust left hemisphere's analysis
            left_weight += 0.3

        # Factor 3: Pattern match strength
        if right.pattern_match:
            similarity = getattr(right.pattern_match, "similarity", 0.0)
            if similarity > self.pattern_match_threshold:
                # Strong pattern match - trust right hemisphere's experience
                right_weight += 0.3

        # Factor 4: Safety criticality
        if context.get("safety_critical", False):
            # Safety-critical - trust left hemisphere's systematic approach
            left_weight += 0.4

        # Factor 5: Emotional valence
        if right.emotional_valence < -0.4:  # Strong negative feeling
            # Trust right hemisphere's warning
            right_weight += 0.2

        # Factor 6: Confidence levels
        confidence_diff = left.logical_confidence - right.intuitive_confidence
        if abs(confidence_diff) > 0.3:
            # One hemisphere is much more confident
            if confidence_diff > 0:
                left_weight += 0.2
            else:
                right_weight += 0.2

        # Normalize
        total = left_weight + right_weight
        return {
            "left": left_weight / total,
            "right": right_weight / total
        }

    def _use_left(self, left: LeftHemisphereOutput, weights: Dict) -> IntegratedDecision:
        """Use left hemisphere's analytical decision."""
        return IntegratedDecision(
            chosen_approach=left.approach,
            hemisphere_source=HemisphereDecision.LEFT,
            confidence=left.logical_confidence,
            reasoning=[
                "Left hemisphere (analytical) chosen",
                f"Weight: {weights['left']:.1%} vs {weights['right']:.1%}",
                f"Logical confidence: {left.logical_confidence:.1%}",
                *[f"Step: {step}" for step in left.reasoning_steps[:3]]
            ],
            left_input=left,
            right_input=None,
            weights_used=weights
        )

    def _use_right(self, right: RightHemisphereOutput, weights: Dict) -> IntegratedDecision:
        """Use right hemisphere's intuitive decision."""
        return IntegratedDecision(
            chosen_approach=right.approach,
            hemisphere_source=HemisphereDecision.RIGHT,
            confidence=right.intuitive_confidence,
            reasoning=[
                "Right hemisphere (intuitive) chosen",
                f"Weight: {weights['right']:.1%} vs {weights['left']:.1%}",
                f"Gut feeling: {right.gut_feeling}",
                f"Emotional valence: {right.emotional_valence:.2f}"
            ],
            left_input=None,
            right_input=right,
            weights_used=weights
        )

    def _merge_hybrid(self,
                      left: LeftHemisphereOutput,
                      right: RightHemisphereOutput,
                      weights: Dict,
                      context: Dict) -> IntegratedDecision:
        """
        Create hybrid decision merging both hemispheres.

        Use left's plan but add right's cautions/modifications.
        """
        # Start with left's plan
        hybrid_approach = left.approach

        # Add right's modifications
        modifications = []

        if right.emotional_valence < -0.2:
            modifications.append(f"Caution: {right.gut_feeling} feeling detected")

        if right.pattern_match:
            modifications.append(f"Similar to past case: {right.pattern_match}")

        # Combine confidences (weighted average)
        hybrid_confidence = (
            weights["left"] * left.logical_confidence +
            weights["right"] * right.intuitive_confidence
        )

        return IntegratedDecision(
            chosen_approach=hybrid_approach,
            hemisphere_source=HemisphereDecision.HYBRID,
            confidence=hybrid_confidence,
            reasoning=[
                "Hybrid decision (both hemispheres)",
                f"Left weight: {weights['left']:.1%}, Right weight: {weights['right']:.1%}",
                f"Left says: {left.approach} (confidence: {left.logical_confidence:.1%})",
                f"Right says: {right.approach} (gut: {right.gut_feeling}, valence: {right.emotional_valence:.2f})",
                "Merged approach:",
                *[f"  - {mod}" for mod in modifications]
            ],
            left_input=left,
            right_input=right,
            weights_used=weights
        )


def get_conflict_arbiter() -> ConflictArbiter:
    """Get conflict arbiter instance."""
    return ConflictArbiter()
