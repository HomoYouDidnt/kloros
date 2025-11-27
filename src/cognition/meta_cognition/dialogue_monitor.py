"""
Conversational Meta-Cognition: Dialogue Quality Monitor

Real-time tracking of conversation health and progress.
Bridges consciousness, memory, and conversation flow into unified meta-awareness.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from collections import deque
import re


@dataclass
class DialogueQualityMetrics:
    """Real-time metrics about conversation quality."""

    # Progress metrics
    turns_since_progress: int = 0  # Turns without new info
    stuck_pattern_detected: bool = False
    progress_score: float = 1.0  # 0-1, how much we're moving forward

    # Clarity metrics
    user_confusion_signals: int = 0  # "what?", "huh?", repetitions
    clarification_requests: int = 0
    clarity_score: float = 1.0  # 0-1, how clear we're being

    # Repetition metrics
    semantic_repetition_score: float = 0.0  # 0-1, how repetitive
    last_n_turns_similarity: List[float] = field(default_factory=list)

    # Engagement metrics
    user_response_times: deque = field(default_factory=lambda: deque(maxlen=5))
    engagement_score: float = 1.0  # 0-1, how engaged user seems

    # Meta-cognitive flags
    should_clarify: bool = False
    should_summarize: bool = False
    should_change_approach: bool = False
    should_confirm_understanding: bool = False

    # Timestamps
    last_progress: float = field(default_factory=time.time)
    last_clarity_issue: Optional[float] = None
    last_intervention: Optional[float] = None


class DialogueMonitor:
    """
    Monitors conversation quality in real-time.

    Detects:
    - Repetition (semantic, not just string matching)
    - Stuck patterns (going in circles)
    - Clarity issues (user confusion)
    - Progress stalls (not moving forward)
    """

    def __init__(self, embedding_engine=None):
        """
        Initialize dialogue monitor.

        Args:
            embedding_engine: Optional embedding engine for semantic similarity
        """
        self.metrics = DialogueQualityMetrics()
        self.embedding_engine = embedding_engine

        # Recent turns for analysis (role, text, embedding, timestamp)
        self.recent_turns: deque = deque(maxlen=10)

        # Confusion signal patterns
        self.confusion_patterns = [
            r"\b(what|huh|sorry|confused|don'?t understand)\b",
            r"^(wh?at\?+|huh\?+|sorry\?+)$",
            r"\bcan you (repeat|say that again|clarify)\b",
        ]

        # Progress indicators (positive signals)
        self.progress_patterns = [
            r"\b(ok|got it|understood|makes sense|ah|i see)\b",
            r"\b(thanks|thank you|perfect|great)\b",
        ]

    def add_turn(self, role: str, text: str, embedding: Optional[List[float]] = None):
        """
        Add a turn and update metrics.

        Args:
            role: "user" or "assistant"
            text: Turn text
            embedding: Optional semantic embedding
        """
        current_time = time.time()

        # Generate embedding if we have the engine
        if embedding is None and self.embedding_engine and text.strip():
            try:
                embedding = self.embedding_engine.embed(text).tolist()
            except:
                pass

        turn = {
            'role': role,
            'text': text,
            'embedding': embedding,
            'timestamp': current_time
        }

        self.recent_turns.append(turn)

        # Update metrics based on this turn
        if role == 'user':
            self._analyze_user_turn(text, current_time)
        else:  # assistant
            self._analyze_assistant_turn(text, embedding)

    def _analyze_user_turn(self, text: str, timestamp: float):
        """Analyze user turn for confusion, progress signals."""
        # Check for confusion signals
        is_confused = any(
            re.search(pattern, text.lower())
            for pattern in self.confusion_patterns
        )

        if is_confused:
            self.metrics.user_confusion_signals += 1
            self.metrics.last_clarity_issue = timestamp
            self.metrics.clarity_score = max(0.0, self.metrics.clarity_score - 0.2)

        # Check for progress signals
        has_progress = any(
            re.search(pattern, text.lower())
            for pattern in self.progress_patterns
        )

        if has_progress:
            self.metrics.last_progress = timestamp
            self.metrics.turns_since_progress = 0
            self.metrics.progress_score = min(1.0, self.metrics.progress_score + 0.1)
        else:
            self.metrics.turns_since_progress += 1

        # Track response time (if we have previous assistant turn)
        for turn in reversed(self.recent_turns):
            if turn['role'] == 'assistant':
                response_time = timestamp - turn['timestamp']
                self.metrics.user_response_times.append(response_time)
                break

    def _analyze_assistant_turn(self, text: str, embedding: Optional[List[float]]):
        """Analyze assistant turn for repetition."""
        if not embedding:
            return

        # Check semantic similarity to recent assistant turns
        similarities = []
        for turn in self.recent_turns:
            if turn['role'] == 'assistant' and turn['embedding']:
                sim = self._cosine_similarity(embedding, turn['embedding'])
                similarities.append(sim)

        if similarities:
            avg_similarity = sum(similarities) / len(similarities)
            self.metrics.semantic_repetition_score = avg_similarity
            self.metrics.last_n_turns_similarity.append(avg_similarity)

            # Keep last 5 similarity scores
            if len(self.metrics.last_n_turns_similarity) > 5:
                self.metrics.last_n_turns_similarity.pop(0)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def compute_meta_state(self) -> Dict[str, Any]:
        """
        Compute current meta-cognitive state.

        Returns:
            Dictionary with meta-state assessment
        """
        current_time = time.time()

        # Reset flags
        self.metrics.should_clarify = False
        self.metrics.should_summarize = False
        self.metrics.should_change_approach = False
        self.metrics.should_confirm_understanding = False

        # Clarity check
        if self.metrics.user_confusion_signals >= 2:
            self.metrics.should_clarify = True
            self.metrics.clarity_score = max(0.0, self.metrics.clarity_score - 0.1)

        # Progress check (lowered threshold from 4 to 3 for faster detection)
        if self.metrics.turns_since_progress >= 3:
            time_since_progress = current_time - self.metrics.last_progress
            # In testing or rapid conversation, don't require 60 second wait
            if time_since_progress > 10 or self.metrics.turns_since_progress >= 4:
                self.metrics.should_change_approach = True
                self.metrics.progress_score = max(0.0, self.metrics.progress_score - 0.2)

        # Repetition check
        if len(self.metrics.last_n_turns_similarity) >= 3:
            avg_recent_sim = sum(self.metrics.last_n_turns_similarity) / len(self.metrics.last_n_turns_similarity)
            if avg_recent_sim > 0.85:  # Very high similarity
                self.metrics.should_change_approach = True

        # Long conversation → summarize
        if len(self.recent_turns) >= 8:
            self.metrics.should_summarize = True

        # Uncertainty → confirm
        if self.metrics.clarity_score < 0.6:
            self.metrics.should_confirm_understanding = True

        return {
            'quality_scores': {
                'progress': self.metrics.progress_score,
                'clarity': self.metrics.clarity_score,
                'engagement': self.metrics.engagement_score,
            },
            'issues': {
                'repetition': self.metrics.semantic_repetition_score > 0.8,
                'stuck': self.metrics.turns_since_progress >= 3,
                'confusion': self.metrics.user_confusion_signals >= 2,
            },
            'interventions': {
                'clarify': self.metrics.should_clarify,
                'summarize': self.metrics.should_summarize,
                'change_approach': self.metrics.should_change_approach,
                'confirm': self.metrics.should_confirm_understanding,
            },
            'turn_count': len(self.recent_turns),
        }

    def get_intervention_suggestion(self) -> Optional[str]:
        """
        Get intervention suggestion based on current meta-state.

        Returns:
            Intervention prompt to prepend to response, or None
        """
        state = self.compute_meta_state()

        # Prioritize interventions
        if state['interventions']['clarify']:
            return "I notice you seem confused. Let me clarify: "

        if state['interventions']['change_approach']:
            return "Let me try a different approach: "

        if state['interventions']['confirm']:
            return "To make sure I understand correctly: "

        if state['interventions']['summarize']:
            return "Let me summarize what we've covered so far: "

        return None

    def reset_session(self):
        """Reset metrics for new conversation session."""
        self.metrics = DialogueQualityMetrics()
        self.recent_turns.clear()
