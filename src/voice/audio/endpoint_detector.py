"""
Phase 4: Natural Endpoint Detection for KLoROS Streaming Audio.

Implements intelligent speech boundary detection that goes beyond simple silence
timeouts to understand natural conversation flow and sentence completion.
"""

import re
import time
import numpy as np
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum


class EndpointType(Enum):
    """Types of detected endpoints."""
    INCOMPLETE = "incomplete"      # Speech still continuing
    NATURAL_PAUSE = "natural_pause"  # Brief pause, likely continuing
    SENTENCE_END = "sentence_end"  # Complete sentence detected
    QUESTION_END = "question_end"  # Question completed
    TIMEOUT = "timeout"           # Hard timeout reached


@dataclass
class EndpointDecision:
    """Result of endpoint detection analysis."""
    endpoint_type: EndpointType
    confidence: float  # 0.0 to 1.0
    wait_time_ms: int  # How long to wait before finalizing
    reasoning: str     # Why this decision was made
    metadata: Dict     # Additional context


class SemanticEndpointDetector:
    """
    Intelligent endpoint detection using semantic analysis of transcribed text
    combined with audio-based silence detection and user speech pattern learning.
    """

    def __init__(self):
        """Initialize the semantic endpoint detector."""

        # Timing parameters (adaptive)
        self.base_silence_ms = 600      # Base silence timeout
        self.max_silence_ms = 2000      # Maximum silence timeout
        self.min_silence_ms = 300       # Minimum silence timeout
        self.question_timeout_ms = 1200  # Extra time for questions

        # Sentence completion patterns
        self.sentence_endings = {'.', '!', '?', ';'}
        self.question_words = {
            'what', 'when', 'where', 'who', 'why', 'how', 'which', 'whose',
            'is', 'are', 'was', 'were', 'will', 'would', 'could', 'should',
            'can', 'do', 'does', 'did', 'have', 'has', 'had'
        }

        # User adaptation tracking
        self.user_patterns = {
            'avg_pause_ms': 800,
            'speech_rate_wpm': 150,
            'sentence_length_words': 12,
            'question_pause_ratio': 1.5,
            'total_samples': 0
        }

        # Confidence thresholds
        self.high_confidence_threshold = 0.8
        self.medium_confidence_threshold = 0.6

    def analyze_endpoint(
        self,
        current_transcript: str,
        silence_duration_ms: int,
        speech_confidence: float,
        audio_energy: float
    ) -> EndpointDecision:
        """
        Analyze current state to determine if we've reached a natural endpoint.

        Args:
            current_transcript: Current transcribed text
            silence_duration_ms: How long silence has been observed
            speech_confidence: STT confidence of current transcript
            audio_energy: Current audio energy level

        Returns:
            EndpointDecision with recommendation
        """

        # Skip analysis if transcript is too short
        if len(current_transcript.strip()) < 3:
            return self._create_decision(
                EndpointType.INCOMPLETE, 0.3, self.min_silence_ms,
                "Transcript too short for analysis"
            )

        # Analyze semantic completeness
        semantic_score, semantic_reasoning = self._analyze_semantic_completeness(current_transcript)

        # Analyze speech patterns
        timing_score, timing_reasoning = self._analyze_timing_patterns(
            current_transcript, silence_duration_ms
        )

        # Analyze audio characteristics
        audio_score, audio_reasoning = self._analyze_audio_characteristics(
            speech_confidence, audio_energy, silence_duration_ms
        )

        # Combine scores for final decision
        final_decision = self._make_final_decision(
            current_transcript, silence_duration_ms,
            semantic_score, timing_score, audio_score,
            f"{semantic_reasoning} | {timing_reasoning} | {audio_reasoning}"
        )

        # Update user patterns for adaptation
        self._update_user_patterns(current_transcript, silence_duration_ms)

        return final_decision

    def _analyze_semantic_completeness(self, transcript: str) -> Tuple[float, str]:
        """Analyze if the transcript represents a semantically complete thought."""

        text = transcript.strip().lower()
        words = text.split()

        if len(words) == 0:
            return 0.0, "empty"

        score = 0.0
        reasons = []

        # Check for explicit sentence endings
        if any(text.endswith(ending) for ending in self.sentence_endings):
            score += 0.4
            reasons.append("explicit_ending")

        # Check for question completion
        if self._is_complete_question(text):
            score += 0.3
            reasons.append("complete_question")
        elif self._starts_like_question(text) and len(words) < 3:
            score -= 0.2
            reasons.append("incomplete_question")

        # Check grammatical completeness
        if self._has_subject_predicate(text):
            score += 0.2
            reasons.append("subject_predicate")

        # Check for incomplete structures
        if self._has_incomplete_structures(text):
            score -= 0.3
            reasons.append("incomplete_structures")

        # Length-based heuristics
        if len(words) >= self.user_patterns['sentence_length_words']:
            score += 0.1
            reasons.append("adequate_length")
        elif len(words) < 4:
            score -= 0.1
            reasons.append("too_short")

        return min(1.0, max(0.0, score)), ",".join(reasons)

    def _analyze_timing_patterns(self, transcript: str, silence_ms: int) -> Tuple[float, str]:
        """Analyze timing patterns relative to user's speech habits."""

        words = transcript.strip().split()
        word_count = len(words)

        # Calculate expected pause time based on user patterns
        if self._starts_like_question(transcript):
            expected_pause = self.user_patterns['avg_pause_ms'] * self.user_patterns['question_pause_ratio']
            context = "question"
        else:
            expected_pause = self.user_patterns['avg_pause_ms']
            context = "statement"

        # Score based on how close we are to expected pause
        if silence_ms >= expected_pause:
            timing_score = 0.8
            reason = f"silence_sufficient_{context}"
        elif silence_ms >= expected_pause * 0.7:
            timing_score = 0.6
            reason = f"silence_approaching_{context}"
        elif silence_ms >= expected_pause * 0.4:
            timing_score = 0.3
            reason = f"silence_partial_{context}"
        else:
            timing_score = 0.1
            reason = f"silence_too_short_{context}"

        return timing_score, reason

    def _analyze_audio_characteristics(
        self, speech_confidence: float, audio_energy: float, silence_ms: int
    ) -> Tuple[float, str]:
        """Analyze audio characteristics for endpoint decision."""

        score = 0.0
        reasons = []

        # High confidence speech suggests clear audio
        if speech_confidence > 0.9:
            score += 0.2
            reasons.append("high_confidence")
        elif speech_confidence < 0.6:
            score += 0.1  # Low confidence might mean trailing off
            reasons.append("low_confidence_trailing")

        # Silence duration relative to hard limits
        if silence_ms >= self.max_silence_ms:
            score += 0.8  # Definitely should end
            reasons.append("max_timeout")
        elif silence_ms >= self.base_silence_ms:
            score += 0.4
            reasons.append("base_timeout")
        elif silence_ms < self.min_silence_ms:
            score -= 0.3
            reasons.append("too_early")

        return min(1.0, max(0.0, score)), ",".join(reasons)

    def _make_final_decision(
        self,
        transcript: str,
        silence_ms: int,
        semantic_score: float,
        timing_score: float,
        audio_score: float,
        reasoning: str
    ) -> EndpointDecision:
        """Combine all scores to make final endpoint decision."""

        # Weighted combination of scores
        combined_score = (
            semantic_score * 0.4 +  # Semantic understanding is most important
            timing_score * 0.35 +   # Timing patterns second
            audio_score * 0.25      # Audio characteristics third
        )

        # Determine endpoint type and wait time
        if combined_score >= self.high_confidence_threshold:
            if self._starts_like_question(transcript):
                endpoint_type = EndpointType.QUESTION_END
                wait_time = min(200, max(0, self.question_timeout_ms - silence_ms))
            else:
                endpoint_type = EndpointType.SENTENCE_END
                wait_time = min(100, max(0, self.base_silence_ms - silence_ms))

        elif combined_score >= self.medium_confidence_threshold:
            endpoint_type = EndpointType.NATURAL_PAUSE
            wait_time = min(400, max(0, self.base_silence_ms - silence_ms))

        elif silence_ms >= self.max_silence_ms:
            endpoint_type = EndpointType.TIMEOUT
            wait_time = 0

        else:
            endpoint_type = EndpointType.INCOMPLETE
            wait_time = min(600, max(0, self.base_silence_ms - silence_ms))

        return self._create_decision(
            endpoint_type, combined_score, wait_time, reasoning,
            {
                'semantic_score': semantic_score,
                'timing_score': timing_score,
                'audio_score': audio_score,
                'transcript_length': len(transcript.strip())
            }
        )

    def _update_user_patterns(self, transcript: str, silence_ms: int):
        """Update user speech patterns for adaptive timing."""

        words = transcript.strip().split()
        word_count = len(words)

        if word_count > 2:  # Only update for substantial input
            # Update running averages
            alpha = 0.1  # Learning rate

            self.user_patterns['avg_pause_ms'] = (
                (1 - alpha) * self.user_patterns['avg_pause_ms'] +
                alpha * silence_ms
            )

            self.user_patterns['sentence_length_words'] = (
                (1 - alpha) * self.user_patterns['sentence_length_words'] +
                alpha * word_count
            )

            self.user_patterns['total_samples'] += 1

    # Utility methods for semantic analysis

    def _is_complete_question(self, text: str) -> bool:
        """Check if text represents a complete question."""
        if not text.endswith('?'):
            return False

        words = text.split()
        if len(words) < 2:
            return False

        # Look for question structure
        return (
            words[0] in self.question_words or
            any(word in self.question_words for word in words[:3])
        )

    def _starts_like_question(self, text: str) -> bool:
        """Check if text starts like a question."""
        words = text.lower().split()
        return len(words) > 0 and words[0] in self.question_words

    def _has_subject_predicate(self, text: str) -> bool:
        """Basic check for subject-predicate structure."""
        words = text.split()

        # Very basic heuristic - look for common patterns
        if len(words) < 2:
            return False

        # Look for verb indicators
        verb_indicators = {'is', 'are', 'was', 'were', 'have', 'has', 'had', 'will', 'would', 'can', 'could'}
        return any(word.lower() in verb_indicators for word in words[1:4])

    def _has_incomplete_structures(self, text: str) -> bool:
        """Check for obviously incomplete grammatical structures."""

        incomplete_patterns = [
            r'\b(and|but|or|because|since|while|if|when|before|after|although)\s*$',
            r'\b(the|a|an)\s*$',
            r'\b(is|are|was|were)\s*$',
            r'\b(i|you|he|she|it|we|they)\s*$'
        ]

        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in incomplete_patterns)

    def _create_decision(
        self,
        endpoint_type: EndpointType,
        confidence: float,
        wait_time_ms: int,
        reasoning: str,
        metadata: Optional[Dict] = None
    ) -> EndpointDecision:
        """Create an EndpointDecision object."""

        return EndpointDecision(
            endpoint_type=endpoint_type,
            confidence=confidence,
            wait_time_ms=wait_time_ms,
            reasoning=reasoning,
            metadata=metadata or {}
        )

    def get_user_patterns(self) -> Dict:
        """Get current user speech patterns for debugging."""
        return self.user_patterns.copy()

    def reset_user_patterns(self):
        """Reset user patterns to defaults."""
        self.user_patterns = {
            'avg_pause_ms': 800,
            'speech_rate_wpm': 150,
            'sentence_length_words': 12,
            'question_pause_ratio': 1.5,
            'total_samples': 0
        }