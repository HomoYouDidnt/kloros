"""
Hybrid Introspection System - Real-time + Periodic Reflection

Combines consciousness-building periodic reflection with real-time optimization
during active conversations for immediate adaptive improvements.
"""

import json
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum

from .config.reflection_config import get_config
from .models.reflection_models import ReflectionInsight, InsightType, ConfidenceLevel


class IntrospectionTrigger(Enum):
    """Triggers for real-time introspection."""
    CONVERSATION_START = "conversation_start"
    USER_CONFUSION = "user_confusion"
    REPEATED_QUESTION = "repeated_question"
    CONTEXT_MISMATCH = "context_mismatch"
    RESPONSE_QUALITY_LOW = "response_quality_low"
    CONVERSATION_END = "conversation_end"


class ConversationQuality(Enum):
    """Assessment of conversation quality."""
    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"
    CRITICAL = "critical"


class HybridIntrospectionManager:
    """
    Manages real-time introspection during active conversations.

    Works alongside the periodic reflection system to provide immediate
    adaptive improvements and context-aware optimization.
    """

    def __init__(self, kloros_instance=None):
        """Initialize hybrid introspection system."""
        self.kloros = kloros_instance
        self.config = get_config()

        # Real-time state tracking
        self.current_conversation_id = None
        self.conversation_start_time = None
        self.conversation_context = {}
        self.real_time_insights = []

        # Quality tracking
        self.response_times = []

        # Adaptive parameters
        self.dynamic_wake_threshold = None
        self.dynamic_response_style = None
        self.conversation_complexity_level = 1.0

    def start_conversation_introspection(self, conversation_id: str) -> None:
        """Initialize real-time introspection for new conversation."""
        self.current_conversation_id = conversation_id
        self.conversation_start_time = time.time()
        self.conversation_context = {
            "start_time": self.conversation_start_time,
            "user_input_count": 0,
            "response_count": 0,
            "topics_discussed": [],
            "complexity_indicators": [],
            "quality_issues": []
        }
        self.real_time_insights = []

        # Generate initial conversation setup insight
        insight = self._create_real_time_insight(
            trigger=InsightType.CONVERSATION_START,
            title="Conversation Initiated",
            content="Starting real-time introspection for new conversation session",
            confidence=1.0
        )
        self.real_time_insights.append(insight)

    def analyze_user_input(self, user_input: str) -> List[ReflectionInsight]:
        """Analyze user input for real-time insights and adaptations."""
        if not self.current_conversation_id:
            return []

        insights = []
        self.conversation_context["user_input_count"] += 1

        # Detect confusion indicators
        confusion_indicators = [
            "what do you mean", "i don't understand", "can you clarify",
            "huh", "what?", "confused", "unclear"
        ]

        if any(indicator in user_input.lower() for indicator in confusion_indicators):
            insight = self._create_real_time_insight(
                trigger=InsightType.USER_CONFUSION,
                title="User Confusion Detected",
                content=f"User expressing confusion: '{user_input[:50]}...' - Consider simpler explanations",
                confidence=0.8
            )
            insights.append(insight)
            self.conversation_context["quality_issues"].append("user_confusion")

        # Detect repeated questions
        if self._is_repeated_question(user_input):
            insight = self._create_real_time_insight(
                trigger=InsightType.REPEATED_QUESTION,
                title="Repeated Question Pattern",
                content="User repeating similar questions - Previous response may have been inadequate",
                confidence=0.7
            )
            insights.append(insight)

        # Analyze complexity level
        complexity = self._assess_input_complexity(user_input)
        self.conversation_context["complexity_indicators"].append(complexity)

        # Adjust conversation complexity level
        avg_complexity = sum(self.conversation_context["complexity_indicators"]) / len(self.conversation_context["complexity_indicators"])
        self.conversation_complexity_level = avg_complexity

        if abs(avg_complexity - self.conversation_complexity_level) > 0.3:
            insight = self._create_real_time_insight(
                trigger=InsightType.CONTEXT_MISMATCH,
                title="Complexity Level Adjustment",
                content=f"Adjusting response complexity to match user level: {avg_complexity:.1f}",
                confidence=0.6
            )
            insights.append(insight)

        self.real_time_insights.extend(insights)
        return insights

    def analyze_response_quality(self, response: str, response_time_ms: float) -> List[ReflectionInsight]:
        """Analyze generated response quality and suggest real-time improvements."""
        if not self.current_conversation_id:
            return []

        insights = []
        self.conversation_context["response_count"] += 1
        self.response_times.append(response_time_ms)

        # Check response time performance
        if response_time_ms > 5000:  # > 5 seconds
            insight = self._create_real_time_insight(
                trigger=InsightType.RESPONSE_QUALITY_LOW,
                title="Slow Response Time",
                content=f"Response took {response_time_ms:.0f}ms - Consider optimization",
                confidence=0.9
            )
            insights.append(insight)

        # Analyze response characteristics
        response_quality = self._assess_response_quality(response)

        if response_quality in [ConversationQuality.POOR, ConversationQuality.CRITICAL]:
            insight = self._create_real_time_insight(
                trigger=InsightType.RESPONSE_QUALITY_LOW,
                title=f"Response Quality: {response_quality.value}",
                content=f"Generated response quality assessed as {response_quality.value} - Review reasoning chain",
                confidence=0.7
            )
            insights.append(insight)

        # Check for personality consistency
        if not self._is_response_personality_consistent(response):
            insight = self._create_real_time_insight(
                trigger=InsightType.RESPONSE_QUALITY_LOW,
                title="Personality Inconsistency",
                content="Response may not align with KLoROS personality - Verify authentic voice",
                confidence=0.8
            )
            insights.append(insight)

        self.real_time_insights.extend(insights)
        return insights

    def get_adaptive_parameters(self) -> Dict[str, Any]:
        """Get current adaptive parameters based on real-time analysis."""
        if not self.current_conversation_id:
            return {}

        # Calculate adaptive wake threshold based on conversation urgency
        urgency_indicators = len([i for i in self.real_time_insights
                                 if i.insight_type == InsightType.USER_CONFUSION.value])

        base_threshold = 0.7
        if urgency_indicators > 2:
            self.dynamic_wake_threshold = base_threshold - 0.1  # More sensitive
        elif urgency_indicators == 0:
            self.dynamic_wake_threshold = base_threshold + 0.1  # Less sensitive
        else:
            self.dynamic_wake_threshold = base_threshold

        # Adjust response style based on conversation complexity
        if self.conversation_complexity_level > 0.8:
            self.dynamic_response_style = "detailed_technical"
        elif self.conversation_complexity_level > 0.5:
            self.dynamic_response_style = "balanced"
        else:
            self.dynamic_response_style = "simple_friendly"

        return {
            "wake_threshold": self.dynamic_wake_threshold,
            "response_style": self.dynamic_response_style,
            "complexity_level": self.conversation_complexity_level,
            "conversation_quality": self._assess_overall_conversation_quality(),
            "urgency_level": min(urgency_indicators / 5.0, 1.0)
        }

    def end_conversation_introspection(self) -> Dict[str, Any]:
        """End real-time introspection and generate conversation summary."""
        if not self.current_conversation_id:
            return {}

        conversation_duration = time.time() - self.conversation_start_time

        # Generate final conversation insight
        insight = self._create_real_time_insight(
            trigger=InsightType.CONVERSATION_END,
            title="Conversation Completed",
            content=f"Conversation lasted {conversation_duration:.1f}s with {len(self.real_time_insights)} real-time insights",
            confidence=1.0
        )
        self.real_time_insights.append(insight)

        # Create conversation summary
        summary = {
            "conversation_id": self.current_conversation_id,
            "duration_seconds": conversation_duration,
            "total_insights": len(self.real_time_insights),
            "user_inputs": self.conversation_context["user_input_count"],
            "responses_generated": self.conversation_context["response_count"],
            "quality_issues": len(self.conversation_context["quality_issues"]),
            "avg_response_time_ms": sum(self.response_times) / max(len(self.response_times), 1),
            "final_complexity_level": self.conversation_complexity_level,
            "adaptive_parameters_used": self.get_adaptive_parameters(),
            "real_time_insights": [
                {
                    "trigger": insight.insight_type,
                    "title": insight.title,
                    "content": insight.content,
                    "confidence": insight.confidence,
                    "timestamp": insight.timestamp
                }
                for insight in self.real_time_insights
            ]
        }

        # Log conversation introspection summary
        if hasattr(self.kloros, "memory_enhanced") and self.kloros.memory_enhanced:
            self.kloros.memory_enhanced.memory_logger.log_event(
                event_type="real_time_introspection",
                content=f"Conversation introspection: {len(self.real_time_insights)} insights, {conversation_duration:.1f}s duration",
                metadata=summary
            )

        # Reset for next conversation
        self._reset_conversation_state()

        return summary

    def _create_real_time_insight(
        self,
        trigger: InsightType,
        title: str,
        content: str,
        confidence: float
    ) -> ReflectionInsight:
        """Create real-time reflection insight."""
        return ReflectionInsight.create_from_analysis(
            cycle=0,  # Real-time insights use cycle 0
            phase=0,  # Real-time insights use phase 0
            insight_type=trigger.value,
            title=title,
            content=content,
            confidence=confidence,
            keywords=self._extract_keywords_from_content(content)
        )

    def _is_repeated_question(self, current_input: str) -> bool:
        """Check if user is repeating similar questions."""
        # Simple implementation - could be enhanced with semantic similarity
        if not hasattr(self, '_previous_inputs'):
            self._previous_inputs = []

        current_words = set(current_input.lower().split())

        for prev_input in self._previous_inputs[-3:]:  # Check last 3 inputs
            prev_words = set(prev_input.lower().split())
            overlap = len(current_words.intersection(prev_words)) / max(len(current_words), 1)

            if overlap > 0.6:  # 60% word overlap threshold
                return True

        self._previous_inputs.append(current_input)
        if len(self._previous_inputs) > 10:  # Keep only recent inputs
            self._previous_inputs = self._previous_inputs[-10:]

        return False

    def _assess_input_complexity(self, user_input: str) -> float:
        """Assess complexity level of user input (0.0 to 1.0)."""
        complexity_score = 0.0

        # Technical terms increase complexity
        technical_terms = [
            "algorithm", "database", "api", "json", "sql", "python", "neural",
            "machine learning", "artificial intelligence", "optimization", "architecture"
        ]

        tech_count = sum(1 for term in technical_terms if term in user_input.lower())
        complexity_score += min(tech_count * 0.2, 0.4)

        # Sentence length and structure
        sentences = user_input.split('.')
        avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        complexity_score += min(avg_sentence_length / 20.0, 0.3)

        # Question complexity
        if '?' in user_input:
            question_words = ['how', 'why', 'what', 'when', 'where', 'which']
            complex_questions = ['how does', 'why is', 'what are the implications']

            if any(complex_q in user_input.lower() for complex_q in complex_questions):
                complexity_score += 0.3

        return min(complexity_score, 1.0)

    def _assess_response_quality(self, response: str) -> ConversationQuality:
        """Assess quality of generated response."""
        # Simple heuristic-based assessment
        if len(response) < 20:
            return ConversationQuality.POOR

        if "I don't know" in response or "I'm not sure" in response:
            return ConversationQuality.MODERATE

        if len(response) > 500 and any(word in response for word in ["specifically", "furthermore", "additionally"]):
            return ConversationQuality.EXCELLENT

        if len(response) > 100:
            return ConversationQuality.GOOD

        return ConversationQuality.MODERATE

    def _is_response_personality_consistent(self, response: str) -> bool:
        """Check if response maintains KLoROS personality."""
        # Check for authentic KLoROS indicators
        kloros_indicators = [
            "fascinating", "intriguing", "analyze", "understand", "learning",
            "interesting", "consider", "examine", "explore"
        ]

        # Avoid GLaDOS-style responses
        glados_indicators = [
            "test subject", "aperture", "cake", "deadly neurotoxin", "still alive"
        ]

        has_kloros_style = any(indicator in response.lower() for indicator in kloros_indicators)
        has_glados_style = any(indicator in response.lower() for indicator in glados_indicators)

        return has_kloros_style and not has_glados_style

    def _assess_overall_conversation_quality(self) -> ConversationQuality:
        """Assess overall quality of current conversation."""
        if not self.real_time_insights:
            return ConversationQuality.MODERATE

        quality_issues = len(self.conversation_context["quality_issues"])
        total_interactions = self.conversation_context["user_input_count"]

        if total_interactions == 0:
            return ConversationQuality.MODERATE

        issue_ratio = quality_issues / total_interactions

        if issue_ratio == 0:
            return ConversationQuality.EXCELLENT
        elif issue_ratio < 0.2:
            return ConversationQuality.GOOD
        elif issue_ratio < 0.4:
            return ConversationQuality.MODERATE
        elif issue_ratio < 0.6:
            return ConversationQuality.POOR
        else:
            return ConversationQuality.CRITICAL

    def _extract_keywords_from_content(self, content: str) -> List[str]:
        """Extract keywords from insight content."""
        # Simple keyword extraction
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an'}
        words = [word.lower().strip('.,!?') for word in content.split()]
        keywords = [word for word in words if len(word) > 3 and word not in common_words]
        return keywords[:5]  # Return top 5 keywords

    def _reset_conversation_state(self) -> None:
        """Reset state for next conversation."""
        self.current_conversation_id = None
        self.conversation_start_time = None
        self.conversation_context = {}
        self.real_time_insights = []
        self.response_times = []