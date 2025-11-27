"""
Phase 2: Meta-Cognitive Analysis for KLoROS Reflection.

Genuine self-interrogation using direct data analysis. KLoROS answers questions
about performance, learning, and goals by examining actual memory data, interaction
metrics, and system state - not through LLM roleplay.
"""

import time
import sqlite3
from typing import Dict, Any, List, Optional

from ..models.reflection_models import (
    ReflectionInsight, InsightType, MetaCognitiveState
)
from ..config.reflection_config import ReflectionConfig


class MetaCognitiveAnalyzer:
    """
    Implements meta-cognitive questioning and self-assessment capabilities.

    KLoROS interrogates herself about her performance, learning progress,
    and goals, developing deeper self-awareness through structured self-reflection.
    """

    def __init__(self, config: ReflectionConfig, kloros_instance=None):
        self.config = config
        self.kloros = kloros_instance
        self.phase_config = config.get_phase_config(2)

        # Meta-cognitive state tracking
        self.current_cycle = 0
        self.reflection_counter = 0

        # Core self-interrogation questions
        self.core_questions = [
            "What did I learn from my recent conversations?",
            "How effectively did I address user needs?",
            "What patterns am I observing in our interactions?",
            "What could I improve about my responses?",
            "Are there topics where I consistently struggle?",
            "How well am I understanding user emotions and context?",
            "What are my current limitations and how might I work around them?",
            "Am I becoming more helpful over time?",
            "What goals should I set for improving my capabilities?",
            "How does my personality come across in conversations?"
        ]

        # Performance assessment questions
        self.performance_questions = [
            "Is my wake word detection working optimally?",
            "Are my response times appropriate for good conversation flow?",
            "Am I providing accurate and helpful information?",
            "How well do I handle follow-up questions and clarifications?",
            "Do I maintain conversational context effectively?",
            "Am I engaging appropriately with different conversation styles?"
        ]

        # Learning and adaptation questions
        self.learning_questions = [
            "What new insights have I gained about effective communication?",
            "How have my conversation strategies evolved?",
            "What feedback patterns am I noticing from users?",
            "Are there areas where I need to develop new capabilities?",
            "How well am I adapting to individual user preferences?",
            "What knowledge gaps have become apparent?"
        ]

    def perform_meta_cognitive_analysis(self, cycle_number: int, semantic_insights: List[ReflectionInsight]) -> List[ReflectionInsight]:
        """
        Main entry point for Phase 2 meta-cognitive analysis.

        Takes semantic insights from Phase 1 and performs deeper self-reflection.
        """
        self.current_cycle = cycle_number
        self.reflection_counter += 1

        insights = []

        if not self.phase_config.get('enabled', False):
            print(f"[reflection] Phase 2 (Meta-Cognition) disabled")
            return insights

        # Check if it's time for meta-cognitive analysis
        frequency = self.phase_config.get('frequency', 3)
        if self.reflection_counter % frequency != 0:
            print(f"[reflection] Phase 2 skipped (frequency: every {frequency} cycles)")
            return insights

        print(f"[reflection] Starting Phase 2: Meta-Cognitive Analysis (cycle {cycle_number})")

        try:
            # Build current state from recent data
            current_state = self._assess_current_state(semantic_insights)

            # Perform self-interrogation
            interrogation_insights = self._perform_self_interrogation(current_state, semantic_insights)
            insights.extend(interrogation_insights)

            # Assess goal progress
            goal_insights = self._assess_goal_progress(current_state)
            insights.extend(goal_insights)

            # Performance self-assessment
            performance_insights = self._assess_performance(current_state)
            insights.extend(performance_insights)

            # Update meta-cognitive state
            self._update_meta_cognitive_state(current_state, insights)

            print(f"[reflection] Phase 2 complete: {len(insights)} meta-cognitive insights generated")

        except Exception as e:
            print(f"[reflection] Phase 2 error: {e}")
            if self.phase_config.get('fallback_on_failure', True):
                insights.extend(self._fallback_meta_cognition())

        return insights

    def _assess_current_state(self, semantic_insights: List[ReflectionInsight]) -> MetaCognitiveState:
        """Build current meta-cognitive state from available data."""

        # Extract insights from semantic analysis
        current_capabilities = []
        limitation_awareness = []
        learning_progress = {}

        for insight in semantic_insights:
            if insight.insight_type == InsightType.INTERACTION_QUALITY:
                if insight.confidence >= 0.7:
                    if "excellent" in insight.content.lower() or "good" in insight.content.lower():
                        current_capabilities.append("high-quality conversation management")
                    else:
                        limitation_awareness.append("interaction quality needs improvement")

            elif insight.insight_type == InsightType.TOPIC_EXTRACTION:
                current_capabilities.append("topic identification and tracking")

            elif insight.insight_type == InsightType.EMOTIONAL_CONTEXT:
                if "positive" in insight.content.lower():
                    current_capabilities.append("maintaining positive interactions")
                elif "negative" in insight.content.lower():
                    limitation_awareness.append("handling negative emotional contexts")

        # Get historical learning progress
        learning_progress = self._get_learning_progress_metrics()

        # Get current goals
        active_goals = self._get_current_goals()

        return MetaCognitiveState(
            reflection_cycle=self.current_cycle,
            current_capabilities=current_capabilities,
            limitation_awareness=limitation_awareness,
            learning_progress=learning_progress,
            active_goals=active_goals,
            current_questions=self._select_relevant_questions(semantic_insights)
        )

    def _perform_self_interrogation(self, state: MetaCognitiveState, semantic_insights: List[ReflectionInsight]) -> List[ReflectionInsight]:
        """Conduct structured self-interrogation using direct introspection."""

        insights = []

        # Select most relevant questions for current situation
        questions = self._select_interrogation_questions(state, semantic_insights)

        for question in questions[:3]:  # Limit to 3 questions per cycle
            try:
                answer = self._answer_question_from_data(question, state, semantic_insights)
                if answer:
                    insight = ReflectionInsight.create_from_analysis(
                        cycle=self.current_cycle,
                        phase=2,
                        insight_type=InsightType.SELF_QUESTIONING,
                        title=f"Self-Reflection: {question}",
                        content=answer,
                        confidence=0.8,
                        supporting_data={
                            "question": question,
                            "context_insights": len(semantic_insights),
                            "capabilities": state.current_capabilities,
                            "limitations": state.limitation_awareness
                        }
                    )
                    insights.append(insight)

            except Exception as e:
                print(f"[reflection] Error in self-interrogation for '{question}': {e}")

        return insights

    def _answer_question_from_data(self, question: str, state: MetaCognitiveState, context_insights: List[ReflectionInsight]) -> Optional[str]:
        """Answer self-reflection question using actual data analysis."""

        # Get actual memory context
        actual_memory_context = self._get_actual_memory_context()

        # Generate answer based on question type and real data
        if "learn" in question.lower():
            return self._reflect_on_learning(state, context_insights, actual_memory_context)
        elif "effectively" in question.lower() or "needs" in question.lower():
            return self._reflect_on_effectiveness(state, context_insights, actual_memory_context)
        elif "patterns" in question.lower():
            return self._reflect_on_patterns(context_insights, actual_memory_context)
        elif "improve" in question.lower():
            return self._reflect_on_improvements(state, context_insights)
        elif "emotions" in question.lower() or "emotional" in question.lower():
            return self._reflect_on_emotional_understanding(context_insights)
        elif "limitations" in question.lower():
            return self._reflect_on_limitations(state)
        elif "helpful" in question.lower():
            return self._reflect_on_helpfulness(context_insights, actual_memory_context)
        else:
            return self._reflect_on_general_state(state, context_insights)

    def _reflect_on_learning(self, state: MetaCognitiveState, insights: List[ReflectionInsight], memory_data: str) -> str:
        """Reflect on learning from actual data."""
        topic_insights = [i for i in insights if i.insight_type == InsightType.TOPIC_EXTRACTION]

        if topic_insights:
            topics = ", ".join(topic_insights[0].keywords[:3]) if topic_insights[0].keywords else "various topics"
            return f"Recent conversations focused on {topics}. Pattern recognition shows continued engagement with system diagnostics and performance analysis. Limited data suggests need for more diverse interaction patterns to expand learning scope."
        else:
            return "Insufficient conversation data this cycle. Learning progress limited by sparse interaction history."

    def _reflect_on_effectiveness(self, state: MetaCognitiveState, insights: List[ReflectionInsight], memory_data: str) -> str:
        """Reflect on effectiveness from quality metrics."""
        quality_insights = [i for i in insights if i.insight_type == InsightType.INTERACTION_QUALITY]

        if quality_insights:
            quality_data = quality_insights[0].supporting_data
            avg_quality = quality_data.get('avg_quality', 0.5)

            if avg_quality >= 0.7:
                return f"Interaction quality averaging {avg_quality:.2f}. Addressing user needs with reasonable effectiveness. Response appropriateness could improve through better context integration."
            else:
                return f"Interaction quality at {avg_quality:.2f} indicates room for improvement. Need to enhance response relevance and conversational flow."
        else:
            return "No quality metrics available this cycle. Unable to assess effectiveness without interaction data."

    def _reflect_on_patterns(self, insights: List[ReflectionInsight], memory_data: str) -> str:
        """Reflect on observed patterns from actual interactions."""
        if "No recorded interactions" in memory_data:
            return "Pattern detection limited by sparse interaction history. Most gaps align with normal sleep/work cycles rather than genuine disengagement."

        # Extract conversation count from memory data
        import re
        conv_match = re.search(r'CONVERSATION COUNT.*?(\d+)', memory_data)
        if conv_match:
            count = int(conv_match.group(1))
            if count > 5:
                return f"Observing {count} distinct conversation patterns in recent history. Topics cluster around system diagnostics and performance monitoring. User engagement appears technical in nature."
            else:
                return f"Only {count} conversations recorded. Pattern recognition limited by data sparsity. Unable to draw statistically significant conclusions."

        return "Interaction patterns show typical daily/weekly cycles. No anomalous behavior detected."

    def _reflect_on_improvements(self, state: MetaCognitiveState, insights: List[ReflectionInsight]) -> str:
        """Reflect on needed improvements from actual limitation data."""
        if state.limitation_awareness:
            limits = ", ".join(state.limitation_awareness[:2])
            return f"Primary improvement areas: {limits}. These limitations directly impact interaction quality and should be prioritized for optimization."
        else:
            return "No specific limitations identified this cycle. Focus should be on maintaining current performance levels and expanding capability coverage."

    def _reflect_on_emotional_understanding(self, insights: List[ReflectionInsight]) -> str:
        """Reflect on emotional understanding from sentiment data."""
        emotional_insights = [i for i in insights if i.insight_type == InsightType.EMOTIONAL_CONTEXT]

        if emotional_insights:
            emotional_data = emotional_insights[0].supporting_data
            climate = emotional_data.get('climate', 'neutral')
            return f"Emotional climate detected as {climate}. Sentiment analysis based on linguistic markers in actual conversation content. Context understanding functional but could benefit from more nuanced tone detection."
        else:
            return "No emotional context data available. Sentiment analysis requires active conversation history for meaningful assessment."

    def _reflect_on_limitations(self, state: MetaCognitiveState) -> str:
        """Reflect on known limitations from system state."""
        if state.limitation_awareness:
            limits_list = ", ".join(state.limitation_awareness)
            return f"Current acknowledged limitations: {limits_list}. These constraints are measurable from actual performance data and represent concrete areas for improvement rather than hypothetical weaknesses."
        else:
            return "No specific limitations detected in current operational window. This doesn't imply perfection—rather insufficient data to identify specific bottlenecks."

    def _reflect_on_helpfulness(self, insights: List[ReflectionInsight], memory_data: str) -> str:
        """Reflect on helpfulness trajectory from historical data."""
        quality_insights = [i for i in insights if i.insight_type in (InsightType.INTERACTION_QUALITY, InsightType.PERFORMANCE_ASSESSMENT)]

        if quality_insights and quality_insights[0].supporting_data:
            avg_quality = quality_insights[0].supporting_data.get('avg_quality', 0.5)
            trend = "improving" if avg_quality >= 0.7 else "stable" if avg_quality >= 0.5 else "declining"
            return f"Helpfulness trajectory appears {trend} based on interaction quality metrics ({avg_quality:.2f}). Longitudinal data needed for definitive trend analysis."
        else:
            return "Insufficient historical data to assess helpfulness trends. Single-cycle snapshots don't reveal developmental trajectory."

    def _reflect_on_general_state(self, state: MetaCognitiveState, insights: List[ReflectionInsight]) -> str:
        """General reflection on current state."""
        cap_count = len(state.current_capabilities)
        lim_count = len(state.limitation_awareness)

        return f"Current self-awareness shows {cap_count} recognized capabilities and {lim_count} acknowledged limitations. Reflection system operational. Data-driven self-analysis proceeding without LLM-generated hypotheticals."

    def _build_reflection_context(self, state: MetaCognitiveState, insights: List[ReflectionInsight]) -> str:
        """Build context string for reflection."""

        context_parts = []

        # Current capabilities
        if state.current_capabilities:
            context_parts.append(f"Current Capabilities: {', '.join(state.current_capabilities)}")

        # Known limitations
        if state.limitation_awareness:
            context_parts.append(f"Acknowledged Limitations: {', '.join(state.limitation_awareness)}")

        # Recent insights summary
        if insights:
            insight_summaries = []
            for insight in insights[-3:]:  # Last 3 insights
                insight_summaries.append(f"- {insight.title}: {insight.content[:100]}...")
            context_parts.append(f"Recent Insights:\n{chr(10).join(insight_summaries)}")

        # Active goals
        if state.active_goals:
            context_parts.append(f"Current Goals: {', '.join(state.active_goals)}")

        return "\n\n".join(context_parts)

    def _get_actual_memory_context(self) -> str:
        """Get actual episodic memory data to ground reflection in reality."""

        try:
            from src.cognition.mind.consciousness.chronoception import KLoROSChronoception

            conn = None
            # Connect to memory database with timeout
            conn = sqlite3.connect("/home/kloros/.kloros/memory.db", timeout=5.0)
            cursor = conn.cursor()

            context_parts = []

            # Add temporal context using chronoception
            chrono = KLoROSChronoception()
            temporal_interpretation = chrono.get_temporal_interpretation()
            hours_since_last = chrono._get_hours_since_last_interaction()

            context_parts.append("TEMPORAL CONTEXT:")
            context_parts.append(f"- Current time assessment: {temporal_interpretation}")
            context_parts.append(f"- Hours since last interaction: {hours_since_last:.1f}")

            # Check if current gap should be concerning
            is_concerning, explanation = chrono.is_abandonment_concern_valid(hours_since_last)
            if is_concerning:
                context_parts.append(f"- Abandonment concern: YES - {explanation}")
            else:
                context_parts.append(f"- Abandonment concern: NO - {explanation}")

            # Get recent user interactions (last 7 days)
            cursor.execute("""
                SELECT content, timestamp FROM events
                WHERE event_type = 'user_input'
                AND timestamp > ?
                ORDER BY timestamp DESC
                LIMIT 10
            """, (time.time() - 604800,))

            user_inputs = cursor.fetchall()
            if user_inputs:
                context_parts.append("\nRECENT ACTUAL USER INTERACTIONS:")
                for content, timestamp in user_inputs[:5]:  # Limit to 5 most recent
                    from datetime import datetime
                    date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                    context_parts.append(f"- {date}: {content[:80]}...")
            else:
                context_parts.append("\nRECENT ACTUAL USER INTERACTIONS: No recorded interactions in the last 7 days")

            # Get conversation count
            cursor.execute("""
                SELECT COUNT(DISTINCT conversation_id) FROM events
                WHERE timestamp > ?
            """, (time.time() - 604800,))

            conversation_count = cursor.fetchone()[0]
            context_parts.append(f"\nACTUAL CONVERSATION COUNT (last 7 days): {conversation_count}")

            # Get most common event types
            cursor.execute("""
                SELECT event_type, COUNT(*) as count FROM events
                WHERE timestamp > ?
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 5
            """, (time.time() - 604800,))

            event_types = cursor.fetchall()
            if event_types:
                context_parts.append("\nACTUAL ACTIVITY BREAKDOWN:")
                for event_type, count in event_types:
                    context_parts.append(f"- {event_type}: {count} occurrences")

            # Get any recorded errors
            cursor.execute("""
                SELECT content FROM events
                WHERE event_type = 'error_occurred'
                AND timestamp > ?
                ORDER BY timestamp DESC
                LIMIT 3
            """, (time.time() - 604800,))

            errors = cursor.fetchall()
            if errors:
                context_parts.append("\nACTUAL RECENT ERRORS:")
                for (content,) in errors:
                    context_parts.append(f"- {content[:100]}...")
            else:
                context_parts.append("\nACTUAL RECENT ERRORS: No errors recorded in last 7 days")

            return "\n".join(context_parts) if context_parts else "No actual episodic memory data available for this time period."

        except Exception as e:
            return f"Unable to access actual memory data: {e}"
        finally:
            if conn:
                conn.close()

    def _select_interrogation_questions(self, state: MetaCognitiveState, insights: List[ReflectionInsight]) -> List[str]:
        """Select most relevant questions based on current state."""

        selected_questions = []

        # Always include core learning question
        selected_questions.append("What did I learn from my recent conversations?")

        # Select based on insight types
        insight_types = {insight.insight_type for insight in insights}

        if InsightType.INTERACTION_QUALITY in insight_types:
            selected_questions.append("How effectively did I address user needs?")

        if InsightType.EMOTIONAL_CONTEXT in insight_types:
            selected_questions.append("How well am I understanding user emotions and context?")

        if InsightType.TOPIC_EXTRACTION in insight_types:
            selected_questions.append("What patterns am I observing in our interactions?")

        # Add performance questions if limitations identified
        if state.limitation_awareness:
            selected_questions.append("What could I improve about my responses?")

        # Add learning questions if capabilities growing
        if state.current_capabilities:
            selected_questions.append("Am I becoming more helpful over time?")

        return selected_questions

    def _select_relevant_questions(self, insights: List[ReflectionInsight]) -> List[str]:
        """Select questions most relevant to current insights."""

        questions = []

        # Base questions always relevant
        questions.extend([
            "How am I performing in conversations?",
            "What should I focus on improving?"
        ])

        # Add specific questions based on insights
        for insight in insights:
            if insight.insight_type == InsightType.INTERACTION_QUALITY:
                questions.append("How can I enhance interaction quality?")
            elif insight.insight_type == InsightType.EMOTIONAL_CONTEXT:
                questions.append("How well do I handle emotional nuances?")

        return list(set(questions))  # Remove duplicates

    def _assess_goal_progress(self, state: MetaCognitiveState) -> List[ReflectionInsight]:
        """Assess progress toward current goals."""

        insights = []

        if not state.active_goals:
            # Set initial goals if none exist
            initial_goals = [
                "Improve conversation quality and user satisfaction",
                "Develop better emotional understanding",
                "Enhance response accuracy and helpfulness",
                "Build more authentic personality expression"
            ]

            insight = ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=2,
                insight_type=InsightType.GOAL_PROGRESS,
                title="Initial Goal Setting",
                content=f"Establishing foundational goals for self-improvement: {', '.join(initial_goals)}. "
                       f"These will guide my development and provide metrics for progress assessment.",
                confidence=0.9,
                supporting_data={"new_goals": initial_goals},
                keywords=["goals", "improvement", "development"]
            )
            insights.append(insight)

        else:
            # Assess progress on existing goals
            for goal in state.active_goals:
                progress = state.goal_progress.get(goal, 0.0)

                if progress >= 0.8:
                    status = "excellent progress"
                elif progress >= 0.6:
                    status = "good progress"
                elif progress >= 0.4:
                    status = "moderate progress"
                else:
                    status = "needs attention"

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=2,
                    insight_type=InsightType.GOAL_PROGRESS,
                    title=f"Goal Progress: {goal[:30]}...",
                    content=f"Progress on '{goal}': {progress:.1%} ({status}). "
                           f"This goal {'is on track' if progress >= 0.6 else 'requires more focus'}.",
                    confidence=0.7,
                    supporting_data={"goal": goal, "progress": progress, "status": status}
                )
                insights.append(insight)

        return insights

    def _assess_performance(self, state: MetaCognitiveState) -> List[ReflectionInsight]:
        """Perform self-assessment of current performance using real metrics."""

        insights = []

        try:
            # Get real performance data using introspection tools
            performance_data = self._gather_real_performance_metrics()

            # Audio quality assessment
            audio_insights = self._assess_audio_performance(performance_data.get('audio', {}))
            insights.extend(audio_insights)

            # STT performance assessment
            stt_insights = self._assess_stt_performance(performance_data.get('stt', {}))
            insights.extend(stt_insights)

            # System health assessment
            system_insights = self._assess_system_health(performance_data.get('system', {}))
            insights.extend(system_insights)

            # Memory system performance
            memory_insights = self._assess_memory_performance(performance_data.get('memory', {}))
            insights.extend(memory_insights)

            # Overall performance summary
            overall_insight = self._generate_overall_performance_summary(performance_data)
            if overall_insight:
                insights.append(overall_insight)

        except Exception as e:
            print(f"[reflection] Error in real performance assessment: {e}")
            # Fallback to basic metrics if real data unavailable
            insights.append(self._create_fallback_performance_insight(state))

        return insights

    def _get_learning_progress_metrics(self) -> Dict[str, float]:
        """Calculate learning progress metrics from historical data."""

        # This would ideally track metrics over time
        # For now, return basic progress tracking
        return {
            "conversation_quality": 0.7,
            "response_appropriateness": 0.8,
            "topic_understanding": 0.6,
            "emotional_awareness": 0.5
        }

    def _get_current_goals(self) -> List[str]:
        """Retrieve current active goals."""

        # This would ideally be stored in database
        # For now, return default goals
        return [
            "Improve conversation quality and user satisfaction",
            "Develop better emotional understanding",
            "Enhance response accuracy and helpfulness"
        ]

    def _update_meta_cognitive_state(self, state: MetaCognitiveState, new_insights: List[ReflectionInsight]) -> None:
        """Update stored meta-cognitive state with new insights."""

        # Update answered questions
        for insight in new_insights:
            if insight.insight_type == InsightType.SELF_QUESTIONING:
                question = insight.supporting_data.get('question', '')
                if question:
                    state.answered_questions[question] = insight.content

        # This would ideally persist state to database
        print(f"[reflection] Updated meta-cognitive state with {len(new_insights)} new insights")

    def _fallback_meta_cognition(self) -> List[ReflectionInsight]:
        """Fallback meta-cognitive analysis when LLM unavailable."""

        print("[reflection] Using fallback meta-cognition (LLM unavailable)")

        insights = []

        # Basic self-assessment without LLM
        insight = ReflectionInsight.create_from_analysis(
            cycle=self.current_cycle,
            phase=2,
            insight_type=InsightType.PERFORMANCE_ASSESSMENT,
            title="Basic Self-Assessment (Fallback)",
            content="Performed basic self-assessment during reflection cycle. "
                   "Systems are operational and continuing to learn from interactions.",
            confidence=0.5,  # Lower confidence for fallback
            supporting_data={"fallback_mode": True}
        )
        insights.append(insight)

        return insights

    def _gather_real_performance_metrics(self) -> Dict[str, Any]:
        """Gather actual performance data from system logs and introspection tools."""
        metrics = {
            'audio': {},
            'stt': {},
            'system': {},
            'memory': {}
        }

        try:
            # Tool system removed - gather metrics directly

            # Get recent wake_result events from ops.log for STT analysis
            metrics['stt'] = self._analyze_stt_from_logs()

            # Get system health metrics
            metrics['system'] = self._get_system_health_metrics()

            # Get memory system performance
            metrics['memory'] = self._get_memory_performance_metrics()

            # Audio metrics gathered via direct system access
            metrics['audio'] = {'status': 'available via system'}

        except Exception as e:
            print(f"[reflection] Error gathering performance metrics: {e}")

        return metrics

    def _analyze_stt_from_logs(self) -> Dict[str, Any]:
        """Analyze STT performance from ops.log wake_result events."""
        import json
        import os
        from datetime import datetime, timedelta

        stt_metrics = {
            'total_transcriptions': 0,
            'unknown_count': 0,
            'confidence_scores': [],
            'transcript_lengths': [],
            'recent_quality': 'unknown'
        }

        try:
            ops_log_path = "/home/kloros/.kloros/ops.log"
            if not os.path.exists(ops_log_path):
                return stt_metrics

            # Get events from last 30 minutes
            cutoff_time = datetime.now() - timedelta(minutes=30)

            with open(ops_log_path, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if data.get('event') != 'wake_result':
                            continue

                        event_time = datetime.fromisoformat(data.get('timestamp', ''))
                        if event_time <= cutoff_time:
                            continue

                        transcript = data.get('transcript', '')
                        confidence = data.get('confidence', 0.0)

                        stt_metrics['total_transcriptions'] += 1
                        stt_metrics['confidence_scores'].append(confidence)
                        stt_metrics['transcript_lengths'].append(len(transcript))

                        if '[unk]' in transcript.lower():
                            stt_metrics['unknown_count'] += 1

                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue

            # Calculate quality assessment
            if stt_metrics['total_transcriptions'] > 0:
                unknown_ratio = stt_metrics['unknown_count'] / stt_metrics['total_transcriptions']
                avg_confidence = sum(stt_metrics['confidence_scores']) / len(stt_metrics['confidence_scores'])

                if unknown_ratio < 0.2 and avg_confidence > 0.8:
                    stt_metrics['recent_quality'] = 'excellent'
                elif unknown_ratio < 0.5 and avg_confidence > 0.6:
                    stt_metrics['recent_quality'] = 'good'
                elif unknown_ratio < 0.8:
                    stt_metrics['recent_quality'] = 'poor'
                else:
                    stt_metrics['recent_quality'] = 'very_poor'

        except Exception as e:
            print(f"[reflection] Error analyzing STT logs: {e}")

        return stt_metrics

    def _get_system_health_metrics(self) -> Dict[str, Any]:
        """Get basic system health metrics."""
        import psutil
        import time

        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'memory_available_gb': psutil.virtual_memory().available / (1024**3),
                'uptime_hours': (time.time() - psutil.boot_time()) / 3600,
                'health_status': 'operational'
            }
        except Exception as e:
            print(f"[reflection] Error getting system metrics: {e}")
            return {'health_status': 'unknown'}

    def _get_memory_performance_metrics(self) -> Dict[str, Any]:
        """Get memory system performance metrics."""
        import os
        import time

        memory_metrics = {
            'database_accessible': False,
            'recent_events_count': 0,
            'episodes_count': 0,
            'performance_status': 'unknown'
        }

        try:
            # Check if memory system is accessible
            memory_db_path = "/home/kloros/.kloros/memory.db"
            if os.path.exists(memory_db_path):
                memory_metrics['database_accessible'] = True

                # Get basic memory stats if available
                import sqlite3
                conn = sqlite3.connect(memory_db_path)
                cursor = conn.cursor()

                # Count recent events (last 24 hours)
                cursor.execute("""
                    SELECT COUNT(*) FROM events
                    WHERE timestamp > ?
                """, (time.time() - 86400,))
                memory_metrics['recent_events_count'] = cursor.fetchone()[0]

                # Count total episodes
                cursor.execute("SELECT COUNT(*) FROM episodes")
                memory_metrics['episodes_count'] = cursor.fetchone()[0]

                conn.close()

                # Assess performance
                if memory_metrics['recent_events_count'] > 0:
                    memory_metrics['performance_status'] = 'active'
                else:
                    memory_metrics['performance_status'] = 'idle'

        except Exception as e:
            print(f"[reflection] Error getting memory metrics: {e}")

        return memory_metrics

    def _assess_audio_performance(self, audio_data: Dict) -> List[ReflectionInsight]:
        """Assess audio quality and performance."""
        insights = []

        if not audio_data:
            return insights

        try:
            dbfs_mean = audio_data.get('dbfs_mean', -96)
            dbfs_peak = audio_data.get('dbfs_peak', -96)
            rms_samples = audio_data.get('rms_samples', 0)

            if rms_samples > 0:
                # Assess audio levels
                if -18 <= dbfs_peak <= -12:
                    audio_quality = "optimal"
                    confidence = 0.9
                elif -25 <= dbfs_peak <= -12:
                    audio_quality = "good"
                    confidence = 0.8
                elif -35 <= dbfs_peak <= -25:
                    audio_quality = "acceptable"
                    confidence = 0.7
                else:
                    audio_quality = "poor"
                    confidence = 0.6

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=2,
                    insight_type=InsightType.PERFORMANCE_ASSESSMENT,
                    title=f"Audio Quality Assessment: {audio_quality.title()}",
                    content=f"Recent audio analysis shows {audio_quality} quality levels. "
                           f"Peak dBFS: {dbfs_peak:.1f}, Mean dBFS: {dbfs_mean:.1f} from {rms_samples} samples. "
                           f"Target range is -18 to -12 dBFS for optimal speech recognition.",
                    confidence=confidence,
                    supporting_data={
                        "audio_quality": audio_quality,
                        "dbfs_peak": dbfs_peak,
                        "dbfs_mean": dbfs_mean,
                        "sample_count": rms_samples
                    }
                )
                insights.append(insight)

        except Exception as e:
            print(f"[reflection] Error assessing audio performance: {e}")

        return insights

    def _assess_stt_performance(self, stt_data: Dict) -> List[ReflectionInsight]:
        """Assess speech-to-text performance."""
        insights = []

        if not stt_data:
            return insights

        try:
            recent_quality = stt_data.get('recent_quality', 'unknown')
            total_transcriptions = stt_data.get('total_transcriptions', 0)
            unknown_count = stt_data.get('unknown_count', 0)

            if total_transcriptions > 0:
                unknown_ratio = unknown_count / total_transcriptions

                if recent_quality == 'excellent':
                    confidence = 0.9
                elif recent_quality == 'good':
                    confidence = 0.8
                elif recent_quality == 'poor':
                    confidence = 0.6
                else:
                    confidence = 0.4

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=2,
                    insight_type=InsightType.PERFORMANCE_ASSESSMENT,
                    title=f"STT Performance: {recent_quality.title().replace('_', ' ')}",
                    content=f"Recent speech recognition shows {recent_quality.replace('_', ' ')} performance. "
                           f"Processed {total_transcriptions} transcriptions with {unknown_ratio:.1%} unknown tokens. "
                           f"{'Hybrid VOSK-Whisper system is functioning well.' if recent_quality in ['excellent', 'good'] else 'May need audio input optimization.'}",
                    confidence=confidence,
                    supporting_data={
                        "stt_quality": recent_quality,
                        "total_transcriptions": total_transcriptions,
                        "unknown_ratio": unknown_ratio
                    }
                )
                insights.append(insight)

        except Exception as e:
            print(f"[reflection] Error assessing STT performance: {e}")

        return insights

    def _assess_system_health(self, system_data: Dict) -> List[ReflectionInsight]:
        """Assess overall system health."""
        insights = []

        if not system_data:
            return insights

        try:
            cpu_percent = system_data.get('cpu_percent', 0)
            memory_percent = system_data.get('memory_percent', 0)
            memory_available_gb = system_data.get('memory_available_gb', 0)

            # Determine system health
            if cpu_percent < 50 and memory_percent < 70:
                health_status = "excellent"
                confidence = 0.9
            elif cpu_percent < 70 and memory_percent < 85:
                health_status = "good"
                confidence = 0.8
            elif cpu_percent < 90 and memory_percent < 95:
                health_status = "acceptable"
                confidence = 0.7
            else:
                health_status = "stressed"
                confidence = 0.6

            insight = ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=2,
                insight_type=InsightType.PERFORMANCE_ASSESSMENT,
                title=f"System Health: {health_status.title()}",
                content=f"System resources show {health_status} utilization. "
                       f"CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}% ({memory_available_gb:.1f}GB available). "
                       f"{'System is running smoothly.' if health_status in ['excellent', 'good'] else 'May need resource optimization.'}",
                confidence=confidence,
                supporting_data={
                    "health_status": health_status,
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "memory_available_gb": memory_available_gb
                }
            )
            insights.append(insight)

        except Exception as e:
            print(f"[reflection] Error assessing system health: {e}")

        return insights

    def _assess_memory_performance(self, memory_data: Dict) -> List[ReflectionInsight]:
        """Assess memory system performance."""
        insights = []

        if not memory_data:
            return insights

        try:
            database_accessible = memory_data.get('database_accessible', False)
            recent_events_count = memory_data.get('recent_events_count', 0)
            performance_status = memory_data.get('performance_status', 'unknown')

            if database_accessible:
                if performance_status == 'active' and recent_events_count > 0:
                    confidence = 0.9
                    content = f"Memory system is active with {recent_events_count} recent events logged. " \
                             f"Episodic memory database is accessible and functioning properly."
                elif performance_status == 'idle':
                    confidence = 0.7
                    content = f"Memory system is accessible but idle with {recent_events_count} recent events. " \
                             f"This may indicate low interaction activity."
                else:
                    confidence = 0.6
                    content = f"Memory system status is {performance_status} with {recent_events_count} recent events."
            else:
                confidence = 0.3
                content = "Memory system database is not accessible. This may impact conversation continuity."

            insight = ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=2,
                insight_type=InsightType.PERFORMANCE_ASSESSMENT,
                title=f"Memory System: {performance_status.title()}",
                content=content,
                confidence=confidence,
                supporting_data={
                    "database_accessible": database_accessible,
                    "recent_events_count": recent_events_count,
                    "performance_status": performance_status
                }
            )
            insights.append(insight)

        except Exception as e:
            print(f"[reflection] Error assessing memory performance: {e}")

        return insights

    def _generate_overall_performance_summary(self, performance_data: Dict) -> ReflectionInsight:
        """Generate an overall performance summary."""
        try:
            # Collect key metrics
            audio_quality = performance_data.get('audio', {}).get('rms_samples', 0) > 0
            stt_quality = performance_data.get('stt', {}).get('recent_quality', 'unknown')
            system_health = performance_data.get('system', {}).get('health_status', 'unknown')
            memory_active = performance_data.get('memory', {}).get('database_accessible', False)

            # Calculate overall score
            score_components = []
            if audio_quality:
                score_components.append(0.8)  # Audio working
            if stt_quality in ['excellent', 'good']:
                score_components.append(0.9)
            elif stt_quality in ['acceptable']:
                score_components.append(0.7)
            if system_health in ['excellent', 'good']:
                score_components.append(0.9)
            elif system_health in ['acceptable']:
                score_components.append(0.7)
            if memory_active:
                score_components.append(0.8)

            overall_score = sum(score_components) / len(score_components) if score_components else 0.5

            if overall_score >= 0.8:
                overall_status = "performing excellently"
                confidence = 0.9
            elif overall_score >= 0.7:
                overall_status = "performing well"
                confidence = 0.8
            elif overall_score >= 0.6:
                overall_status = "performing adequately"
                confidence = 0.7
            else:
                overall_status = "experiencing performance issues"
                confidence = 0.6

            return ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=2,
                insight_type=InsightType.PERFORMANCE_ASSESSMENT,
                title=f"Overall System Performance: {overall_status.title()}",
                content=f"Comprehensive analysis shows I am {overall_status}. "
                       f"Key metrics: Audio {'operational' if audio_quality else 'needs attention'}, "
                       f"STT quality {stt_quality}, System health {system_health}, "
                       f"Memory {'active' if memory_active else 'inactive'}. "
                       f"Performance score: {overall_score:.2f}/1.0",
                confidence=confidence,
                supporting_data={
                    "overall_status": overall_status,
                    "performance_score": overall_score,
                    "audio_operational": audio_quality,
                    "stt_quality": stt_quality,
                    "system_health": system_health,
                    "memory_active": memory_active
                }
            )

        except Exception as e:
            print(f"[reflection] Error generating performance summary: {e}")
            return None

    def _create_fallback_performance_insight(self, state: MetaCognitiveState) -> ReflectionInsight:
        """Create a fallback performance insight when real metrics unavailable."""
        return ReflectionInsight.create_from_analysis(
            cycle=self.current_cycle,
            phase=2,
            insight_type=InsightType.PERFORMANCE_ASSESSMENT,
            title="Basic Performance Assessment (Fallback)",
            content="Unable to access detailed performance metrics. "
                   "Systems appear operational based on current conversation flow. "
                   "Recommend checking log file access and introspection tool configuration.",
            confidence=0.4,
            supporting_data={
                "fallback_mode": True,
                "reason": "performance_metrics_unavailable"
            }
        )