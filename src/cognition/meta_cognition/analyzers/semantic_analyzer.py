"""
Phase 1: Semantic Analysis for KLoROS Reflection System.

Direct introspective analysis using actual conversation data, performance metrics,
and linguistic pattern detection. No LLM dependency - genuine self-examination
based on measurable interaction patterns and objective quality indicators.
"""

import time
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..models.reflection_models import (
    ReflectionInsight, InsightType, ConversationAnalysis
)
from ..config.reflection_config import ReflectionConfig


class SemanticAnalyzer:
    """
    Analyzes conversation content using LLM for semantic understanding.

    Extracts meaningful themes, user intents, interaction quality,
    and emotional context from recent conversations.
    """

    def __init__(self, config: ReflectionConfig, kloros_instance=None):
        self.config = config
        self.kloros = kloros_instance
        self.phase_config = config.get_phase_config(1)

        # Analysis state
        self.current_cycle = 0
        self.analysis_start_time = 0

    def analyze_recent_conversations(self, cycle_number: int) -> List[ReflectionInsight]:
        """
        Main entry point for Phase 1 semantic analysis.

        Returns list of insights generated from analyzing recent conversations.
        """
        self.current_cycle = cycle_number
        self.analysis_start_time = time.time()

        insights = []

        if not self.phase_config.get('enabled', False):
            print(f"[reflection] Phase 1 (Semantic Analysis) disabled")
            return insights

        print(f"[reflection] Starting Phase 1: Semantic Analysis (cycle {cycle_number})")

        try:
            # Get recent conversation data
            conversations = self._get_recent_conversations()
            if not conversations:
                print(f"[reflection] No recent conversations to analyze")
                return insights

            print(f"[reflection] Analyzing {len(conversations)} recent conversations")

            # Analyze each conversation for themes and quality
            conversation_analyses = []
            for conv in conversations:
                analysis = self._analyze_conversation_content(conv)
                if analysis:
                    conversation_analyses.append(analysis)

            # Generate insights from conversation analyses
            if conversation_analyses:
                insights.extend(self._generate_topic_insights(conversation_analyses))
                insights.extend(self._generate_quality_insights(conversation_analyses))
                insights.extend(self._generate_intent_insights(conversation_analyses))
                insights.extend(self._generate_emotional_insights(conversation_analyses))

            processing_time = (time.time() - self.analysis_start_time) * 1000
            print(f"[reflection] Phase 1 complete: {len(insights)} insights generated in {processing_time:.1f}ms")

        except Exception as e:
            print(f"[reflection] Phase 1 error: {e}")
            if self.phase_config.get('fallback_on_failure', True):
                insights.extend(self._fallback_analysis())

        return insights

    def _get_recent_conversations(self) -> List[Dict[str, Any]]:
        """Retrieve recent conversation data from memory database."""
        conversations = []

        conn = None
        try:
            # Calculate lookback time
            lookback_hours = self.phase_config.get('lookback_hours', 24)
            cutoff_time = time.time() - (lookback_hours * 3600)

            # Connect to memory database with timeout
            conn = sqlite3.connect("/home/kloros/.kloros/memory.db", timeout=5.0)
            cursor = conn.cursor()

            # Get conversation groups from recent events
            cursor.execute("""
                SELECT conversation_id,
                       GROUP_CONCAT(content, ' | ') as combined_content,
                       COUNT(*) as event_count,
                       MIN(timestamp) as start_time,
                       MAX(timestamp) as end_time
                FROM events
                WHERE timestamp > ?
                  AND event_type IN ('user_input', 'llm_response')
                  AND conversation_id IS NOT NULL
                GROUP BY conversation_id
                ORDER BY start_time DESC
                LIMIT ?
            """, (cutoff_time, self.phase_config.get('batch_size', 20)))

            rows = cursor.fetchall()

            for row in rows:
                conv_id, content, event_count, start_time, end_time = row

                # Get individual events for this conversation
                cursor.execute("""
                    SELECT event_type, content, timestamp
                    FROM events
                    WHERE conversation_id = ?
                      AND event_type IN ('user_input', 'llm_response')
                    ORDER BY timestamp
                """, (conv_id,))

                events = cursor.fetchall()

                conversations.append({
                    'conversation_id': conv_id,
                    'combined_content': content,
                    'event_count': event_count,
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': end_time - start_time,
                    'events': [
                        {'type': evt[0], 'content': evt[1], 'timestamp': evt[2]}
                        for evt in events
                    ]
                })

        except Exception as e:
            print(f"[reflection] Error retrieving conversations: {e}")
        finally:
            if conn:
                conn.close()

        return conversations

    def _analyze_conversation_content(self, conversation: Dict[str, Any]) -> Optional[ConversationAnalysis]:
        """Analyze conversation using direct introspective analysis (no LLM)."""

        try:
            # Extract actual metrics from conversation data
            topics = self._extract_topics_from_keywords(conversation)
            themes = self._identify_themes_from_patterns(conversation)
            user_intent = self._infer_user_intent(conversation)
            emotional_tone = self._detect_emotional_tone(conversation)

            # Calculate objective quality metrics
            interaction_quality = self._calculate_interaction_quality(conversation)
            response_appropriateness = self._assess_response_appropriateness(conversation)

            # Identify actual signals from conversation
            satisfaction_signals = self._detect_satisfaction_signals(conversation)
            knowledge_gaps = self._identify_knowledge_gaps(conversation)
            improvement_areas = self._identify_improvement_areas(conversation)

            # Create ConversationAnalysis from real data
            analysis = ConversationAnalysis(
                conversation_id=conversation['conversation_id'],
                topics=topics,
                themes=themes,
                user_intent=user_intent,
                emotional_tone=emotional_tone,
                interaction_quality=interaction_quality,
                response_appropriateness=response_appropriateness,
                user_satisfaction_signals=satisfaction_signals,
                knowledge_gaps=knowledge_gaps,
                improvement_areas=improvement_areas
            )

            # Calculate timing metrics from actual events
            analysis.response_time_avg = self._calculate_avg_response_time(conversation['events'])
            analysis.interruption_count = self._count_interruptions(conversation['events'])
            analysis.clarification_requests = self._count_clarifications(conversation['events'])

            return analysis

        except Exception as e:
            print(f"[reflection] Error analyzing conversation {conversation['conversation_id']}: {e}")
            return None

    def _extract_topics_from_keywords(self, conversation: Dict[str, Any]) -> List[str]:
        """Extract topics using keyword analysis from actual conversation content."""
        combined_text = conversation['combined_content'].lower()

        # Technical/system topics
        topic_keywords = {
            'system': ['system', 'diagnostic', 'status', 'component', 'pipeline'],
            'audio': ['audio', 'microphone', 'speaker', 'sound', 'voice', 'tts', 'stt'],
            'memory': ['memory', 'remember', 'recall', 'episodic', 'conversation'],
            'reflection': ['reflection', 'thinking', 'analysis', 'introspection'],
            'performance': ['performance', 'speed', 'quality', 'optimization'],
            'enrollment': ['enrollment', 'enroll', 'register', 'speaker'],
            'configuration': ['config', 'setting', 'parameter', 'environment'],
            'error': ['error', 'issue', 'problem', 'debug', 'fix']
        }

        topics = []
        for topic, keywords in topic_keywords.items():
            if any(kw in combined_text for kw in keywords):
                topics.append(topic)

        return topics[:5]  # Limit to top 5

    def _identify_themes_from_patterns(self, conversation: Dict[str, Any]) -> List[str]:
        """Identify conversation themes from interaction patterns."""
        themes = []
        events = conversation['events']

        # Check for diagnostic/troubleshooting theme
        if any('status' in e['content'].lower() or 'check' in e['content'].lower() for e in events):
            themes.append('system_diagnostics')

        # Check for learning/configuration theme
        if any('how' in e['content'].lower() or 'what' in e['content'].lower() for e in events if e['type'] == 'user_input'):
            themes.append('information_seeking')

        # Check for problem-solving theme
        if any('error' in e['content'].lower() or 'issue' in e['content'].lower() for e in events):
            themes.append('troubleshooting')

        return themes

    def _infer_user_intent(self, conversation: Dict[str, Any]) -> str:
        """Infer primary user intent from conversation structure."""
        events = conversation['events']
        if not events:
            return "unknown"

        first_user_input = next((e['content'].lower() for e in events if e['type'] == 'user_input'), '')

        # Pattern matching on first input
        if any(word in first_user_input for word in ['how', 'what', 'when', 'where', 'why']):
            return "seeking_information"
        elif any(word in first_user_input for word in ['check', 'status', 'diagnostic']):
            return "system_inspection"
        elif any(word in first_user_input for word in ['fix', 'solve', 'help', 'issue']):
            return "problem_solving"
        elif any(word in first_user_input for word in ['enroll', 'register', 'add']):
            return "configuration_change"
        else:
            return "general_interaction"

    def _detect_emotional_tone(self, conversation: Dict[str, Any]) -> str:
        """Detect emotional tone from linguistic markers."""
        combined_text = conversation['combined_content'].lower()

        positive_markers = ['thank', 'great', 'good', 'excellent', 'perfect', 'appreciate']
        negative_markers = ['bad', 'wrong', 'error', 'issue', 'problem', 'frustrat']

        positive_count = sum(1 for marker in positive_markers if marker in combined_text)
        negative_count = sum(1 for marker in negative_markers if marker in combined_text)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        elif positive_count > 0 and negative_count > 0:
            return "mixed"
        else:
            return "neutral"

    def _calculate_interaction_quality(self, conversation: Dict[str, Any]) -> float:
        """Calculate interaction quality from objective metrics."""
        score = 0.5  # Base score

        # Positive factors
        if conversation['event_count'] >= 4:  # Sustained conversation
            score += 0.2
        if conversation['duration'] >= 10:  # Meaningful duration
            score += 0.1

        # Check for completion indicators
        combined_text = conversation['combined_content'].lower()
        if any(marker in combined_text for marker in ['thank', 'good', 'perfect']):
            score += 0.2

        return min(1.0, score)

    def _assess_response_appropriateness(self, conversation: Dict[str, Any]) -> float:
        """Assess response appropriateness from conversation flow."""
        events = conversation['events']
        if len(events) < 2:
            return 0.5

        score = 0.7  # Base score

        # Check for no interruptions (good flow)
        if self._count_interruptions(events) == 0:
            score += 0.2

        # Check for no clarification requests (understood well)
        if self._count_clarifications(events) == 0:
            score += 0.1

        return min(1.0, score)

    def _detect_satisfaction_signals(self, conversation: Dict[str, Any]) -> List[str]:
        """Detect actual satisfaction signals from conversation."""
        combined_text = conversation['combined_content'].lower()
        signals = []

        signal_markers = {
            'thank you': 'gratitude_expressed',
            'thanks': 'gratitude_expressed',
            'good': 'positive_feedback',
            'great': 'positive_feedback',
            'perfect': 'positive_feedback',
            'excellent': 'positive_feedback'
        }

        for marker, signal in signal_markers.items():
            if marker in combined_text and signal not in signals:
                signals.append(signal)

        return signals

    def _identify_knowledge_gaps(self, conversation: Dict[str, Any]) -> List[str]:
        """Identify knowledge gaps from conversation patterns."""
        gaps = []
        combined_text = conversation['combined_content'].lower()

        # Check for uncertainty indicators in KLoROS responses
        uncertainty_markers = ['not sure', 'unclear', 'unable to', 'cannot', "don't know"]
        for marker in uncertainty_markers:
            if marker in combined_text:
                gaps.append(f"uncertainty_expressed: {marker}")

        return gaps

    def _identify_improvement_areas(self, conversation: Dict[str, Any]) -> List[str]:
        """Identify improvement areas from conversation metrics."""
        improvements = []

        # Slow response time
        avg_response_time = self._calculate_avg_response_time(conversation['events'])
        if avg_response_time > 5.0:
            improvements.append('reduce_response_time')

        # Interruptions present
        if self._count_interruptions(conversation['events']) > 0:
            improvements.append('reduce_interruptions')

        # Clarifications needed
        if self._count_clarifications(conversation['events']) > 0:
            improvements.append('improve_clarity')

        return improvements

    def _calculate_avg_response_time(self, events: List[Dict[str, Any]]) -> float:
        """Calculate average response time between user input and KLoROS response."""

        response_times = []
        last_user_time = None

        for event in events:
            if event['type'] == 'user_input':
                last_user_time = event['timestamp']
            elif event['type'] == 'llm_response' and last_user_time:
                response_time = event['timestamp'] - last_user_time
                response_times.append(response_time)
                last_user_time = None

        return sum(response_times) / len(response_times) if response_times else 0.0

    def _count_interruptions(self, events: List[Dict[str, Any]]) -> int:
        """Count conversation interruptions (consecutive user inputs)."""

        interruptions = 0
        last_type = None

        for event in events:
            if event['type'] == 'user_input' and last_type == 'user_input':
                interruptions += 1
            last_type = event['type']

        return interruptions

    def _count_clarifications(self, events: List[Dict[str, Any]]) -> int:
        """Count clarification requests in conversation."""

        clarification_keywords = [
            'what do you mean', 'can you clarify', 'i don\'t understand',
            'could you explain', 'what was that', 'repeat that', 'huh?',
            'sorry?', 'come again', 'clarify'
        ]

        clarifications = 0

        for event in events:
            content_lower = event['content'].lower()
            if any(keyword in content_lower for keyword in clarification_keywords):
                clarifications += 1

        return clarifications

    def _generate_topic_insights(self, analyses: List[ConversationAnalysis]) -> List[ReflectionInsight]:
        """Generate insights about conversation topics and themes."""

        insights = []

        # Collect all topics and themes
        all_topics = []
        all_themes = []

        for analysis in analyses:
            all_topics.extend(analysis.topics)
            all_themes.extend(analysis.themes)

        # Find most common topics
        if all_topics:
            topic_freq = {}
            for topic in all_topics:
                topic_freq[topic] = topic_freq.get(topic, 0) + 1

            # Create insight for most frequent topics
            top_topics = sorted(topic_freq.items(), key=lambda x: x[1], reverse=True)[:5]

            if top_topics:
                topic_list = [f"{topic} ({count}x)" for topic, count in top_topics]

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=1,
                    insight_type=InsightType.TOPIC_EXTRACTION,
                    title="Frequent Conversation Topics",
                    content=f"Most discussed topics: {', '.join(topic_list)}. "
                           f"Shows user interests and areas where I'm frequently engaged.",
                    confidence=0.8,
                    supporting_data={"topic_frequencies": topic_freq},
                    keywords=list(topic_freq.keys())[:10],
                    source_events_count=len(analyses)
                )
                insights.append(insight)

        # Theme analysis
        if all_themes:
            theme_freq = {}
            for theme in all_themes:
                theme_freq[theme] = theme_freq.get(theme, 0) + 1

            top_themes = sorted(theme_freq.items(), key=lambda x: x[1], reverse=True)[:3]

            if top_themes:
                theme_list = [f"{theme} ({count}x)" for theme, count in top_themes]

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=1,
                    insight_type=InsightType.CONVERSATION_THEME,
                    title="Dominant Conversation Themes",
                    content=f"Recurring themes: {', '.join(theme_list)}. "
                           f"Reveals the nature and style of our interactions.",
                    confidence=0.75,
                    supporting_data={"theme_frequencies": theme_freq},
                    keywords=list(theme_freq.keys()),
                    source_events_count=len(analyses)
                )
                insights.append(insight)

        return insights

    def _generate_quality_insights(self, analyses: List[ConversationAnalysis]) -> List[ReflectionInsight]:
        """Generate insights about interaction quality and performance."""

        insights = []

        if not analyses:
            return insights

        # Calculate average quality metrics
        quality_scores = [a.interaction_quality for a in analyses if a.interaction_quality > 0]
        appropriateness_scores = [a.response_appropriateness for a in analyses if a.response_appropriateness > 0]
        avg_response_times = [a.response_time_avg for a in analyses if a.response_time_avg > 0]

        if quality_scores:
            avg_quality = sum(quality_scores) / len(quality_scores)

            # Determine quality assessment
            if avg_quality >= 0.8:
                quality_assessment = "excellent"
                confidence = 0.9
            elif avg_quality >= 0.6:
                quality_assessment = "good"
                confidence = 0.8
            elif avg_quality >= 0.4:
                quality_assessment = "moderate"
                confidence = 0.7
            else:
                quality_assessment = "needs improvement"
                confidence = 0.8

            insight = ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=1,
                insight_type=InsightType.INTERACTION_QUALITY,
                title=f"Interaction Quality Assessment: {quality_assessment.title()}",
                content=f"Average interaction quality: {avg_quality:.2f}/1.0 ({quality_assessment}). "
                       f"Based on {len(quality_scores)} conversations. "
                       f"This reflects how well I'm meeting user needs and expectations.",
                confidence=confidence,
                supporting_data={
                    "avg_quality": avg_quality,
                    "quality_scores": quality_scores,
                    "assessment": quality_assessment
                },
                source_events_count=len(analyses)
            )
            insights.append(insight)

        # Response time analysis
        if avg_response_times:
            avg_response_time = sum(avg_response_times) / len(avg_response_times)

            if avg_response_time <= 2.0:
                time_assessment = "very responsive"
            elif avg_response_time <= 5.0:
                time_assessment = "responsive"
            elif avg_response_time <= 10.0:
                time_assessment = "moderate"
            else:
                time_assessment = "slow"

            insight = ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=1,
                insight_type=InsightType.PERFORMANCE_ASSESSMENT,
                title=f"Response Time Performance: {time_assessment.title()}",
                content=f"Average response time: {avg_response_time:.1f} seconds ({time_assessment}). "
                       f"Response speed affects user experience and conversation flow.",
                confidence=0.9,
                supporting_data={
                    "avg_response_time": avg_response_time,
                    "response_times": avg_response_times,
                    "assessment": time_assessment
                },
                source_events_count=len(analyses)
            )
            insights.append(insight)

        return insights

    def _generate_intent_insights(self, analyses: List[ConversationAnalysis]) -> List[ReflectionInsight]:
        """Generate insights about user intent patterns."""

        insights = []

        # Collect user intents
        intents = [a.user_intent for a in analyses if a.user_intent]

        if intents:
            intent_freq = {}
            for intent in intents:
                intent_freq[intent] = intent_freq.get(intent, 0) + 1

            top_intents = sorted(intent_freq.items(), key=lambda x: x[1], reverse=True)[:5]

            if top_intents:
                intent_list = [f"{intent} ({count}x)" for intent, count in top_intents]

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=1,
                    insight_type=InsightType.USER_INTENT_PATTERN,
                    title="User Intent Patterns",
                    content=f"Common user intentions: {', '.join(intent_list)}. "
                           f"Understanding intent patterns helps me anticipate needs and provide better assistance.",
                    confidence=0.75,
                    supporting_data={"intent_frequencies": intent_freq},
                    keywords=list(intent_freq.keys()),
                    source_events_count=len(analyses)
                )
                insights.append(insight)

        return insights

    def _generate_emotional_insights(self, analyses: List[ConversationAnalysis]) -> List[ReflectionInsight]:
        """Generate insights about emotional context and tone."""

        insights = []

        # Collect emotional tones
        tones = [a.emotional_tone for a in analyses if a.emotional_tone]

        if tones:
            tone_freq = {}
            for tone in tones:
                tone_freq[tone] = tone_freq.get(tone, 0) + 1

            # Analyze emotional climate
            total_conversations = len(tones)
            positive_ratio = tone_freq.get('positive', 0) / total_conversations
            negative_ratio = tone_freq.get('negative', 0) / total_conversations

            if positive_ratio >= 0.6:
                emotional_climate = "predominantly positive"
                confidence = 0.8
            elif negative_ratio >= 0.4:
                emotional_climate = "concerning negative trends"
                confidence = 0.9
            elif tone_freq.get('mixed', 0) / total_conversations >= 0.5:
                emotional_climate = "emotionally complex"
                confidence = 0.7
            else:
                emotional_climate = "neutral and balanced"
                confidence = 0.6

            insight = ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=1,
                insight_type=InsightType.EMOTIONAL_CONTEXT,
                title=f"Emotional Climate: {emotional_climate.title()}",
                content=f"Emotional tone distribution: {dict(tone_freq)}. "
                       f"Overall climate is {emotional_climate}. "
                       f"This affects how I should approach future interactions.",
                confidence=confidence,
                supporting_data={
                    "tone_frequencies": tone_freq,
                    "positive_ratio": positive_ratio,
                    "negative_ratio": negative_ratio,
                    "climate": emotional_climate
                },
                source_events_count=len(analyses)
            )
            insights.append(insight)

        return insights

    def _fallback_analysis(self) -> List[ReflectionInsight]:
        """Fallback analysis when LLM is unavailable."""

        print("[reflection] Using fallback analysis (LLM unavailable)")

        insights = []

        # Basic keyword-based analysis as fallback
        try:
            conversations = self._get_recent_conversations()

            if conversations:
                # Simple topic extraction using keywords
                all_text = " ".join([conv['combined_content'].lower() for conv in conversations])

                # Technical topics
                tech_keywords = ['code', 'system', 'error', 'debug', 'programming', 'software']
                tech_count = sum(1 for keyword in tech_keywords if keyword in all_text)

                if tech_count > 0:
                    insight = ReflectionInsight.create_from_analysis(
                        cycle=self.current_cycle,
                        phase=1,
                        insight_type=InsightType.TOPIC_EXTRACTION,
                        title="Technical Discussion Detected (Fallback)",
                        content=f"Detected {tech_count} technical keywords in recent conversations. "
                               f"User appears to be discussing technical topics.",
                        confidence=0.4,  # Lower confidence for fallback
                        keywords=tech_keywords,
                        source_events_count=len(conversations)
                    )
                    insights.append(insight)

        except Exception as e:
            print(f"[reflection] Fallback analysis error: {e}")

        return insights