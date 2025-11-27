"""
Repetition prevention for KLoROS memory system.

Detects and tracks repetitive responses to improve conversation quality.
"""

from typing import List, Optional, Tuple
from difflib import SequenceMatcher


class RepetitionChecker:
    """Detects and prevents repetitive responses in conversations."""

    def __init__(self, similarity_threshold: float = 0.75, history_size: int = 10):
        """
        Initialize repetition checker.

        Args:
            similarity_threshold: Threshold above which responses are considered repetitive (0.0-1.0)
                                Default 0.75 means 75% similarity triggers repetition warning
            history_size: Number of recent responses to check against
                         Default 10 means check last 10 responses
        """
        self.similarity_threshold = similarity_threshold
        self.history_size = history_size
        self.recent_responses: List[str] = []

    def is_repetitive(self, new_response: str) -> Tuple[bool, Optional[str], float]:
        """
        Check if a response is too similar to recent ones.

        Args:
            new_response: The response to check

        Returns:
            Tuple of (is_repetitive, similar_response, similarity_score)
            - is_repetitive: True if response exceeds similarity threshold
            - similar_response: The most similar previous response (if repetitive)
            - similarity_score: Highest similarity score found (0.0-1.0)
        """
        if not self.recent_responses or not new_response.strip():
            return False, None, 0.0

        max_similarity = 0.0
        most_similar = None

        # Check against all recent responses
        for prev_response in self.recent_responses:
            similarity = self._calculate_similarity(new_response, prev_response)
            if similarity > max_similarity:
                max_similarity = similarity
                most_similar = prev_response

        is_repetitive = max_similarity >= self.similarity_threshold
        return is_repetitive, most_similar, max_similarity

    def add_response(self, response: str):
        """
        Add a response to the history.

        Automatically maintains history size by removing oldest entries.
        """
        if response.strip():  # Only add non-empty responses
            self.recent_responses.append(response)

            # Keep only recent history (sliding window)
            if len(self.recent_responses) > self.history_size:
                self.recent_responses.pop(0)

    def clear(self):
        """Clear response history (e.g., when starting new conversation)."""
        self.recent_responses.clear()

    def get_history_summary(self) -> dict:
        """Get summary of current repetition checking state."""
        return {
            "history_size": len(self.recent_responses),
            "max_history": self.history_size,
            "similarity_threshold": self.similarity_threshold
        }

    @staticmethod
    def _calculate_similarity(text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts.

        Uses SequenceMatcher for character-level similarity with some
        normalization to handle case and whitespace differences.

        Returns:
            Similarity score between 0.0 (completely different) and 1.0 (identical)
        """
        # Normalize texts (lowercase, strip whitespace)
        text1_norm = text1.lower().strip()
        text2_norm = text2.lower().strip()

        # Handle empty strings
        if not text1_norm or not text2_norm:
            return 0.0

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()

    @staticmethod
    def _word_overlap_similarity(text1: str, text2: str) -> float:
        """
        Alternative similarity measure based on word overlap.

        Useful for catching semantic repetition even when phrasing differs.

        Returns:
            Jaccard similarity of word sets (0.0-1.0)
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0
