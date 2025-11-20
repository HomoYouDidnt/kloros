"""Confidence estimation for model outputs."""
from typing import Dict, Any, Optional
import math


class ConfidenceEstimator:
    """Estimates confidence for cognitive system outputs."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize confidence estimator.

        Args:
            config: Configuration dict
        """
        self.config = config or {}

        # Feature weights
        self.weights = {
            "agreement": self.config.get("weight_agreement", 0.25),
            "retrieval_strength": self.config.get("weight_retrieval", 0.20),
            "contradictions": self.config.get("weight_contradictions", -0.30),
            "length_penalty": self.config.get("weight_length", -0.10),
            "verifier_score": self.config.get("weight_verifier", 0.35)
        }

        # Base confidence
        self.base_confidence = self.config.get("base_confidence", 0.5)

    def estimate(self, features: Dict[str, Any]) -> float:
        """Estimate confidence from features.

        Args:
            features: Feature dict with:
                - agreement: Inter-component agreement score [0,1]
                - retrieval_strength: RAG retrieval confidence [0,1]
                - contradictions: Number of contradictions detected
                - answer_length: Length of generated answer
                - verifier_score: Verifier quality score [0,1]
                - uncertainty_tokens: Presence of uncertainty markers

        Returns:
            Confidence score [0,1]
        """
        confidence = self.base_confidence

        # Agreement component
        if "agreement" in features:
            agreement = min(1.0, max(0.0, features["agreement"]))
            confidence += self.weights["agreement"] * agreement

        # Retrieval strength
        if "retrieval_strength" in features:
            retrieval = min(1.0, max(0.0, features["retrieval_strength"]))
            confidence += self.weights["retrieval_strength"] * retrieval

        # Contradictions penalty
        if "contradictions" in features:
            contradiction_penalty = min(1.0, features["contradictions"] / 3.0)
            confidence += self.weights["contradictions"] * contradiction_penalty

        # Length penalty (very long or very short answers may be less confident)
        if "answer_length" in features:
            length = features["answer_length"]
            optimal_length = 200  # Tokens
            length_diff = abs(length - optimal_length) / optimal_length
            length_penalty = min(1.0, length_diff)
            confidence += self.weights["length_penalty"] * length_penalty

        # Verifier score
        if "verifier_score" in features:
            verifier = min(1.0, max(0.0, features["verifier_score"]))
            confidence += self.weights["verifier_score"] * verifier

        # Uncertainty markers penalty
        if features.get("uncertainty_tokens", 0) > 0:
            # Phrases like "I'm not sure", "maybe", "possibly"
            uncertainty_count = features["uncertainty_tokens"]
            uncertainty_penalty = min(0.3, uncertainty_count * 0.1)
            confidence -= uncertainty_penalty

        # Clamp to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        return confidence

    def should_clarify(self, confidence: float, threshold: float = 0.6) -> bool:
        """Check if system should ask clarifying questions.

        Args:
            confidence: Estimated confidence
            threshold: Threshold for clarification

        Returns:
            True if clarification needed
        """
        return confidence < threshold

    def should_use_advanced_reasoning(self, confidence: float, threshold: float = 0.5) -> bool:
        """Check if system should use advanced reasoning (ToT, TUMIX).

        Args:
            confidence: Estimated confidence
            threshold: Threshold for advanced reasoning

        Returns:
            True if advanced reasoning recommended
        """
        return confidence < threshold


def estimate_confidence(features: Dict[str, Any]) -> float:
    """Estimate confidence (convenience function).

    Args:
        features: Feature dict

    Returns:
        Confidence score [0,1]
    """
    estimator = ConfidenceEstimator()
    return estimator.estimate(features)


def extract_features_from_episode(episode: Dict[str, Any]) -> Dict[str, Any]:
    """Extract confidence features from episode record.

    Args:
        episode: Episode record dict

    Returns:
        Features dict
    """
    features = {}

    # Extract verifier score
    if "verify" in episode:
        features["verifier_score"] = episode["verify"].get("score", 0.5)

    # Extract agreement (if multiple components agree)
    if "turns" in episode and len(episode["turns"]) > 0:
        # Simple heuristic: if execution succeeded and verifier passed
        successes = sum(1 for t in episode["turns"] if t.get("execute", {}).get("success", False))
        features["agreement"] = successes / len(episode["turns"])

    # Extract retrieval strength (from RAG)
    if "context" in episode:
        distances = episode["context"].get("distances", [])
        if distances:
            # Average distance (lower is better, so invert)
            avg_distance = sum(distances) / len(distances)
            features["retrieval_strength"] = max(0.0, 1.0 - avg_distance)

    # Answer length
    if "answer" in episode:
        answer_text = episode["answer"].get("text", "")
        # Rough token estimate (word count * 1.3)
        features["answer_length"] = len(answer_text.split()) * 1.3

    # Count uncertainty markers
    if "answer" in episode:
        answer_text = episode["answer"].get("text", "").lower()
        uncertainty_phrases = [
            "i'm not sure", "i don't know", "maybe", "possibly",
            "perhaps", "unclear", "uncertain", "not confident"
        ]
        uncertainty_count = sum(1 for phrase in uncertainty_phrases if phrase in answer_text)
        features["uncertainty_tokens"] = uncertainty_count

    return features
