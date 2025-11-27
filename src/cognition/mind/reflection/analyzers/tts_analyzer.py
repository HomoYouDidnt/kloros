"""
TTS Quality Reflection Analyzer for KLoROS.

Analyzes TTS quality metrics from memory and generates insights for improvement.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ..models.reflection_models import ReflectionInsight, InsightType


class TTSQualityAnalyzer:
    """Analyzes TTS quality data for reflection insights."""

    def __init__(self, kloros_instance):
        """Initialize TTS quality analyzer."""
        self.kloros = kloros_instance
        self.current_cycle = 0

    def analyze_tts_quality_insights(self) -> List[ReflectionInsight]:
        """
        Analyze recent TTS quality metrics and generate reflection insights.

        Returns:
            List of reflection insights about TTS quality
        """
        insights = []

        try:
            # Get recent TTS analysis events from memory
            tts_events = self._get_recent_tts_analysis_events()

            if not tts_events:
                return insights

            # Analyze quality trends
            quality_trend = self._analyze_quality_trend(tts_events)
            if quality_trend:
                insights.append(quality_trend)

            # Analyze specific quality issues
            quality_issues = self._analyze_quality_issues(tts_events)
            insights.extend(quality_issues)

            # Analyze improvement opportunities
            improvement_opportunities = self._analyze_improvement_opportunities(tts_events)
            insights.extend(improvement_opportunities)

        except Exception as e:
            print(f"[reflection] TTS quality analysis error: {e}")

        return insights

    def _get_recent_tts_analysis_events(self) -> List[Dict[str, Any]]:
        """Get recent TTS analysis events from memory."""
        try:
            # Check if memory system is available
            if not hasattr(self.kloros, 'memory_system') or not self.kloros.memory_system:
                return []

            # Get events from the last 24 hours
            start_time = (datetime.now() - timedelta(hours=24)).timestamp()

            # Get TTS analysis events
            from src.kloros_memory.models import EventType
            from src.kloros_memory.storage import MemoryStore

            store = MemoryStore()
            events = store.get_events(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                start_time=start_time,
                limit=50
            )

            # Filter for TTS analysis events
            tts_events = []
            for event in events:
                metadata = getattr(event, 'metadata', {})
                if isinstance(metadata, dict) and metadata.get('component') == 'tts_quality_analysis':
                    tts_events.append({
                        'timestamp': event.timestamp,
                        'content': event.content,
                        'metadata': metadata
                    })

            return tts_events

        except Exception as e:
            print(f"[reflection] Error getting TTS analysis events: {e}")
            return []

    def _analyze_quality_trend(self, tts_events: List[Dict[str, Any]]) -> Optional[ReflectionInsight]:
        """Analyze TTS quality trends over time."""
        if len(tts_events) < 2:
            return None

        try:
            # Extract quality scores from events
            quality_scores = []
            for event in tts_events:
                metadata = event.get('metadata', {})
                quality_score = metadata.get('quality_score', 0)
                if quality_score > 0:
                    quality_scores.append(quality_score)

            if len(quality_scores) < 2:
                return None

            # Analyze trend
            recent_avg = sum(quality_scores[-3:]) / len(quality_scores[-3:])
            overall_avg = sum(quality_scores) / len(quality_scores)

            trend_direction = "stable"
            confidence = 0.6

            if recent_avg > overall_avg + 0.05:
                trend_direction = "improving"
                confidence = 0.8
            elif recent_avg < overall_avg - 0.05:
                trend_direction = "declining"
                confidence = 0.8

            return ReflectionInsight.create_from_analysis(
                cycle=self.current_cycle,
                phase=4,
                insight_type=InsightType.BEHAVIORAL_OPTIMIZATION,
                title=f"TTS Quality Trend: {trend_direction.title()}",
                content=f"TTS quality analysis shows {trend_direction} trend. "
                       f"Recent quality average: {recent_avg:.3f}, "
                       f"Overall average: {overall_avg:.3f}. "
                       f"{'Positive development in speech synthesis.' if trend_direction == 'improving' else ''}"
                       f"{'Quality decline requires attention.' if trend_direction == 'declining' else ''}"
                       f"{'Quality remains consistent.' if trend_direction == 'stable' else ''}",
                confidence=confidence,
                supporting_data={
                    "trend_direction": trend_direction,
                    "recent_quality": recent_avg,
                    "overall_quality": overall_avg,
                    "samples_analyzed": len(quality_scores)
                },
                keywords=["tts", "quality", "trend", "speech_synthesis"]
            )

        except Exception as e:
            print(f"[reflection] Error analyzing quality trend: {e}")
            return None

    def _analyze_quality_issues(self, tts_events: List[Dict[str, Any]]) -> List[ReflectionInsight]:
        """Analyze specific TTS quality issues."""
        insights = []

        try:
            # Aggregate quality metrics
            total_files = 0
            total_quality = 0.0
            issue_counts = {}

            for event in tts_events:
                metadata = event.get('metadata', {})
                files_analyzed = metadata.get('files_analyzed', 0)
                quality_score = metadata.get('quality_score', 0)

                total_files += files_analyzed
                total_quality += quality_score * files_analyzed

                # Count issues from recommendations
                recommendations = metadata.get('recommendations', [])
                for rec in recommendations:
                    if 'clarity' in rec.lower():
                        issue_counts['clarity'] = issue_counts.get('clarity', 0) + 1
                    elif 'natural' in rec.lower():
                        issue_counts['naturalness'] = issue_counts.get('naturalness', 0) + 1
                    elif 'clipping' in rec.lower():
                        issue_counts['clipping'] = issue_counts.get('clipping', 0) + 1

            if total_files == 0:
                return insights

            avg_quality = total_quality / total_files

            # Generate insights for significant issues
            if avg_quality < 0.7:
                insights.append(ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=4,
                    insight_type=InsightType.IMPROVEMENT_OPPORTUNITY,
                    title="TTS Quality Below Threshold",
                    content=f"TTS quality analysis indicates below-threshold performance ({avg_quality:.3f} < 0.7). "
                           f"Speech synthesis parameters may need optimization to improve clarity and naturalness.",
                    confidence=0.8,
                    supporting_data={
                        "average_quality": avg_quality,
                        "threshold": 0.7,
                        "files_analyzed": total_files
                    },
                    keywords=["tts", "quality", "improvement", "optimization"]
                ))

            # Generate insights for specific recurring issues
            for issue_type, count in issue_counts.items():
                if count >= 2:  # Issue appears in multiple analyses
                    insights.append(ReflectionInsight.create_from_analysis(
                        cycle=self.current_cycle,
                        phase=4,
                        insight_type=InsightType.IMPROVEMENT_OPPORTUNITY,
                        title=f"Recurring TTS {issue_type.title()} Issue",
                        content=f"TTS {issue_type} issues detected in {count} recent analyses. "
                               f"Consistent {issue_type} problems suggest systematic optimization needed.",
                        confidence=0.7,
                        supporting_data={
                            "issue_type": issue_type,
                            "occurrence_count": count,
                            "analysis_period": "24h"
                        },
                        keywords=["tts", issue_type, "recurring", "optimization"]
                    ))

        except Exception as e:
            print(f"[reflection] Error analyzing quality issues: {e}")

        return insights

    def _analyze_improvement_opportunities(self, tts_events: List[Dict[str, Any]]) -> List[ReflectionInsight]:
        """Analyze TTS improvement opportunities."""
        insights = []

        try:
            # Collect all recommendations
            all_recommendations = []
            recommendation_counts = {}

            for event in tts_events:
                metadata = event.get('metadata', {})
                recommendations = metadata.get('recommendations', [])
                all_recommendations.extend(recommendations)

                for rec in recommendations:
                    recommendation_counts[rec] = recommendation_counts.get(rec, 0) + 1

            # Generate insights for frequent recommendations
            for recommendation, count in recommendation_counts.items():
                if count >= 2:  # Recommendation appears multiple times
                    insights.append(ReflectionInsight.create_from_analysis(
                        cycle=self.current_cycle,
                        phase=4,
                        insight_type=InsightType.PARAMETER_ADJUSTMENT,
                        title="TTS Optimization Recommendation",
                        content=f"Repeated recommendation detected: {recommendation}. "
                               f"This suggestion has appeared {count} times in recent analyses, "
                               f"indicating a systematic optimization opportunity for speech synthesis.",
                        confidence=0.7,
                        supporting_data={
                            "recommendation": recommendation,
                            "frequency": count,
                            "total_recommendations": len(all_recommendations)
                        },
                        keywords=["tts", "optimization", "recommendation", "speech_synthesis"]
                    ))

            # Meta-insight about TTS optimization system
            if all_recommendations:
                insights.append(ReflectionInsight.create_from_analysis(
                    cycle=self.current_cycle,
                    phase=4,
                    insight_type=InsightType.BEHAVIORAL_OPTIMIZATION,
                    title="TTS Analysis System Active",
                    content=f"TTS quality analysis system is actively monitoring speech synthesis. "
                           f"{len(all_recommendations)} improvement recommendations generated, "
                           f"demonstrating systematic approach to voice quality optimization.",
                    confidence=0.9,
                    supporting_data={
                        "recommendations_generated": len(all_recommendations),
                        "unique_recommendations": len(set(all_recommendations)),
                        "analysis_events": len(tts_events)
                    },
                    keywords=["tts", "analysis", "monitoring", "self_improvement"]
                ))

        except Exception as e:
            print(f"[reflection] Error analyzing improvement opportunities: {e}")

        return insights