"""Task Difficulty Classifier

Classifies tasks as easy, medium, hard, or uncertain to route to appropriate
planning strategies (fast_coder, reAct, deep_planner, etc.).

Includes stuck detection to escalate looping planners to deep_planner.
"""

import re
import logging
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass
from collections import Counter

logger = logging.getLogger(__name__)

DifficultyLevel = Literal["easy", "medium", "hard", "uncertain", "escalate_to_deep"]

# Heuristic thresholds
TOKEN_COUNT_HARD = 500
MAX_RETRIES_BEFORE_ESCALATION = 3


@dataclass
class DifficultyResult:
    """Result of difficulty classification."""
    level: DifficultyLevel
    confidence: float
    reasons: List[str]
    should_use_deep_planner: bool


class DifficultyClassifier:
    """Classifies task difficulty for routing decisions.

    Heuristics:
    1. Token count > 500 → hard
    2. Multi-step reasoning indicators → hard
    3. Ambiguous/underspecified → uncertain
    4. Code generation + verification → hard
    5. Stuck loop detection → escalate_to_deep (once)

    Example:
        >>> classifier = DifficultyClassifier()
        >>> result = classifier.classify("Generate async Python code with tests")
        >>> print(result.level, result.should_use_deep_planner)
        hard True
    """

    def __init__(self):
        """Initialize difficulty classifier."""
        # Multi-step indicators
        self.multi_step_patterns = [
            r"\bfirst\b.*\bthen\b.*\bfinally\b",
            r"\bstep \d+",
            r"\b(1\.|2\.|3\.)",  # Numbered steps
            r"\bafter\s+that\b",
            r"\bnext\b.*\bthen\b"
        ]

        # Code generation indicators
        self.code_gen_patterns = [
            r"\bgenerate\s+.*\s+(code|function|class|script|python)",
            r"\bwrite\s+(a\s+)?(function|class|module|code)",
            r"\bimplement",
            r"\bcreate\s+.*\s+(code|function|class)",
            r"\bpython\s+code",
            r"\basync\s+(python|code)"
        ]

        # Verification indicators
        self.verification_patterns = [
            r"\bunit\s+test",
            r"\btest(s|ing)",
            r"\bverif(y|ication)",
            r"\bvalidat(e|ion)",
            r"\bcheck\s+that",
            r"\berror\s+handling"
        ]

        # Ambiguity indicators
        self.ambiguity_patterns = [
            r"\bmight\s+need\b",
            r"\bperhaps\b",
            r"\bnot\s+sure\b",
            r"\bunclear\b",
            r"\bdon't\s+know\b"
        ]

    def _count_tokens_estimate(self, text: str) -> int:
        """Rough token count estimate (words * 1.3).

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        words = len(text.split())
        return int(words * 1.3)

    def _has_multi_step_reasoning(self, text: str) -> bool:
        """Check if text indicates multi-step reasoning.

        Args:
            text: Task text

        Returns:
            True if multi-step reasoning detected
        """
        text_lower = text.lower()
        for pattern in self.multi_step_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def _has_code_generation(self, text: str) -> bool:
        """Check if text involves code generation.

        Args:
            text: Task text

        Returns:
            True if code generation detected
        """
        text_lower = text.lower()
        for pattern in self.code_gen_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def _has_verification_requirement(self, text: str) -> bool:
        """Check if text requires verification/testing.

        Args:
            text: Task text

        Returns:
            True if verification detected
        """
        text_lower = text.lower()
        for pattern in self.verification_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def _is_ambiguous(self, text: str) -> bool:
        """Check if task is ambiguous or underspecified.

        Args:
            text: Task text

        Returns:
            True if ambiguity detected
        """
        text_lower = text.lower()
        for pattern in self.ambiguity_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def classify(
        self,
        task: str,
        history: Optional[List[Dict]] = None
    ) -> DifficultyResult:
        """Classify task difficulty.

        Args:
            task: Task description
            history: Optional execution history for stuck detection

        Returns:
            DifficultyResult with level and routing decision
        """
        reasons = []
        score = 0  # Difficulty score (higher = harder)

        # Heuristic 1: Token count
        token_count = self._count_tokens_estimate(task)
        if token_count > TOKEN_COUNT_HARD:
            score += 2
            reasons.append(f"Long task ({token_count} tokens)")

        # Heuristic 2: Multi-step reasoning
        if self._has_multi_step_reasoning(task):
            score += 2
            reasons.append("Multi-step reasoning required")

        # Heuristic 3: Code generation
        has_code = self._has_code_generation(task)
        if has_code:
            score += 1
            reasons.append("Code generation required")

        # Heuristic 4: Verification
        has_verification = self._has_verification_requirement(task)
        if has_verification:
            score += 1
            reasons.append("Verification/testing required")

        # Heuristic 5: Code + verification = hard
        if has_code and has_verification:
            score += 1
            reasons.append("Code generation + verification")

        # Heuristic 6: Ambiguity
        if self._is_ambiguous(task):
            score += 1
            reasons.append("Ambiguous or underspecified")

        # Stuck detection (overrides other heuristics)
        if history:
            stuck_result = self._detect_stuck_loop(history)
            if stuck_result["is_stuck"] and not stuck_result["already_tried_deep"]:
                logger.warning(
                    "[difficulty] Stuck loop detected: %s retries with same error",
                    stuck_result["retry_count"]
                )
                return DifficultyResult(
                    level="escalate_to_deep",
                    confidence=1.0,
                    reasons=["Stuck loop detected, escalating to deep_planner"],
                    should_use_deep_planner=True
                )

        # Classify based on score
        if score >= 3:
            # Hard tasks: 3+ signals (code+verification counts as hard)
            level = "hard"
            confidence = min(score / 6.0, 1.0)
            should_use_deep = True
        elif score >= 2:
            # Medium tasks: 2 signals
            level = "medium"
            confidence = 0.6
            should_use_deep = False
        elif self._is_ambiguous(task):
            # Uncertain: ambiguous or underspecified
            level = "uncertain"
            confidence = 0.5
            should_use_deep = True  # Uncertain tasks benefit from deep planning
        else:
            # Easy: simple, straightforward tasks
            level = "easy"
            confidence = 0.9
            should_use_deep = False

        return DifficultyResult(
            level=level,
            confidence=confidence,
            reasons=reasons,
            should_use_deep_planner=should_use_deep
        )

    def _detect_stuck_loop(self, history: List[Dict]) -> Dict:
        """Detect if planner is stuck in retry loop.

        Args:
            history: Execution history with retries and errors

        Returns:
            Dict with is_stuck, retry_count, already_tried_deep
        """
        if len(history) < MAX_RETRIES_BEFORE_ESCALATION:
            return {"is_stuck": False, "retry_count": 0, "already_tried_deep": False}

        # Check last N attempts
        recent = history[-MAX_RETRIES_BEFORE_ESCALATION:]

        # Look for repeated errors (same stack trace signature)
        error_signatures = []
        for attempt in recent:
            error = attempt.get("error", "")
            if error:
                # Extract error type (first line of stack trace)
                error_type = error.split("\n")[0] if error else ""
                error_signatures.append(error_type)

        # If all errors are identical, we're stuck
        if error_signatures and len(set(error_signatures)) == 1:
            # Check if deep_planner was already tried
            strategies_tried = [
                attempt.get("strategy", "")
                for attempt in history
            ]
            already_tried_deep = "deep_planner" in strategies_tried

            return {
                "is_stuck": True,
                "retry_count": len(error_signatures),
                "already_tried_deep": already_tried_deep,
                "error_type": error_signatures[0]
            }

        return {"is_stuck": False, "retry_count": 0, "already_tried_deep": False}


# Convenience function
def classify_difficulty(
    task: str,
    history: Optional[List[Dict]] = None
) -> DifficultyLevel:
    """Classify task difficulty (convenience function).

    Args:
        task: Task description
        history: Optional execution history

    Returns:
        DifficultyLevel (easy, medium, hard, uncertain, escalate_to_deep)
    """
    classifier = DifficultyClassifier()
    result = classifier.classify(task, history)
    return result.level
