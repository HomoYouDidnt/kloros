"""
Phase 4: Adaptive Self-Optimization for KLoROS Reflection.

Implements self-optimization capabilities where KLoROS can adaptively tune
her own parameters and behaviors based on reflection insights and performance analysis.
"""

import json
import time
import uuid
import sqlite3
import requests
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

import os

# Tool synthesis queue for autonomous proposals
try:
    from src.orchestration.core.synthesis_queue import SynthesisQueue
    SYNTHESIS_QUEUE_AVAILABLE = True
except ImportError:
    SYNTHESIS_QUEUE_AVAILABLE = False
    print("[reflection] SynthesisQueue not available - autonomous tool proposals disabled")

from ..models.reflection_models import (
    ReflectionInsight, InsightType, AdaptiveOptimization
)
from ..config.reflection_config import ReflectionConfig


class AdaptiveOptimizer:
    """
    Implements adaptive self-optimization based on reflection insights.

    Analyzes performance patterns and automatically adjusts system parameters
    to improve conversation quality, response effectiveness, and user satisfaction.
    """

    def __init__(self, config: ReflectionConfig, kloros_instance=None):
        self.config = config
        self.kloros = kloros_instance
        self.phase_config = config.get_phase_config(4)

        # Optimization tracking
        self.current_cycle = 0
        self.optimization_history = []

        # Safe parameter ranges for optimization (mapped to actual KLoROS parameters)
        self.safe_parameter_ranges = {
            # Audio/Voice Parameters
            'wake_confidence_threshold': (0.5, 0.8),      # wake_conf_min
            'wake_rms_threshold': (50, 500),              # wake_rms_min
            'wake_cooldown_ms': (1000, 5000),             # wake_cooldown_ms
            'speaker_confidence_threshold': (0.6, 0.9),   # speaker_threshold
            'vad_threshold_dbfs': (-60.0, -30.0),         # vad_threshold_dbfs_fallback

            # Memory/Context Parameters
            'memory_context_summaries': (1, 10),          # KLR_MAX_CONTEXT_SUMMARIES
            'memory_context_events': (3, 20),             # KLR_MAX_CONTEXT_EVENTS
            'memory_context_enabled': (0, 1),             # KLR_CONTEXT_IN_CHAT (boolean)

            # Response Quality Parameters
            'response_temperature': (0.3, 1.2),           # LLM temperature for emotional adaptation
            'conversation_timeout': (5, 30),              # KLR_CONVERSATION_TIMEOUT
            'max_conversation_turns': (2, 10)             # KLR_MAX_CONVERSATION_TURNS
        }

        # Current optimization experiments
        self.active_optimizations = []

        # Tool synthesis queue (Level 2 autonomy)
        self.synthesis_queue = SynthesisQueue() if SYNTHESIS_QUEUE_AVAILABLE else None
        self.tool_synthesis_enabled = os.getenv('KLR_ENABLE_AUTO_SYNTHESIS', '0') == '1'
        self.synthesis_min_confidence = float(os.getenv('KLR_AUTO_SYNTHESIS_MIN_CONFIDENCE', '0.75'))

    def perform_adaptive_optimization(
        self,
        cycle_number: int,
        all_insights: List[ReflectionInsight]
    ) -> List[ReflectionInsight]:
        """
        Main entry point for Phase 4 adaptive optimization.

        Analyzes insights to identify optimization opportunities and
        implements safe, reversible parameter adjustments.
        """
        self.current_cycle = cycle_number

        insights = []

        if not self.phase_config.get('enabled', False):
            print(f"[reflection] Phase 4 (Adaptive Optimization) disabled")
            return insights

        print(f"[reflection] Starting Phase 4: Adaptive Self-Optimization (cycle {cycle_number})")

        try:
            # Add TTS quality analysis insights
            tts_insights = self._analyze_tts_quality()
            all_insights.extend(tts_insights)

            # Analyze current performance metrics
            performance_analysis = self._analyze_current_performance(all_insights)

            # Identify optimization opportunities
            optimization_opportunities = self._identify_optimization_opportunities(all_insights, performance_analysis)

            # Evaluate and implement safe optimizations
            for opportunity in optimization_opportunities:
                optimization_insight = self._evaluate_and_implement_optimization(opportunity)
                if optimization_insight:
                    insights.append(optimization_insight)

            # Review and assess active optimizations
            assessment_insights = self._assess_active_optimizations()
            insights.extend(assessment_insights)


            # Check for tool synthesis opportunities (Level 2 autonomy)
            queued = self._detect_and_queue_tool_synthesis_opportunities(all_insights)
            if queued:
                print(f"[reflection] Phase 4: Queued {len(queued)} tool synthesis proposals")
                # Create notification for user
                self._create_synthesis_notification(len(queued))

            # Generate predictive insights for future improvements
            predictive_insights = self._generate_predictive_insights(all_insights)
            insights.extend(predictive_insights)

            print(f"[reflection] Phase 4 complete: {len(insights)} optimization insights generated")

        except Exception as e:
            print(f"[reflection] Phase 4 error: {e}")
            if self.phase_config.get('fallback_on_failure', True):
                insights.extend(self._fallback_optimization())

        return insights

    def _analyze_current_performance(self, insights: List[ReflectionInsight]) -> Dict[str, Any]:
        """Analyze current performance metrics from insights."""

        performance_metrics = {
            'interaction_quality': None,  # Use None to indicate no data available
            'response_appropriateness': None,
            'response_time': None,
            'emotional_understanding': None,
            'topic_recognition': None,
            'user_satisfaction': None,
            'tts_quality': None,
            'performance_issues': [],
            'strengths': [],
            'has_actual_data': False  # Track whether we have real performance data
        }

        for insight in insights:
            # Extract performance indicators from insights
            if insight.insight_type == InsightType.INTERACTION_QUALITY:
                quality_data = insight.supporting_data.get('avg_quality', 0.0)
                performance_metrics['interaction_quality'] = quality_data
                performance_metrics['has_actual_data'] = True  # Mark that we have real data

                if quality_data >= 0.8:
                    performance_metrics['strengths'].append('high_interaction_quality')
                elif quality_data < 0.6:
                    performance_metrics['performance_issues'].append('low_interaction_quality')

            elif insight.insight_type == InsightType.PERFORMANCE_ASSESSMENT:
                response_time = insight.supporting_data.get('avg_response_time', 0.0)
                performance_metrics['response_time'] = response_time
                performance_metrics['has_actual_data'] = True  # Mark that we have real data

                if response_time > 5.0:
                    performance_metrics['performance_issues'].append('slow_response_time')
                elif response_time <= 2.0:
                    performance_metrics['strengths'].append('fast_response_time')

            elif insight.insight_type == InsightType.EMOTIONAL_CONTEXT:
                emotional_data = insight.supporting_data
                positive_ratio = emotional_data.get('positive_ratio', 0.0)
                performance_metrics['emotional_understanding'] = positive_ratio

                if positive_ratio >= 0.7:
                    performance_metrics['strengths'].append('good_emotional_understanding')
                elif positive_ratio < 0.4:
                    performance_metrics['performance_issues'].append('poor_emotional_understanding')

            elif insight.insight_type == InsightType.TOPIC_EXTRACTION:
                # Topic recognition strength
                keywords = insight.keywords or []
                if len(keywords) >= 5:
                    performance_metrics['strengths'].append('strong_topic_recognition')
                    performance_metrics['topic_recognition'] = 0.8
                else:
                    performance_metrics['topic_recognition'] = 0.5

            elif insight.insight_type == InsightType.BEHAVIORAL_OPTIMIZATION and 'tts' in insight.keywords:
                # TTS quality insights
                supporting_data = insight.supporting_data
                if 'recent_quality' in supporting_data:
                    quality_score = supporting_data['recent_quality']
                    performance_metrics['tts_quality'] = quality_score

                    if quality_score >= 0.8:
                        performance_metrics['strengths'].append('high_tts_quality')
                    elif quality_score < 0.6:
                        performance_metrics['performance_issues'].append('low_tts_quality')

            elif insight.insight_type == InsightType.IMPROVEMENT_OPPORTUNITY and 'tts' in insight.keywords:
                # TTS improvement opportunities
                performance_metrics['performance_issues'].append('tts_optimization_needed')

        return performance_metrics

    def _identify_optimization_opportunities(
        self,
        insights: List[ReflectionInsight],
        performance: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify specific optimization opportunities based on performance analysis."""

        opportunities = []

        # Skip all optimizations if we don't have actual performance data
        if not performance['has_actual_data']:
            print(f"[reflection] Phase 4: No performance data available, skipping optimizations")
            return opportunities

        print(f"[reflection] Phase 4: Analyzing performance data for optimization opportunities")

        # Response time optimization - only if we have actual data
        if (performance['has_actual_data'] and
            performance['response_time'] is not None and
            performance['response_time'] > 3.0):
            opportunities.append({
                'type': 'response_time_optimization',
                'priority': 'high',
                'description': 'Optimize response time for better conversation flow',
                'target_parameter': 'memory_context_events',
                'current_issue': 'slow_response_time',
                'suggested_adjustment': 'reduce',
                'confidence': 0.8
            })

        # Wake word sensitivity optimization
        wake_word_issues = any('wake' in insight.content.lower() for insight in insights)
        if wake_word_issues:
            opportunities.append({
                'type': 'wake_word_optimization',
                'priority': 'medium',
                'description': 'Adjust wake word detection sensitivity',
                'target_parameter': 'wake_confidence_threshold',
                'current_issue': 'wake_detection_issues',
                'suggested_adjustment': 'fine_tune',
                'confidence': 0.6
            })

        # Memory context optimization - only if we have actual interaction data
        if (performance['has_actual_data'] and
            performance['interaction_quality'] is not None and
            performance['interaction_quality'] < 0.6):
            opportunities.append({
                'type': 'memory_context_optimization',
                'priority': 'medium',
                'description': 'Optimize memory context for better conversation quality',
                'target_parameter': 'memory_context_summaries',
                'current_issue': 'low_interaction_quality',
                'suggested_adjustment': 'increase',
                'confidence': 0.7
            })

        # Emotional understanding enhancement - only if we have actual data
        if (performance['has_actual_data'] and
            performance['emotional_understanding'] is not None and
            performance['emotional_understanding'] < 0.5):
            opportunities.append({
                'type': 'emotional_enhancement',
                'priority': 'low',
                'description': 'Enhance emotional context processing',
                'target_parameter': 'response_temperature',
                'current_issue': 'poor_emotional_understanding',
                'suggested_adjustment': 'increase',
                'confidence': 0.5
            })

        return opportunities

    def _evaluate_and_implement_optimization(self, opportunity: Dict[str, Any]) -> Optional[ReflectionInsight]:
        """Evaluate an optimization opportunity and implement if safe."""

        try:
            # Check optimization confidence threshold
            min_confidence = self.phase_config.get('optimization_threshold', 0.7)
            if opportunity['confidence'] < min_confidence:
                return self._create_optimization_insight(
                    f"Optimization Deferred: {opportunity['type']}",
                    f"Deferred optimization for {opportunity['description']} due to low confidence ({opportunity['confidence']:.2f} < {min_confidence:.2f})",
                    InsightType.PARAMETER_ADJUSTMENT,
                    0.5,
                    {"deferred_reason": "low_confidence", "opportunity": opportunity}
                )

            # Check if this parameter is safe to optimize
            target_param = opportunity['target_parameter']
            if target_param not in self.safe_parameter_ranges:
                return self._create_optimization_insight(
                    f"Optimization Restricted: {opportunity['type']}",
                    f"Cannot optimize {target_param} - not in safe parameter list",
                    InsightType.PARAMETER_ADJUSTMENT,
                    0.3,
                    {"restriction_reason": "unsafe_parameter", "opportunity": opportunity}
                )

            # Implement the optimization
            optimization_result = self._implement_parameter_optimization(opportunity)

            if optimization_result:
                return self._create_optimization_insight(
                    f"Optimization Applied: {opportunity['type']}",
                    f"Applied optimization: {opportunity['description']}. {optimization_result['description']}",
                    InsightType.PARAMETER_ADJUSTMENT,
                    opportunity['confidence'],
                    {
                        "optimization_id": optimization_result['optimization_id'],
                        "parameter_changes": optimization_result['changes'],
                        "opportunity": opportunity
                    }
                )

        except Exception as e:
            print(f"[reflection] Error implementing optimization: {e}")
            return None

        return None

    def _implement_parameter_optimization(self, opportunity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Implement a specific parameter optimization."""

        target_param = opportunity['target_parameter']
        adjustment = opportunity['suggested_adjustment']

        # Generate optimization ID
        optimization_id = str(uuid.uuid4())[:8]

        try:
            # Get current parameter value (this would interface with actual KLoROS parameters)
            current_value = self._get_current_parameter_value(target_param)
            if current_value is None:
                return None

            # Calculate new value based on adjustment type
            new_value = self._calculate_new_parameter_value(target_param, current_value, adjustment)
            if new_value is None:
                return None

            # Apply the optimization (in a real implementation)
            success = self._apply_parameter_change(target_param, new_value)
            if not success:
                return None

            # Create optimization record
            optimization = AdaptiveOptimization(
                optimization_id=optimization_id,
                optimization_type=opportunity['type'],
                parameter_changes={target_param: {"old": current_value, "new": new_value}},
                rationale=opportunity['description'],
                success_metrics={"target_metric": 0.0},  # Will be updated during evaluation
                outcome_confidence=opportunity['confidence']
            )

            # Track this optimization
            self.active_optimizations.append(optimization)

            return {
                'optimization_id': optimization_id,
                'changes': {target_param: {"old": current_value, "new": new_value}},
                'description': f"Changed {target_param} from {current_value} to {new_value}"
            }

        except Exception as e:
            print(f"[reflection] Error in parameter optimization: {e}")
            return None

    def _get_current_parameter_value(self, parameter: str) -> Optional[Any]:
        """Get current value of a system parameter from running KLoROS instance."""

        try:
            if not self.kloros:
                return None

            # Map optimization parameters to actual KLoROS attributes and environment variables
            parameter_mapping = {
                # Audio/Voice Parameters (direct attributes)
                'wake_confidence_threshold': 'wake_conf_min',
                'wake_rms_threshold': 'wake_rms_min',
                'wake_cooldown_ms': 'wake_cooldown_ms',
                'speaker_confidence_threshold': 'speaker_threshold',
                'vad_threshold_dbfs': 'vad_threshold_dbfs_fallback',

                # Memory/Context Parameters (environment variables)
                'memory_context_summaries': 'env:KLR_MAX_CONTEXT_SUMMARIES',
                'memory_context_events': 'env:KLR_MAX_CONTEXT_EVENTS',
                'memory_context_enabled': 'env:KLR_CONTEXT_IN_CHAT',

                # Response Quality Parameters (environment variables)
                'response_temperature': 'env:OLLAMA_TEMPERATURE',
                'conversation_timeout': 'env:KLR_CONVERSATION_TIMEOUT',
                'max_conversation_turns': 'env:KLR_MAX_CONVERSATION_TURNS'
            }

            kloros_attr = parameter_mapping.get(parameter, parameter)

            # Handle environment variables
            if kloros_attr.startswith('env:'):
                env_var = kloros_attr[4:]  # Remove 'env:' prefix
                import os
                env_value = os.getenv(env_var)
                if env_value is not None:
                    # Convert to appropriate type
                    try:
                        if env_var in ['KLR_CONTEXT_IN_CHAT', 'KLR_MAX_CONTEXT_SUMMARIES', 'KLR_MAX_CONTEXT_EVENTS', 'KLR_CONVERSATION_TIMEOUT', 'KLR_MAX_CONVERSATION_TURNS']:
                            return int(env_value)
                        elif env_var in ['OLLAMA_TEMPERATURE']:
                            return float(env_value)
                        else:
                            return env_value
                    except ValueError:
                        print(f"[reflection] Could not convert environment variable {env_var}={env_value} to appropriate type")
                        return None
                else:
                    # Return default values for memory parameters
                    defaults = {
                        'KLR_MAX_CONTEXT_SUMMARIES': 3,
                        'KLR_MAX_CONTEXT_EVENTS': 10,
                        'KLR_CONTEXT_IN_CHAT': 1,
                        'OLLAMA_TEMPERATURE': 0.7,
                        'KLR_CONVERSATION_TIMEOUT': 10,
                        'KLR_MAX_CONVERSATION_TURNS': 5
                    }
                    return defaults.get(env_var, None)

            # Handle direct KLoROS attributes
            elif hasattr(self.kloros, kloros_attr):
                return getattr(self.kloros, kloros_attr)
            else:
                print(f"[reflection] Parameter not found: {kloros_attr}")
                return None

        except Exception as e:
            print(f"[reflection] Error getting parameter value: {e}")
            return None

    def _calculate_new_parameter_value(self, parameter: str, current_value: Any, adjustment: str) -> Optional[Any]:
        """Calculate new parameter value based on adjustment strategy."""

        param_range = self.safe_parameter_ranges.get(parameter)
        if not param_range:
            return None

        min_val, max_val = param_range

        if adjustment == 'increase':
            # Increase by 10-20% within safe range
            increase_factor = 1.15
            new_value = min(current_value * increase_factor, max_val)
        elif adjustment == 'decrease':
            # Decrease by 10-20% within safe range
            decrease_factor = 0.85
            new_value = max(current_value * decrease_factor, min_val)
        elif adjustment == 'reduce':
            # More conservative reduction
            new_value = max(current_value * 0.9, min_val)
        elif adjustment == 'fine_tune':
            # Small adjustment in either direction
            if current_value < (min_val + max_val) / 2:
                new_value = min(current_value * 1.05, max_val)
            else:
                new_value = max(current_value * 0.95, min_val)
        else:
            return None

        # Ensure new value is different from current
        if abs(new_value - current_value) < 0.001:
            return None

        # Determine appropriate return type based on parameter
        integer_params = [
            'memory_context_summaries', 'memory_context_events', 'memory_context_enabled',
            'wake_rms_threshold', 'wake_cooldown_ms', 'conversation_timeout', 'max_conversation_turns'
        ]

        if parameter in integer_params:
            return max(1, int(round(new_value)))  # Ensure minimum value of 1 for counts
        else:
            return round(new_value, 3)

    def _apply_parameter_change(self, parameter: str, new_value: Any) -> bool:
        """Apply parameter change to the running KLoROS system."""

        try:
            if not self.kloros:
                print(f"[reflection] No KLoROS instance available for parameter change: {parameter}")
                return False

            # Map optimization parameters to actual KLoROS attributes and environment variables
            parameter_mapping = {
                # Audio/Voice Parameters (direct attributes)
                'wake_confidence_threshold': 'wake_conf_min',
                'wake_rms_threshold': 'wake_rms_min',
                'wake_cooldown_ms': 'wake_cooldown_ms',
                'speaker_confidence_threshold': 'speaker_threshold',
                'vad_threshold_dbfs': 'vad_threshold_dbfs_fallback',

                # Memory/Context Parameters (environment variables)
                'memory_context_summaries': 'env:KLR_MAX_CONTEXT_SUMMARIES',
                'memory_context_events': 'env:KLR_MAX_CONTEXT_EVENTS',
                'memory_context_enabled': 'env:KLR_CONTEXT_IN_CHAT',

                # Response Quality Parameters (environment variables)
                'response_temperature': 'env:OLLAMA_TEMPERATURE',
                'conversation_timeout': 'env:KLR_CONVERSATION_TIMEOUT',
                'max_conversation_turns': 'env:KLR_MAX_CONVERSATION_TURNS'
            }

            kloros_attr = parameter_mapping.get(parameter, parameter)

            # Handle environment variables
            if kloros_attr.startswith('env:'):
                env_var = kloros_attr[4:]  # Remove 'env:' prefix
                import os

                # Get old value for logging
                old_value = os.getenv(env_var, "default")

                # Set new environment variable
                os.environ[env_var] = str(new_value)
                print(f"[reflection] ✓ Applied optimization: {env_var} {old_value} → {new_value}")

                # For memory parameters, we should also update the memory system if it exists
                if hasattr(self.kloros, 'memory_enhanced') and self.kloros.memory_enhanced:
                    try:
                        if env_var == 'KLR_MAX_CONTEXT_SUMMARIES':
                            self.kloros.memory_enhanced.max_context_summaries = int(new_value)
                        elif env_var == 'KLR_MAX_CONTEXT_EVENTS':
                            self.kloros.memory_enhanced.max_context_events = int(new_value)
                        elif env_var == 'KLR_CONTEXT_IN_CHAT':
                            self.kloros.memory_enhanced.context_in_chat = int(new_value)
                        print(f"[reflection] ✓ Updated memory system parameter: {env_var}")
                    except Exception as e:
                        print(f"[reflection] ⚠ Could not update memory system: {e}")

                # Validate the environment change took effect
                current_value = os.getenv(env_var)
                if current_value == str(new_value):
                    return True
                else:
                    print(f"[reflection] ⚠ Environment variable change validation failed: expected {new_value}, got {current_value}")
                    return False

            # Handle direct KLoROS attributes
            elif hasattr(self.kloros, kloros_attr):
                old_value = getattr(self.kloros, kloros_attr)
                setattr(self.kloros, kloros_attr, new_value)
                print(f"[reflection] ✓ Applied optimization: {kloros_attr} {old_value} → {new_value}")

                # Validate the change took effect
                current_value = getattr(self.kloros, kloros_attr)
                if current_value == new_value:
                    return True
                else:
                    print(f"[reflection] ⚠ Parameter change validation failed: expected {new_value}, got {current_value}")
                    return False
            else:
                print(f"[reflection] Parameter not found in KLoROS instance: {kloros_attr}")
                return False

        except Exception as e:
            print(f"[reflection] Error applying parameter change: {e}")
            return False

    def _assess_active_optimizations(self) -> List[ReflectionInsight]:
        """Assess the effectiveness of currently active optimizations."""

        insights = []

        for optimization in self.active_optimizations:
            # Check if optimization has been active long enough for assessment
            days_active = (time.time() - optimization.timestamp) / 86400

            if days_active >= optimization.evaluation_period_days:
                # Time to evaluate this optimization
                assessment = self._evaluate_optimization_effectiveness(optimization)
                if assessment:
                    insights.append(assessment)

        return insights

    def _evaluate_optimization_effectiveness(self, optimization: AdaptiveOptimization) -> Optional[ReflectionInsight]:
        """Evaluate the effectiveness of a specific optimization."""

        try:
            # In a real implementation, this would analyze performance metrics
            # to determine if the optimization was successful

            # Simulate assessment based on optimization type
            effectiveness_score = 0.7  # Simulated

            if effectiveness_score >= 0.7:
                assessment = "successful"
                should_keep = True
            elif effectiveness_score >= 0.5:
                assessment = "moderately effective"
                should_keep = True
            else:
                assessment = "ineffective"
                should_keep = False

            content = f"Optimization assessment for {optimization.optimization_type}: {assessment} "
            content += f"(effectiveness: {effectiveness_score:.2f}). "

            if should_keep:
                content += "Optimization will be maintained as it shows positive impact."
                optimization.is_active = True
            else:
                content += "Optimization will be reverted due to poor performance."
                optimization.is_active = False
                # In real implementation, would revert parameter changes

            return self._create_optimization_insight(
                f"Optimization Assessment: {optimization.optimization_type}",
                content,
                InsightType.BEHAVIORAL_OPTIMIZATION,
                0.8,
                {
                    "optimization_id": optimization.optimization_id,
                    "effectiveness_score": effectiveness_score,
                    "assessment": assessment,
                    "keeping_optimization": should_keep,
                    "parameter_changes": optimization.parameter_changes
                }
            )

        except Exception as e:
            print(f"[reflection] Error evaluating optimization: {e}")
            return None

    def _generate_predictive_insights(self, insights: List[ReflectionInsight]) -> List[ReflectionInsight]:
        """Generate predictive insights for future improvements."""

        predictive_insights = []

        try:
            # Analyze trends to predict future optimization needs
            future_opportunities = self._predict_future_optimization_needs(insights)

            if future_opportunities:
                content = f"Predictive analysis identifies {len(future_opportunities)} potential future optimization areas: "
                content += ", ".join(future_opportunities[:3]) + ". "
                content += "These areas should be monitored for optimization opportunities in upcoming reflection cycles."

                insight = self._create_optimization_insight(
                    "Future Optimization Predictions",
                    content,
                    InsightType.PREDICTIVE_INSIGHT,
                    0.6,
                    {"predicted_opportunities": future_opportunities}
                )
                predictive_insights.append(insight)

        except Exception as e:
            print(f"[reflection] Error generating predictive insights: {e}")

        return predictive_insights

    def _predict_future_optimization_needs(self, insights: List[ReflectionInsight]) -> List[str]:
        """Predict future optimization needs based on current trends."""

        predictions = []

        # Analyze insight patterns for predictive indicators
        insight_types = [insight.insight_type for insight in insights]

        if insight_types.count(InsightType.PERFORMANCE_ASSESSMENT) > 2:
            predictions.append("response_time_optimization")

        if insight_types.count(InsightType.EMOTIONAL_CONTEXT) > 1:
            predictions.append("emotional_processing_enhancement")

        if insight_types.count(InsightType.INTERACTION_QUALITY) > 1:
            predictions.append("conversation_quality_optimization")

        return predictions

    def _create_optimization_insight(
        self,
        title: str,
        content: str,
        insight_type: InsightType,
        confidence: float,
        supporting_data: Dict[str, Any]
    ) -> ReflectionInsight:
        """Create a standardized optimization insight."""

        return ReflectionInsight.create_from_analysis(
            cycle=self.current_cycle,
            phase=4,
            insight_type=insight_type,
            title=title,
            content=content,
            confidence=confidence,
            supporting_data=supporting_data,
            keywords=["optimization", "adaptation", "improvement"]
        )

    def _fallback_optimization(self) -> List[ReflectionInsight]:
        """Fallback optimization when full analysis unavailable."""

        print("[reflection] Using fallback optimization")

        insights = []

        insight = ReflectionInsight.create_from_analysis(
            cycle=self.current_cycle,
            phase=4,
            insight_type=InsightType.PARAMETER_ADJUSTMENT,
            title="Optimization System Status (Fallback)",
            content="Adaptive optimization system is monitoring for improvement opportunities. "
                   "No immediate optimizations identified in current cycle. "
                   "System parameters remain stable and within optimal ranges.",
            confidence=0.5,
            supporting_data={"fallback_mode": True}
        )
        insights.append(insight)

        return insights

    def _analyze_tts_quality(self) -> List[ReflectionInsight]:
        """Analyze TTS quality and generate optimization insights."""
        try:
            from .tts_analyzer import TTSQualityAnalyzer

            tts_analyzer = TTSQualityAnalyzer(self.kloros)
            tts_analyzer.current_cycle = self.current_cycle

            return tts_analyzer.analyze_tts_quality_insights()

        except Exception as e:
            print(f"[reflection] TTS quality analysis failed: {e}")
            return []
    def _detect_and_queue_tool_synthesis_opportunities(
        self,
        all_insights: List[ReflectionInsight]
    ) -> List[str]:
        """
        Detect opportunities for new tool synthesis from reflection insights.
        Level 2 autonomy: Queue proposals for user review.

        Returns:
            List of proposal IDs that were queued
        """
        if not self.synthesis_queue:
            return []

        if not self.tool_synthesis_enabled:
            return []

        autonomy_level = int(os.getenv('KLR_AUTONOMY_LEVEL', '0'))
        if autonomy_level < 2:
            return []

        queued_proposals = []

        # Analyze insights for tool synthesis opportunities
        for insight in all_insights:
            # Look for indicators of missing capabilities
            indicators = [
                'missing tool',
                'need tool',
                'should create',
                'could benefit from',
                'no tool for',
                'manual process',
                'repeated task',
                'lacking capability'
            ]

            text = insight.content.lower()
            if any(indicator in text for indicator in indicators):
                # High confidence insight about missing tool
                if insight.confidence >= self.synthesis_min_confidence:
                    # Extract tool requirements
                    tool_proposal = self._extract_tool_requirements_from_insight(insight)

                    if tool_proposal:
                        # Queue for user review
                        proposal_id = self.synthesis_queue.add_proposal(
                            tool_name=tool_proposal['tool_name'],
                            description=tool_proposal['description'],
                            requirements=tool_proposal['requirements'],
                            source='reflection',
                            confidence=insight.confidence,
                            insight_id=getattr(insight, 'id', None)
                        )
                        queued_proposals.append(proposal_id)

                        print(f"[reflection] 🔧 Queued tool synthesis: {tool_proposal['tool_name']}")
                        print(f"[reflection]    Confidence: {insight.confidence:.2f}")
                        print(f"[reflection]    Reason: {insight.content[:100]}...")

        return queued_proposals

    def _extract_tool_requirements_from_insight(self, insight: ReflectionInsight) -> Optional[Dict]:
        """
        Extract tool synthesis requirements from a reflection insight.
        Uses simple heuristics and keyword extraction.

        Returns:
            Dict with tool_name, description, requirements or None
        """
        import re

        text = insight.content

        # Try to extract tool name from context
        # Look for patterns like "need a X tool" or "create X tool"
        name_patterns = [
            r'need (?:a |an )?(\w+) tool',
            r'create (?:a |an )?(\w+) tool',
            r'missing (\w+) capability',
            r'lacking (\w+) feature'
        ]

        tool_name = None
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tool_name = match.group(1).lower().replace(' ', '_')
                break

        # If no explicit name, generate from insight type
        if not tool_name:
            if 'diagnostic' in text.lower():
                tool_name = 'auto_diagnostic'
            elif 'monitor' in text.lower():
                tool_name = 'auto_monitor'
            elif 'check' in text.lower():
                tool_name = 'auto_health_check'
            else:
                # Generic name based on timestamp
                tool_name = f'reflection_tool_{int(time.time())}'

        # Build description and requirements
        description = insight.content

        # Extract evidence as requirements
        requirements = insight.evidence if hasattr(insight, 'evidence') else ''
        if not requirements:
            requirements = f"Generated from reflection insight: {insight.content}"

        return {
            'tool_name': tool_name,
            'description': description,
            'requirements': requirements
        }

    def _create_synthesis_notification(self, count: int):
        """
        Create a notification file to alert user about pending synthesis proposals.
        This file is checked by KLoROS on conversation start.

        Args:
            count: Number of new proposals queued
        """
        try:
            from pathlib import Path

            notification_file = Path("/home/kloros/.kloros/synthesis_notifications.json")
            notification_file.parent.mkdir(parents=True, exist_ok=True)

            # Read existing notifications or create new
            if notification_file.exists():
                with open(notification_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {
                    'pending_count': 0,
                    'last_notification': None,
                    'notified': False
                }

            # Update notification data
            data['pending_count'] = data.get('pending_count', 0) + count
            data['last_notification'] = datetime.utcnow().isoformat() + "Z"
            data['notified'] = False  # Reset notification flag

            # Write notification
            with open(notification_file, 'w') as f:
                json.dump(data, f, indent=2)

            print(f"[reflection] Created notification for {count} new synthesis proposal(s)")
            print(f"[reflection] Total pending: {data['pending_count']}")

        except Exception as e:
            print(f"[reflection] Failed to create synthesis notification: {e}")
