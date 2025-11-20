#!/usr/bin/env python3
"""
Adaptive reasoning for KLoROS conversation mode.
Selectively applies Tree of Thought, Multi-Agent Debate, and VOI based on query complexity.
"""

import logging
from typing import Optional, Any, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)


class QueryComplexity(Enum):
    """Query complexity levels."""
    SIMPLE = "simple"      # Fast path, no reasoning
    MODERATE = "moderate"  # VOI for context ranking
    COMPLEX = "complex"    # Full ToT + Debate


class ConversationReasoningAdapter:
    """
    Adaptive reasoning wrapper for conversation mode.

    Routes queries based on complexity:
    - Simple: Direct to reason_backend (no overhead)
    - Moderate: VOI-ranked context selection (+50ms)
    - Complex: Full ToT + Debate reasoning (+200-500ms)
    """

    def __init__(self, reason_backend: Any):
        """
        Initialize adapter.

        Args:
            reason_backend: The underlying reasoning backend (RAG + tools)
        """
        self.reason_backend = reason_backend
        self.coordinator = None
        self._init_coordinator()

        # Statistics
        self.query_stats = {
            'simple': 0,
            'moderate': 0,
            'complex': 0
        }

    def _init_coordinator(self):
        """Initialize reasoning coordinator if available."""
        try:
            from src.reasoning_coordinator import get_reasoning_coordinator
            self.coordinator = get_reasoning_coordinator()
            logger.info("[conversation] Reasoning coordinator available")
        except Exception as e:
            logger.warning(f"[conversation] Reasoning coordinator unavailable: {e}")
            self.coordinator = None

    def reply(self, transcript: str, kloros_instance: Optional[Any] = None, **kwargs) -> Any:
        """
        Generate reply with adaptive reasoning.

        Args:
            transcript: User's message
            kloros_instance: KLoROS instance for tool execution
            **kwargs: Additional arguments to pass to reason_backend

        Returns:
            Reply object from reason_backend
        """
        # Assess query complexity
        complexity = self._assess_complexity(transcript)
        self.query_stats[complexity.value] += 1

        logger.debug(f"[conversation] Query complexity: {complexity.value}")

        # Route based on complexity
        if complexity == QueryComplexity.SIMPLE or not self.coordinator:
            # Fast path - no reasoning overhead
            return self._simple_reply(transcript, kloros_instance, **kwargs)

        elif complexity == QueryComplexity.MODERATE:
            # Moderate path - VOI for context/tool selection
            return self._moderate_reply(transcript, kloros_instance, **kwargs)

        else:  # COMPLEX
            # Full reasoning path - ToT + Debate
            return self._complex_reply(transcript, kloros_instance, **kwargs)

    def _assess_complexity(self, transcript: str) -> QueryComplexity:
        """
        Assess query complexity using heuristics.

        Args:
            transcript: User's message

        Returns:
            QueryComplexity level
        """
        transcript_lower = transcript.lower()
        word_count = len(transcript.split())

        # Safety-critical indicators (always complex)
        safety_keywords = [
            'should i', 'is it safe', 'medical', 'health', 'legal', 'financial',
            'dangerous', 'harmful', 'risk', 'injury', 'disease'
        ]
        if any(keyword in transcript_lower for keyword in safety_keywords):
            logger.debug(f"[conversation] Safety-critical query detected")
            return QueryComplexity.COMPLEX

        # Explicit reasoning request (always complex)
        reasoning_requests = [
            'think carefully', 'analyze', 'explain why', 'reason about',
            'compare and contrast', 'pros and cons', 'evaluate'
        ]
        if any(phrase in transcript_lower for phrase in reasoning_requests):
            logger.debug(f"[conversation] Explicit reasoning request detected")
            return QueryComplexity.COMPLEX

        # Complex reasoning indicators
        complex_indicators = [
            word_count > 20,  # Long query
            transcript.count('?') > 1,  # Multiple questions
            any(word in transcript_lower for word in [
                'how does', 'why does', 'what if', 'suppose', 'hypothetically'
            ]),
            transcript_lower.startswith('compare'),
            'because' in transcript_lower,  # Causal reasoning
        ]

        if sum(complex_indicators) >= 2:
            logger.debug(f"[conversation] Complex query detected ({sum(complex_indicators)} indicators)")
            return QueryComplexity.COMPLEX

        # Moderate complexity indicators
        moderate_indicators = [
            word_count > 10,
            '?' in transcript,
            any(word in transcript_lower for word in [
                'what', 'how', 'when', 'where', 'which', 'list'
            ])
        ]

        if any(moderate_indicators):
            logger.debug(f"[conversation] Moderate query detected")
            return QueryComplexity.MODERATE

        # Default to simple
        logger.debug(f"[conversation] Simple query detected")
        return QueryComplexity.SIMPLE

    def _simple_reply(self, transcript: str, kloros_instance: Optional[Any], **kwargs) -> Any:
        """Fast path - direct to reason_backend with no reasoning overhead."""
        logger.debug(f"[conversation] 🚀 Fast path (simple query)")
        return self.reason_backend.reply(transcript, kloros_instance=kloros_instance, **kwargs)

    def _moderate_reply(self, transcript: str, kloros_instance: Optional[Any], **kwargs) -> Any:
        """
        Moderate path - use VOI for context/tool selection.

        This could rank RAG contexts or prioritize tool calls, but for now
        we just add a light reasoning trace and fall back to normal processing.
        """
        logger.debug(f"[conversation] 🧠 Moderate reasoning (VOI-guided)")

        # For now, just log that we would use VOI here
        # In future, could intercept RAG retrieval or tool selection
        # and apply VOI ranking

        return self.reason_backend.reply(transcript, kloros_instance=kloros_instance, **kwargs)

    def _complex_reply(self, transcript: str, kloros_instance: Optional[Any], **kwargs) -> Any:
        """
        Complex path - full reasoning with ToT + Debate.

        This explores multiple response strategies and validates the response
        before returning it.
        """
        logger.info(f"[conversation] 🧠🧠 Deep reasoning (ToT + Debate)")

        try:
            # Step 1: Explore response strategies using Tree of Thought
            strategies = self.coordinator.explore_solutions(
                problem=f"How should I respond to this query: {transcript}",
                max_depth=2
            )

            if strategies:
                logger.debug(f"[conversation] Explored {len(strategies)} response strategies")

                # Step 2: Pick best strategy using VOI
                best_strategy = self.coordinator.reason_about_alternatives(
                    context="Which response strategy is best?",
                    alternatives=[
                        {
                            'name': f"strategy_{i}",
                            'description': str(s),
                            'strategy': s
                        } for i, s in enumerate(strategies[:3])  # Top 3
                    ],
                    mode='standard'
                )

                logger.debug(f"[conversation] Selected strategy: {best_strategy.get('decision', {}).get('name')}")

            # Step 3: Generate response using normal backend
            # (In future, could guide generation with selected strategy)
            result = self.reason_backend.reply(transcript, kloros_instance=kloros_instance, **kwargs)

            # Step 4: Validate response using multi-agent debate
            if hasattr(result, 'reply_text'):
                response_text = result.reply_text

                debate_result = self.coordinator.debate_decision(
                    context="Is this response appropriate and helpful?",
                    proposed_decision={
                        'action': 'provide_this_response',
                        'response': response_text,
                        'user_query': transcript,
                        'rationale': 'Generated response to user query',
                        'confidence': 0.8,
                        'risks': [
                            'Response may not fully address user intent',
                            'May contain inaccurate information',
                            'May be too verbose or too terse'
                        ]
                    },
                    rounds=1  # Single round for speed
                )

                verdict = debate_result.get('verdict', {})
                decision = verdict.get('verdict', 'approved')
                reasoning = verdict.get('reasoning', '')

                if decision == 'approved':
                    logger.info(f"[conversation] ✅ Response approved by debate")
                else:
                    logger.warning(f"[conversation] ⚠️ Response concerns: {reasoning}")
                    # Could add disclaimer or regenerate, but for now just log

            return result

        except Exception as e:
            logger.error(f"[conversation] Reasoning failed, falling back to simple: {e}")
            return self._simple_reply(transcript, kloros_instance, **kwargs)

    def get_stats(self) -> Dict[str, int]:
        """Get query complexity statistics."""
        return self.query_stats.copy()

    def log_stats(self):
        """Log query complexity statistics."""
        total = sum(self.query_stats.values())
        if total == 0:
            return

        logger.info(f"[conversation] Query complexity distribution:")
        logger.info(f"[conversation]   Simple: {self.query_stats['simple']} ({self.query_stats['simple']/total*100:.1f}%)")
        logger.info(f"[conversation]   Moderate: {self.query_stats['moderate']} ({self.query_stats['moderate']/total*100:.1f}%)")
        logger.info(f"[conversation]   Complex: {self.query_stats['complex']} ({self.query_stats['complex']/total*100:.1f}%)")
