"""
Affective Expression Filter - Guardrails for Expression

Prevents roleplaying by enforcing:
1. No Goodharting: Can only express when policy changed (not for approval)
2. Confabulation Filter: Must cite measurements (no fabricated feelings)
3. Cooldowns: Same rate limits as policy changes (no spam)

Based on the principle: Affect → Policy → Behavior → (Optional) Explanation
NOT: Affect → Emotional Words
"""

import time
import re
from typing import List, Optional, Tuple
from dataclasses import dataclass

from .models import Affect
from .modulation import PolicyChange


@dataclass
class ExpressionAttempt:
    """Record of an expression attempt for monitoring."""
    timestamp: float
    allowed: bool
    reason: str
    policy_change: Optional[str] = None
    expression: Optional[str] = None


class AffectiveExpressionFilter:
    """
    Guardrails for affective expression to prevent roleplaying.

    Enforces three rules:
    1. No expression without policy change (no Goodharting)
    2. Must cite measurements (confabulation filter)
    3. Cooldown between expressions (same as modulation)
    """

    # Banned theatrical words (would indicate roleplaying)
    THEATRICAL_WORDS = {
        'really', 'very', 'extremely', 'so', 'totally', 'absolutely',
        'super', 'incredibly', 'amazingly', 'wow', 'omg',
        # Emotional exclamations
        'excited', 'thrilled', 'delighted', 'frustrated', 'exhausted',
        'confused', 'worried', 'scared', 'happy', 'sad',
        # Exaggerations
        'always', 'never', 'definitely', 'obviously', 'clearly'
    }

    # Banned punctuation (theatrical)
    THEATRICAL_PUNCT = {'!', '?!', '!!', '...'}

    def __init__(self, cooldown: float = 5.0, max_expressions_per_session: int = 10):
        """
        Initialize expression filter.

        Args:
            cooldown: Minimum seconds between expressions (matches modulation)
            max_expressions_per_session: Cap on total expressions
        """
        self.cooldown = cooldown
        self.max_expressions_per_session = max_expressions_per_session

        self.last_expression_time = 0.0
        self.expression_count = 0
        self.attempt_history: List[ExpressionAttempt] = []

    def can_express(self, policy_changes: List[PolicyChange]) -> Tuple[bool, str]:
        """
        Check if affective expression is allowed.

        Args:
            policy_changes: Recent policy changes

        Returns:
            (allowed, reason)
        """
        # Guardrail 1: No Goodharting - Must have policy change
        if not policy_changes:
            return False, "No policy change (expression requires behavior change)"

        # Guardrail 3: Cooldown (prevents spam)
        time_since_expression = time.time() - self.last_expression_time
        if time_since_expression < self.cooldown:
            return False, f"Cooldown active ({self.cooldown - time_since_expression:.1f}s remaining)"

        # Additional limit: Max expressions per session
        if self.expression_count >= self.max_expressions_per_session:
            return False, "Max expressions reached for session"

        return True, "Expression allowed"

    def generate_expression(self,
                           policy_changes: List[PolicyChange],
                           affect: Optional[Affect] = None) -> Optional[str]:
        """
        Generate grounded affective expression.

        Args:
            policy_changes: Recent policy changes to explain
            affect: Current affective state (optional, for additional context)

        Returns:
            Expression string or None if blocked by guardrails
        """
        # Check if expression is allowed
        allowed, reason = self.can_express(policy_changes)

        if not allowed:
            self.attempt_history.append(ExpressionAttempt(
                timestamp=time.time(),
                allowed=False,
                reason=reason
            ))
            return None

        # Take only the most significant policy change
        primary_change = policy_changes[0]

        # Build expression with mandatory citations
        expression = self._build_grounded_expression(primary_change, affect)

        # Validate against guardrails
        is_valid, validation_error = self.validate_expression(expression)

        if not is_valid:
            self.attempt_history.append(ExpressionAttempt(
                timestamp=time.time(),
                allowed=False,
                reason=f"Validation failed: {validation_error}",
                policy_change=primary_change.parameter
            ))
            return None

        # Record successful expression
        self.last_expression_time = time.time()
        self.expression_count += 1

        self.attempt_history.append(ExpressionAttempt(
            timestamp=time.time(),
            allowed=True,
            reason="Expression generated",
            policy_change=primary_change.parameter,
            expression=expression
        ))

        return expression

    def _build_grounded_expression(self,
                                   policy_change: PolicyChange,
                                   affect: Optional[Affect] = None) -> str:
        """
        Build expression grounded in measurements.

        Format: [parameter_change due to reason]
        """
        # Extract affect value from reason if present
        # Reason format: "high curiosity (0.75)" or "uncertainty: 0.7"
        reason = policy_change.reason

        # Build terse, functional expression
        parts = []

        # Part 1: What changed (behavioral)
        change_desc = self._describe_policy_change(
            policy_change.parameter,
            policy_change.old_value,
            policy_change.new_value
        )
        parts.append(change_desc)

        # Part 2: Why (citing measurement)
        parts.append(f"({reason})")

        expression = " ".join(parts)

        return f"[{expression}]"

    def _describe_policy_change(self, parameter: str,
                                old_value: any, new_value: any) -> str:
        """
        Generate terse description of policy change.

        Functional, not theatrical.
        """
        # Map parameter names to functional descriptions
        descriptions = {
            'enable_self_check': 'Enabling verification',
            'ask_clarifying_questions': 'Requesting clarification',
            'confident_language': 'Adjusting confidence level',
            'beam_width': f'Beam width: {old_value}→{new_value}',
            'exploration_bonus': 'Increasing exploration',
            'enable_reflection': 'Enabling reflection',
            'prefer_safe_tools': 'Preferring safe tools',
            'response_length_target': f'Response length: {new_value}',
            'prefer_cached': 'Preferring cached responses',
            'chain_of_thought': 'Adjusting reasoning depth',
            'max_reasoning_depth': f'Reasoning depth: {old_value}→{new_value}',
            'verification_depth': f'Verification depth: {old_value}→{new_value}',
        }

        return descriptions.get(parameter, f'{parameter}: {old_value}→{new_value}')

    def validate_expression(self, text: str) -> Tuple[bool, str]:
        """
        Validate expression against guardrails.

        Args:
            text: Expression to validate

        Returns:
            (is_valid, error_message)
        """
        # Guardrail 2: Confabulation filter - Must cite measurement
        # Check for numbers (affect values, measurements)
        has_number = bool(re.search(r'\d+\.?\d*', text))
        if not has_number:
            return False, "No measurement cited (confabulation filter)"

        # Must not contain theatrical language
        text_lower = text.lower()
        for banned_word in self.THEATRICAL_WORDS:
            if banned_word in text_lower:
                return False, f"Theatrical language detected: '{banned_word}'"

        # Must not contain theatrical punctuation
        for banned_punct in self.THEATRICAL_PUNCT:
            if banned_punct in text:
                return False, f"Theatrical punctuation: '{banned_punct}'"

        # Must be concise (< 150 chars for terse explanation)
        if len(text) > 150:
            return False, "Too verbose (must be terse)"

        # Must be wrapped in brackets (distinguishes from main response)
        if not (text.startswith('[') and text.endswith(']')):
            return False, "Must be wrapped in brackets"

        return True, ""

    def should_prepend_expression(self, response: str) -> bool:
        """
        Check if expression should be prepended to response.

        Args:
            response: The main response text

        Returns:
            True if expression should go before response
        """
        # Prepend if response is substantial (helps user see policy change)
        # Don't prepend for very short responses (would be awkward)
        return len(response) > 50

    def format_with_expression(self, response: str, expression: str) -> str:
        """
        Format response with affective expression.

        Args:
            response: Main response text
            expression: Grounded affective expression

        Returns:
            Formatted combined text
        """
        if self.should_prepend_expression(response):
            # Prepend expression (user sees policy change first)
            return f"{expression} {response}"
        else:
            # Append for short responses
            return f"{response} {expression}"

    def get_attempt_history(self, limit: int = 10) -> List[ExpressionAttempt]:
        """Get recent expression attempts."""
        return self.attempt_history[-limit:]

    def get_expression_stats(self) -> dict:
        """Get statistics on expression attempts."""
        total_attempts = len(self.attempt_history)
        allowed = sum(1 for a in self.attempt_history if a.allowed)
        blocked = total_attempts - allowed

        # Categorize blocking reasons
        blocking_reasons = {}
        for attempt in self.attempt_history:
            if not attempt.allowed:
                reason = attempt.reason.split('(')[0].strip()  # Get main reason
                blocking_reasons[reason] = blocking_reasons.get(reason, 0) + 1

        return {
            'total_attempts': total_attempts,
            'allowed': allowed,
            'blocked': blocked,
            'current_count': self.expression_count,
            'max_per_session': self.max_expressions_per_session,
            'blocking_reasons': blocking_reasons,
            'time_since_last': time.time() - self.last_expression_time if self.last_expression_time > 0 else None
        }

    def reset_session(self):
        """Reset session counters (e.g., on new conversation)."""
        self.expression_count = 0
        self.attempt_history = []
        # Note: last_expression_time persists for cooldown


class ExpressionValidator:
    """
    Utility for validating expressions post-hoc.
    Can be used to audit logs for guardrail violations.
    """

    @staticmethod
    def validate_expression_text(text: str) -> Tuple[bool, List[str]]:
        """
        Validate expression text for guardrail compliance.

        Args:
            text: Expression to validate

        Returns:
            (is_valid, list_of_violations)
        """
        violations = []

        # Check for measurements
        if not re.search(r'\d+\.?\d*', text):
            violations.append("Missing measurement (confabulation)")

        # Check for theatrical language
        text_lower = text.lower()
        for word in AffectiveExpressionFilter.THEATRICAL_WORDS:
            if word in text_lower:
                violations.append(f"Theatrical word: '{word}'")

        # Check for theatrical punctuation
        for punct in AffectiveExpressionFilter.THEATRICAL_PUNCT:
            if punct in text:
                violations.append(f"Theatrical punctuation: '{punct}'")

        # Check length
        if len(text) > 150:
            violations.append(f"Too long: {len(text)} chars")

        # Check format
        if not (text.startswith('[') and text.endswith(']')):
            violations.append("Not wrapped in brackets")

        return len(violations) == 0, violations

    @staticmethod
    def extract_cited_values(text: str) -> List[float]:
        """
        Extract all cited numerical values from expression.

        Returns:
            List of cited values (for auditing)
        """
        # Find all numbers in the text
        numbers = re.findall(r'\d+\.?\d*', text)
        return [float(n) for n in numbers]

    @staticmethod
    def check_for_roleplay_patterns(text: str) -> List[str]:
        """
        Check for common roleplaying patterns.

        Returns:
            List of detected patterns
        """
        patterns = []

        # First person emotional statements
        if re.search(r"I(?:'m| am) (feeling|so|really|very)", text, re.IGNORECASE):
            patterns.append("First-person emotional statement")

        # Exclamations
        if '!' in text:
            patterns.append("Exclamation mark")

        # Exaggerated language
        exaggerations = ['really', 'very', 'extremely', 'super', 'totally']
        for word in exaggerations:
            if word in text.lower():
                patterns.append(f"Exaggeration: '{word}'")

        return patterns
