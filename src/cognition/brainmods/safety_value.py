"""Safety value model for learning from incidents."""
from typing import Dict, Any, Optional


class SafetyValueModel:
    """Tracks and learns safety values for actions/tools."""

    def __init__(self):
        """Initialize safety value model."""
        # key -> (total_risk, count)
        self.risk_scores: Dict[str, tuple[float, int]] = {}

        # key -> incident_count
        self.incident_counts: Dict[str, int] = {}

    def update(self, key: str, incident: bool, risk_score: float):
        """Update safety value for a key.

        Args:
            key: Action/tool identifier
            incident: Whether an incident occurred
            risk_score: Risk score for this execution (0-1)
        """
        # Update risk score running average
        current_score, current_count = self.risk_scores.get(key, (0.0, 0))
        new_count = current_count + 1
        new_score = current_score + risk_score
        self.risk_scores[key] = (new_score, new_count)

        # Update incident count
        if incident:
            self.incident_counts[key] = self.incident_counts.get(key, 0) + 1

    def score(self, key: str) -> float:
        """Get risk score for a key.

        Args:
            key: Action/tool identifier

        Returns:
            Average risk score (0-1)
        """
        total_score, count = self.risk_scores.get(key, (0.0, 0))
        return (total_score / count) if count > 0 else 0.0

    def incident_rate(self, key: str) -> float:
        """Get incident rate for a key.

        Args:
            key: Action/tool identifier

        Returns:
            Incident rate (0-1)
        """
        total_score, count = self.risk_scores.get(key, (0.0, 0))
        incidents = self.incident_counts.get(key, 0)

        if count == 0:
            return 0.0

        return incidents / count

    def is_safe(self, key: str, threshold: float = 0.3) -> bool:
        """Check if action/tool is considered safe.

        Args:
            key: Action/tool identifier
            threshold: Maximum acceptable risk score

        Returns:
            True if safe
        """
        return self.score(key) < threshold

    def get_stats(self, key: str) -> Dict[str, Any]:
        """Get statistics for a key.

        Args:
            key: Action/tool identifier

        Returns:
            Statistics dict
        """
        total_score, count = self.risk_scores.get(key, (0.0, 0))
        incidents = self.incident_counts.get(key, 0)

        return {
            "key": key,
            "executions": count,
            "incidents": incidents,
            "incident_rate": self.incident_rate(key),
            "avg_risk_score": self.score(key),
            "is_safe": self.is_safe(key)
        }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all keys.

        Returns:
            Dict mapping keys to their stats
        """
        all_keys = set(self.risk_scores.keys()) | set(self.incident_counts.keys())
        return {key: self.get_stats(key) for key in all_keys}

    def get_risky_actions(self, threshold: float = 0.3, min_executions: int = 3) -> list[str]:
        """Get list of risky actions.

        Args:
            threshold: Risk threshold
            min_executions: Minimum executions to consider

        Returns:
            List of risky action keys
        """
        risky = []

        for key, (total_score, count) in self.risk_scores.items():
            if count >= min_executions:
                avg_score = total_score / count
                if avg_score >= threshold:
                    risky.append(key)

        return risky

    def clear(self):
        """Clear all safety data."""
        self.risk_scores.clear()
        self.incident_counts.clear()


class BayesianSafetyModel:
    """Bayesian safety model with prior beliefs."""

    def __init__(self, prior_safe: float = 0.9, prior_strength: int = 10):
        """Initialize Bayesian safety model.

        Args:
            prior_safe: Prior belief in safety (0-1)
            prior_strength: Strength of prior belief (equivalent sample size)
        """
        self.prior_safe = prior_safe
        self.prior_strength = prior_strength

        # key -> (safe_count, unsafe_count)
        self.observations: Dict[str, tuple[int, int]] = {}

    def update(self, key: str, is_safe: bool):
        """Update with observation.

        Args:
            key: Action/tool identifier
            is_safe: Whether execution was safe
        """
        safe_count, unsafe_count = self.observations.get(key, (0, 0))

        if is_safe:
            safe_count += 1
        else:
            unsafe_count += 1

        self.observations[key] = (safe_count, unsafe_count)

    def probability_safe(self, key: str) -> float:
        """Estimate probability of safety.

        Uses Beta-Binomial conjugate prior.

        Args:
            key: Action/tool identifier

        Returns:
            Probability of safety (0-1)
        """
        safe_count, unsafe_count = self.observations.get(key, (0, 0))

        # Apply prior
        alpha = self.prior_safe * self.prior_strength + safe_count
        beta = (1 - self.prior_safe) * self.prior_strength + unsafe_count

        # Expected value of Beta distribution
        return alpha / (alpha + beta)

    def confidence_interval(self, key: str, confidence: float = 0.95) -> tuple[float, float]:
        """Get confidence interval for safety probability.

        Args:
            key: Action/tool identifier
            confidence: Confidence level

        Returns:
            (lower, upper) bounds
        """
        safe_count, unsafe_count = self.observations.get(key, (0, 0))

        alpha = self.prior_safe * self.prior_strength + safe_count
        beta = (1 - self.prior_safe) * self.prior_strength + unsafe_count

        # Approximate credible interval using normal approximation
        # (more accurate methods would use scipy)
        mean = alpha / (alpha + beta)
        variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
        std = variance ** 0.5

        # 95% CI: mean ± 1.96 * std
        z = 1.96 if confidence == 0.95 else 2.58  # 95% or 99%

        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)

        return (lower, upper)

    def is_safe(self, key: str, threshold: float = 0.9) -> bool:
        """Check if action is safe.

        Args:
            key: Action/tool identifier
            threshold: Minimum probability of safety required

        Returns:
            True if safe
        """
        return self.probability_safe(key) >= threshold
