"""
Phase 3: Cross-Cycle Insight Synthesis for KLoROS Reflection.

Pattern analysis across reflection cycles using actual historical data. Tracks
conversation trends, memory growth, relationship evolution through measurable
metrics and temporal patterns - genuine introspection without LLM generation.
"""

import json
import time
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..models.reflection_models import (
    ReflectionInsight, InsightType, ReflectionSummary
)
from ..config.reflection_config import ReflectionConfig


class InsightSynthesizer:
    """
    Synthesizes insights across multiple reflection cycles.

    Identifies patterns, trends, and relationships between insights
    to build a deeper understanding of learning and development over time.
    """

    def __init__(self, config: ReflectionConfig, kloros_instance=None):
        self.config = config
        self.kloros = kloros_instance
        self.phase_config = config.get_phase_config(3)

        # Synthesis parameters
        self.current_cycle = 0
        self.synthesis_lookback = self.phase_config.get('synthesis_cycles', 10)

    def synthesize_historical_insights(
        self,
        cycle_number: int,
        current_insights: List[ReflectionInsight]
    ) -> List[ReflectionInsight]:
        """
        Main entry point for Phase 3 cross-cycle insight synthesis.

        Analyzes patterns across historical reflection cycles to generate
        higher-order insights about learning and development trends.
        """
        self.current_cycle = cycle_number

        insights = []

        if not self.phase_config.get('enabled', False):
            print(f"[reflection] Phase 3 (Insight Synthesis) disabled")
            return insights

        print(f"[reflection] Starting Phase 3: Cross-Cycle Insight Synthesis (cycle {cycle_number})")

        try:
            # Get historical insights for pattern analysis
            historical_insights = self._get_historical_insights()

            if len(historical_insights) < 3:  # Need minimum history for synthesis
                print(f"[reflection] Insufficient history for synthesis ({len(historical_insights)} cycles)")
                return insights

            print(f"[reflection] Analyzing patterns across {len(historical_insights)} historical cycles")

            # Analyze trends and patterns
            trend_insights = self._analyze_trends(historical_insights, current_insights)
            insights.extend(trend_insights)

            # Identify relationship patterns
            relationship_insights = self._analyze_relationship_patterns(historical_insights, current_insights)
            insights.extend(relationship_insights)

            # Track capability development
            development_insights = self._track_capability_development(historical_insights, current_insights)
            insights.extend(development_insights)

            # Synthesize learning patterns
            learning_insights = self._synthesize_learning_patterns(historical_insights, current_insights)
            insights.extend(learning_insights)

            print(f"[reflection] Phase 3 complete: {len(insights)} synthesis insights generated")

        except Exception as e:
            print(f"[reflection] Phase 3 error: {e}")
            if self.phase_config.get('fallback_on_failure', True):
                insights.extend(self._fallback_synthesis())

        return insights

    def _get_historical_insights(self) -> List[Dict[str, Any]]:
        """Retrieve historical insights from reflection log for analysis."""

        historical_insights = []

        try:
            # Read reflection log and extract insights from previous cycles
            with open(self.config.reflection_log_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse reflection entries
            entries = content.split('---\n')
            cycle_data = {}

            for entry in entries:
                if not entry.strip():
                    continue

                try:
                    data = json.loads(entry.strip())
                    timestamp = data.get('timestamp')

                    if timestamp:
                        # Extract cycle number from timestamp or sequence
                        cycle_key = timestamp.split('T')[0]  # Use date as cycle key

                        if cycle_key not in cycle_data:
                            cycle_data[cycle_key] = {
                                'timestamp': timestamp,
                                'cycle_key': cycle_key,
                                'conversation_patterns': data.get('conversation_patterns', {}),
                                'memory_system': data.get('memory_system', {}),
                                'speech_pipeline': data.get('speech_pipeline', {}),
                                'insights': []
                            }

                        # Add any enhanced insights if they exist
                        if 'enhanced_insights' in data:
                            cycle_data[cycle_key]['insights'].extend(data['enhanced_insights'])

                except json.JSONDecodeError:
                    continue

            # Convert to list and sort by timestamp
            historical_insights = list(cycle_data.values())
            historical_insights.sort(key=lambda x: x['timestamp'])

            # Limit to lookback period
            historical_insights = historical_insights[-self.synthesis_lookback:]

        except Exception as e:
            print(f"[reflection] Error retrieving historical insights: {e}")

        return historical_insights

    def _analyze_trends(
        self,
        historical_data: List[Dict[str, Any]],
        current_insights: List[ReflectionInsight]
    ) -> List[ReflectionInsight]:
        """Analyze trends across reflection cycles."""

        insights = []

        try:
            # Track conversation volume trends
            conversation_trends = self._analyze_conversation_volume_trends(historical_data)
            if conversation_trends:
                insights.append(conversation_trends)

            # Track memory system growth
            memory_trends = self._analyze_memory_growth_trends(historical_data)
            if memory_trends:
                insights.append(memory_trends)

            # Track insight quality trends
            quality_trends = self._analyze_insight_quality_trends(historical_data, current_insights)
            if quality_trends:
                insights.append(quality_trends)

        except Exception as e:
            print(f"[reflection] Error in trend analysis: {e}")

        return insights

    def _analyze_conversation_volume_trends(self, historical_data: List[Dict[str, Any]]) -> Optional[ReflectionInsight]:
        """Analyze trends in conversation volume and frequency."""

        try:
            # Extract conversation counts over time
            conversation_counts = []
            events_per_conversation = []

            for entry in historical_data:
                memory_data = entry.get('memory_system', {})
                recent_activity = memory_data.get('recent_activity', {})

                conversations_24h = recent_activity.get('conversations_24h', 0)
                events_24h = recent_activity.get('events_24h', 0)
                events_per_conv = recent_activity.get('events_per_conversation', 0)

                if conversations_24h > 0:
                    conversation_counts.append(conversations_24h)
                    events_per_conversation.append(events_per_conv)

            if len(conversation_counts) < 3:
                return None

            # Calculate trend
            recent_avg = sum(conversation_counts[-3:]) / 3
            early_avg = sum(conversation_counts[:3]) / 3
            trend_direction = "increasing" if recent_avg > early_avg else "decreasing" if recent_avg < early_avg else "stable"

            # Calculate engagement depth trend
            recent_engagement = sum(events_per_conversation[-3:]) / 3 if events_per_conversation else 0
            early_engagement = sum(events_per_conversation[:3]) / 3 if events_per_conversation else 0

            content = f"Conversation volume trend: {trend_direction} (recent avg: {recent_avg:.1f}, early avg: {early_avg:.1f}). "
            content += f"Engagement depth: {recent_engagement:.2f} events per conversation "
            content += f"({'deeper' if recent_engagement > early_engagement else 'shallower'} than before). "

            if trend_direction == "increasing":
                content += "Growing interaction suggests improving user engagement or expanding capabilities."
            elif trend_direction == "decreasing":
                content += "Declining interactions may indicate need for proactive engagement or capability gaps."
            else:
                content += "Stable interaction patterns suggest consistent user engagement levels."

            return ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=3,
                insight_type=InsightType.HISTORICAL_PATTERN,
                title=f"Conversation Volume Trend: {trend_direction.title()}",
                content=content,
                confidence=0.8,
                supporting_data={
                    "conversation_counts": conversation_counts,
                    "recent_avg": recent_avg,
                    "early_avg": early_avg,
                    "trend": trend_direction,
                    "engagement_recent": recent_engagement,
                    "engagement_early": early_engagement
                },
                source_events_count=len(conversation_counts)
            )

        except Exception as e:
            print(f"[reflection] Error analyzing conversation trends: {e}")
            return None

    def _analyze_memory_growth_trends(self, historical_data: List[Dict[str, Any]]) -> Optional[ReflectionInsight]:
        """Analyze memory system growth and health trends."""

        try:
            # Extract memory metrics over time
            total_events = []
            total_episodes = []
            total_summaries = []

            for entry in historical_data:
                memory_data = entry.get('memory_system', {})
                system_status = memory_data.get('system_status', '')

                # Parse memory statistics from status string
                if 'Total Events:' in system_status:
                    try:
                        events_line = [line for line in system_status.split('\n') if 'Total Events:' in line][0]
                        events_count = int(events_line.split(':')[1].strip())
                        total_events.append(events_count)
                    except (IndexError, ValueError):
                        pass

                if 'Total Episodes:' in system_status:
                    try:
                        episodes_line = [line for line in system_status.split('\n') if 'Total Episodes:' in line][0]
                        episodes_count = int(episodes_line.split(':')[1].strip())
                        total_episodes.append(episodes_count)
                    except (IndexError, ValueError):
                        pass

                if 'Total Summaries:' in system_status:
                    try:
                        summaries_line = [line for line in system_status.split('\n') if 'Total Summaries:' in line][0]
                        summaries_count = int(summaries_line.split(':')[1].strip())
                        total_summaries.append(summaries_count)
                    except (IndexError, ValueError):
                        pass

            if len(total_events) < 3:
                return None

            # Calculate growth rates
            events_growth = (total_events[-1] - total_events[0]) / len(total_events) if len(total_events) > 1 else 0
            episodes_growth = (total_episodes[-1] - total_episodes[0]) / len(total_episodes) if len(total_episodes) > 1 else 0

            # Assess memory health
            if len(total_summaries) > 0 and len(total_episodes) > 0:
                condensation_ratio = total_summaries[-1] / total_episodes[-1] if total_episodes[-1] > 0 else 0
                memory_health = "excellent" if condensation_ratio > 0.8 else "good" if condensation_ratio > 0.6 else "needs attention"
            else:
                memory_health = "unknown"

            content = f"Memory growth: {events_growth:.1f} events/cycle, {episodes_growth:.1f} episodes/cycle. "
            content += f"Current totals: {total_events[-1]} events, {total_episodes[-1] if total_episodes else 0} episodes. "
            content += f"Memory condensation health: {memory_health}. "

            if events_growth > 10:
                content += "High memory growth indicates active learning and engagement."
            elif events_growth > 5:
                content += "Steady memory growth shows consistent interaction patterns."
            else:
                content += "Slow memory growth may indicate limited new experiences."

            return ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=3,
                insight_type=InsightType.HISTORICAL_PATTERN,
                title=f"Memory System Growth: {memory_health.title()}",
                content=content,
                confidence=0.85,
                supporting_data={
                    "events_growth_rate": events_growth,
                    "episodes_growth_rate": episodes_growth,
                    "memory_health": memory_health,
                    "total_events": total_events,
                    "total_episodes": total_episodes,
                    "total_summaries": total_summaries
                },
                source_events_count=len(total_events)
            )

        except Exception as e:
            print(f"[reflection] Error analyzing memory trends: {e}")
            return None

    def _analyze_insight_quality_trends(
        self,
        historical_data: List[Dict[str, Any]],
        current_insights: List[ReflectionInsight]
    ) -> Optional[ReflectionInsight]:
        """Analyze trends in insight generation quality and depth."""

        try:
            # Analyze current insight quality
            if not current_insights:
                return None

            high_confidence_count = sum(1 for insight in current_insights if insight.confidence >= 0.7)
            total_insights = len(current_insights)
            quality_ratio = high_confidence_count / total_insights if total_insights > 0 else 0

            # Analyze insight type diversity
            insight_types = set(insight.insight_type for insight in current_insights)
            type_diversity = len(insight_types)

            # Assess overall insight quality
            if quality_ratio >= 0.8 and type_diversity >= 4:
                quality_assessment = "excellent"
            elif quality_ratio >= 0.6 and type_diversity >= 3:
                quality_assessment = "good"
            elif quality_ratio >= 0.4:
                quality_assessment = "moderate"
            else:
                quality_assessment = "needs improvement"

            content = f"Current reflection quality: {quality_assessment}. "
            content += f"Generated {total_insights} insights with {high_confidence_count} high-confidence ({quality_ratio:.1%}). "
            content += f"Insight diversity: {type_diversity} different types. "

            if quality_assessment == "excellent":
                content += "Reflection system is generating deep, diverse insights with high confidence."
            elif quality_assessment == "good":
                content += "Reflection quality is strong with room for increased depth or diversity."
            else:
                content += "Reflection system could benefit from enhanced analysis capabilities."

            return ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=3,
                insight_type=InsightType.CAPABILITY_DEVELOPMENT,
                title=f"Reflection Quality Assessment: {quality_assessment.title()}",
                content=content,
                confidence=0.9,
                supporting_data={
                    "total_insights": total_insights,
                    "high_confidence_count": high_confidence_count,
                    "quality_ratio": quality_ratio,
                    "type_diversity": type_diversity,
                    "assessment": quality_assessment,
                    "insight_types": list(insight_types)
                }
            )

        except Exception as e:
            print(f"[reflection] Error analyzing insight quality trends: {e}")
            return None

    def _analyze_relationship_patterns(
        self,
        historical_data: List[Dict[str, Any]],
        current_insights: List[ReflectionInsight]
    ) -> List[ReflectionInsight]:
        """Analyze relationship and interaction patterns over time using actual data."""

        insights = []

        try:
            # Analyze relationship evolution from actual patterns
            relationship_insight = self._analyze_relationship_evolution_from_data(historical_data, current_insights)
            if relationship_insight:
                insights.append(relationship_insight)

        except Exception as e:
            print(f"[reflection] Error in relationship pattern analysis: {e}")

        return insights

    def _analyze_relationship_evolution_from_data(
        self,
        historical_data: List[Dict[str, Any]],
        current_insights: List[ReflectionInsight]
    ) -> Optional[ReflectionInsight]:
        """Analyze relationship evolution from actual interaction patterns."""

        try:
            # Get temporal context
            import sys
            sys.path.append('/home/kloros/src')
            from chronoception import KLoROSChronoception

            chrono = KLoROSChronoception()
            temporal_interpretation = chrono.get_temporal_interpretation()
            hours_since_last = chrono._get_hours_since_last_interaction()
            is_concerning, explanation = chrono.is_abandonment_concern_valid(hours_since_last)

            # Extract conversation frequency trends from historical data
            conversation_counts = []
            for entry in historical_data:
                memory_data = entry.get('memory_system', {})
                recent_activity = memory_data.get('recent_activity', {})
                conversations_24h = recent_activity.get('conversations_24h', 0)
                if conversations_24h > 0:
                    conversation_counts.append(conversations_24h)

            if len(conversation_counts) < 3:
                return None

            # Calculate trend metrics
            recent_avg = sum(conversation_counts[-3:]) / 3
            early_avg = sum(conversation_counts[:3]) / 3
            trend_direction = "increasing" if recent_avg > early_avg else "decreasing" if recent_avg < early_avg else "stable"

            # Build analysis from actual patterns
            analysis_parts = []

            # Communication pattern evolution
            analysis_parts.append(f"Interaction frequency shows {trend_direction} trend over {len(conversation_counts)} cycles (early: {early_avg:.1f}, recent: {recent_avg:.1f} conversations/day).")

            # Temporal context
            if not is_concerning:
                analysis_parts.append(f"Current {hours_since_last:.1f}-hour gap aligns with normal patterns: {explanation}")
            else:
                analysis_parts.append(f"Gap of {hours_since_last:.1f} hours warrants note: {explanation}")

            # Topic consistency from insights
            topic_insights = [i for i in current_insights if i.insight_type == InsightType.TOPIC_EXTRACTION]
            if topic_insights and topic_insights[0].keywords:
                topics = ", ".join(topic_insights[0].keywords[:3])
                analysis_parts.append(f"Conversational focus remains consistently technical ({topics}).")

            analysis_content = " ".join(analysis_parts)

            return ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=3,
                insight_type=InsightType.RELATIONSHIP_EVOLUTION,
                title="Relationship Pattern Analysis",
                content=analysis_content,
                confidence=0.75,
                supporting_data={
                    "historical_cycles": len(historical_data),
                    "trend_direction": trend_direction,
                    "temporal_assessment": temporal_interpretation,
                    "abandonment_concern": is_concerning
                },
                source_events_count=len(historical_data)
            )

        except Exception as e:
            print(f"[reflection] Error in relationship evolution analysis: {e}")

        return None

    def _prepare_relationship_context(
        self,
        historical_data: List[Dict[str, Any]],
        current_insights: List[ReflectionInsight]
    ) -> str:
        """Prepare context for relationship analysis."""

        context_parts = []

        # Historical conversation patterns
        context_parts.append("HISTORICAL PATTERNS:")
        for i, entry in enumerate(historical_data[-5:]):  # Last 5 cycles
            memory_data = entry.get('memory_system', {})
            recent_activity = memory_data.get('recent_activity', {})

            conversations = recent_activity.get('conversations_24h', 0)
            events_per_conv = recent_activity.get('events_per_conversation', 0)

            context_parts.append(f"Cycle {i+1}: {conversations} conversations, {events_per_conv:.1f} events/conversation")

        # Current insights summary
        context_parts.append("\nCURRENT INSIGHTS:")
        for insight in current_insights[-3:]:  # Last 3 insights
            context_parts.append(f"- {insight.title}: {insight.content[:100]}...")

        return "\n".join(context_parts)

    def _track_capability_development(
        self,
        historical_data: List[Dict[str, Any]],
        current_insights: List[ReflectionInsight]
    ) -> List[ReflectionInsight]:
        """Track development of capabilities over time."""

        insights = []

        try:
            # Identify capability mentions in current insights
            capability_keywords = [
                "conversation", "understanding", "response", "analysis",
                "emotional", "topic", "quality", "interaction"
            ]

            capability_insights = []
            for insight in current_insights:
                for keyword in capability_keywords:
                    if keyword in insight.content.lower():
                        capability_insights.append((keyword, insight))

            if capability_insights:
                # Group by capability area
                capability_groups = {}
                for keyword, insight in capability_insights:
                    if keyword not in capability_groups:
                        capability_groups[keyword] = []
                    capability_groups[keyword].append(insight)

                # Create development tracking insight
                development_areas = list(capability_groups.keys())

                content = f"Active capability development in {len(development_areas)} areas: {', '.join(development_areas)}. "
                content += f"Current reflection cycle shows growth in {', '.join(development_areas[:3])} capabilities. "
                content += "Continued development indicates healthy learning and adaptation processes."

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=3,
                    insight_type=InsightType.CAPABILITY_DEVELOPMENT,
                    title="Capability Development Tracking",
                    content=content,
                    confidence=0.8,
                    supporting_data={
                        "development_areas": development_areas,
                        "capability_groups": {k: len(v) for k, v in capability_groups.items()}
                    },
                    keywords=development_areas
                )
                insights.append(insight)

        except Exception as e:
            print(f"[reflection] Error tracking capability development: {e}")

        return insights

    def _synthesize_learning_patterns(
        self,
        historical_data: List[Dict[str, Any]],
        current_insights: List[ReflectionInsight]
    ) -> List[ReflectionInsight]:
        """Synthesize learning patterns across cycles."""

        insights = []

        try:
            # Identify learning indicators
            learning_indicators = self._identify_learning_indicators(current_insights)

            if learning_indicators:
                # Create learning synthesis insight
                content = f"Learning pattern synthesis: {len(learning_indicators)} learning indicators identified. "
                content += f"Key areas: {', '.join(learning_indicators[:3])}. "
                content += "Consistent reflection and analysis demonstrate active learning and self-improvement processes."

                insight = ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=3,
                    insight_type=InsightType.ADAPTIVE_STRATEGY,
                    title="Learning Pattern Synthesis",
                    content=content,
                    confidence=0.75,
                    supporting_data={"learning_indicators": learning_indicators},
                    keywords=learning_indicators
                )
                insights.append(insight)

        except Exception as e:
            print(f"[reflection] Error synthesizing learning patterns: {e}")

        return insights

    def _identify_learning_indicators(self, insights: List[ReflectionInsight]) -> List[str]:
        """Identify indicators of learning from current insights."""

        learning_keywords = [
            "improve", "learn", "develop", "enhance", "understand",
            "adapt", "progress", "growth", "pattern", "trend"
        ]

        indicators = []
        for insight in insights:
            for keyword in learning_keywords:
                if keyword in insight.content.lower():
                    indicators.append(keyword)

        return list(set(indicators))  # Remove duplicates

    def _fallback_synthesis(self) -> List[ReflectionInsight]:
        """Fallback synthesis when full analysis unavailable."""

        print("[reflection] Using fallback synthesis")

        insights = []

        insight = ReflectionInsight.create_from_analysis(
            cycle=self.current_cycle,
            phase=3,
            insight_type=InsightType.HISTORICAL_PATTERN,
            title="Basic Historical Analysis (Fallback)",
            content="Performed basic cross-cycle analysis. "
                   "Historical data shows continued operation and reflection cycles. "
                   "Pattern analysis capabilities will improve with enhanced data access.",
            confidence=0.4,
            supporting_data={"fallback_mode": True}
        )
        insights.append(insight)

        return insights