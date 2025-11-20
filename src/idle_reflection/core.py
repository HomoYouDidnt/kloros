"""
Enhanced Idle Reflection Manager - Core Orchestration

Coordinates all four phases of the enhanced reflection system to provide
KLoROS with genuine self-awareness and adaptive learning capabilities.
"""

import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from .config.reflection_config import get_config
from .models.reflection_models import ReflectionInsight, ReflectionSummary
from .analyzers.semantic_analyzer import SemanticAnalyzer
from .analyzers.meta_cognitive import MetaCognitiveAnalyzer
from .analyzers.insight_synthesizer import InsightSynthesizer
from .analyzers.adaptive_optimizer import AdaptiveOptimizer
from .hybrid_introspection import HybridIntrospectionManager


class EnhancedIdleReflectionManager:
    """
    Enhanced reflection manager orchestrating all four analytical phases.

    Provides KLoROS with sophisticated self-awareness capabilities through:
    1. Semantic Analysis (Phase 1) - Understanding conversation content
    2. Meta-Cognitive Analysis (Phase 2) - Self-questioning and assessment
    3. Cross-Cycle Synthesis (Phase 3) - Pattern recognition over time
    4. Adaptive Optimization (Phase 4) - Self-tuning and improvement
    """

    def __init__(self, kloros_instance=None):
        """Initialize enhanced reflection system."""
        self.kloros = kloros_instance
        self.config = get_config()

        # Reflection state
        self.last_reflection_time = time.time()  # Initialize to current time, not 0
        self.reflection_cycle_count = 0

        # Initialize analyzers
        self.semantic_analyzer = SemanticAnalyzer(self.config, kloros_instance)
        self.meta_cognitive_analyzer = MetaCognitiveAnalyzer(self.config, kloros_instance)
        self.insight_synthesizer = InsightSynthesizer(self.config, kloros_instance)
        self.adaptive_optimizer = AdaptiveOptimizer(self.config, kloros_instance)

        # Hybrid introspection system
        self.hybrid_introspection = HybridIntrospectionManager(kloros_instance)

        # Performance tracking
        self.total_insights_generated = 0
        self.phase_performance = {
            1: {'executions': 0, 'insights': 0, 'avg_time_ms': 0.0},
            2: {'executions': 0, 'insights': 0, 'avg_time_ms': 0.0},
            3: {'executions': 0, 'insights': 0, 'avg_time_ms': 0.0},
            4: {'executions': 0, 'insights': 0, 'avg_time_ms': 0.0}
        }

    def should_reflect(self) -> bool:
        """Check if it's time for enhanced reflection cycle."""
        current_time = time.time()
        return (current_time - self.last_reflection_time) >= self.config.reflection_interval

    def perform_enhanced_reflection(self) -> ReflectionSummary:
        """
        Execute complete enhanced reflection cycle with all enabled phases.

        Returns summary of insights generated and analysis performed.
        """
        if not self.should_reflect():
            return None

        cycle_start_time = time.time()
        self.reflection_cycle_count += 1

        print(f"[reflection] ===== Enhanced Reflection Cycle {self.reflection_cycle_count} =====")
        print(f"[reflection] Depth: {self.config.reflection_depth} phases")

        # Track all insights from this cycle
        all_insights = []
        phase_results = {}

        try:
            # Phase 1: Semantic Analysis (if enabled)
            if self.config.reflection_depth >= 1:
                phase1_insights = self._execute_phase_with_timing(
                    1,
                    self.semantic_analyzer.analyze_recent_conversations,
                    self.reflection_cycle_count
                )
                all_insights.extend(phase1_insights)
                phase_results[1] = len(phase1_insights)

            # Phase 2: Meta-Cognitive Analysis (if enabled)
            if self.config.reflection_depth >= 2:
                phase2_insights = self._execute_phase_with_timing(
                    2,
                    self.meta_cognitive_analyzer.perform_meta_cognitive_analysis,
                    self.reflection_cycle_count,
                    all_insights  # Pass semantic insights as context
                )
                all_insights.extend(phase2_insights)
                phase_results[2] = len(phase2_insights)

            # Phase 3: Cross-Cycle Synthesis (if enabled)
            if self.config.reflection_depth >= 3:
                phase3_insights = self._execute_phase_with_timing(
                    3,
                    self.insight_synthesizer.synthesize_historical_insights,
                    self.reflection_cycle_count,
                    all_insights  # Pass current insights for synthesis
                )
                all_insights.extend(phase3_insights)
                phase_results[3] = len(phase3_insights)

            # Phase 4: Adaptive Optimization (if enabled)
            if self.config.reflection_depth >= 4:
                phase4_insights = self._execute_phase_with_timing(
                    4,
                    self.adaptive_optimizer.perform_adaptive_optimization,
                    self.reflection_cycle_count,
                    all_insights  # Pass all insights for optimization analysis
                )
                all_insights.extend(phase4_insights)
                phase_results[4] = len(phase4_insights)

            # Create reflection summary
            cycle_time = (time.time() - cycle_start_time) * 1000
            summary = self._create_reflection_summary(all_insights, phase_results, cycle_time)

            # Log enhanced reflection results
            self._log_enhanced_reflection(summary, all_insights)

            # Store insights in memory system if available
            self._store_insights_in_memory(all_insights)

            # Update tracking
            self.total_insights_generated += len(all_insights)
            self.last_reflection_time = time.time()

            print(f"[reflection] Cycle {self.reflection_cycle_count} complete: "
                  f"{len(all_insights)} insights in {cycle_time:.1f}ms")

            return summary

        except Exception as e:
            print(f"[reflection] Enhanced reflection cycle error: {e}")
            return self._create_error_summary(str(e))

    def _execute_phase_with_timing(self, phase_num: int, phase_func, *args) -> List[ReflectionInsight]:
        """Execute a reflection phase with performance timing."""

        phase_start = time.time()

        try:
            insights = phase_func(*args)
            execution_time = (time.time() - phase_start) * 1000

            # Update performance tracking
            stats = self.phase_performance[phase_num]
            stats['executions'] += 1
            stats['insights'] += len(insights)

            # Update average time (exponential moving average)
            if stats['avg_time_ms'] == 0:
                stats['avg_time_ms'] = execution_time
            else:
                stats['avg_time_ms'] = 0.7 * stats['avg_time_ms'] + 0.3 * execution_time

            return insights

        except Exception as e:
            print(f"[reflection] Phase {phase_num} error: {e}")
            return []

    def _create_reflection_summary(
        self,
        insights: List[ReflectionInsight],
        phase_results: Dict[int, int],
        total_time_ms: float
    ) -> ReflectionSummary:
        """Create summary of reflection cycle results."""

        high_confidence_count = sum(1 for insight in insights if insight.confidence >= 0.7)

        # Extract top insights
        top_insights = sorted(insights, key=lambda x: x.confidence, reverse=True)[:5]
        top_insight_titles = [insight.title for insight in top_insights]

        # Count LLM calls (approximate)
        llm_calls = 0
        for phase in [1, 2, 3, 4]:
            if phase in phase_results and phase_results[phase] > 0:
                llm_calls += phase_results[phase] // 2  # Rough estimate

        return ReflectionSummary(
            cycle_number=self.reflection_cycle_count,
            analysis_depth=self.config.reflection_depth,
            events_analyzed=self._estimate_events_analyzed(),
            conversations_analyzed=self._estimate_conversations_analyzed(),
            insights_generated=len(insights),
            high_confidence_insights=high_confidence_count,
            semantic_analysis_complete=1 in phase_results,
            meta_cognition_complete=2 in phase_results,
            insight_synthesis_complete=3 in phase_results,
            adaptive_optimization_complete=4 in phase_results,
            total_processing_time_ms=total_time_ms,
            llm_calls_made=llm_calls,
            top_insights=top_insight_titles,
            optimizations_applied=sum(1 for insight in insights
                                    if 'optimization' in insight.title.lower()),
            questions_raised=self._extract_questions_from_insights(insights)
        )

    def _estimate_events_analyzed(self) -> int:
        """Estimate number of events analyzed in this cycle."""
        # This would ideally track actual events processed
        # For now, return reasonable estimate based on lookback period
        return min(50, self.config.semantic_analysis_lookback_hours * 2)

    def _estimate_conversations_analyzed(self) -> int:
        """Estimate number of conversations analyzed in this cycle."""
        # This would ideally track actual conversations processed
        return min(10, self.config.semantic_analysis_lookback_hours // 3)

    def _extract_questions_from_insights(self, insights: List[ReflectionInsight]) -> List[str]:
        """Extract questions raised during reflection."""
        questions = []

        for insight in insights:
            if '?' in insight.content:
                # Extract questions from insight content
                sentences = insight.content.split('.')
                for sentence in sentences:
                    if '?' in sentence:
                        question = sentence.strip()
                        if len(question) > 10:  # Filter out very short questions
                            questions.append(question)

        return questions[:5]  # Limit to 5 questions

    def _log_enhanced_reflection(self, summary: ReflectionSummary, insights: List[ReflectionInsight]) -> None:
        """Log enhanced reflection results."""

        try:
            # Create enhanced log entry
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "reflection_type": "enhanced",
                "cycle_number": summary.cycle_number,
                "analysis_depth": summary.analysis_depth,
                "summary": {
                    "insights_generated": summary.insights_generated,
                    "high_confidence_insights": summary.high_confidence_insights,
                    "processing_time_ms": summary.total_processing_time_ms,
                    "phases_completed": {
                        "semantic_analysis": summary.semantic_analysis_complete,
                        "meta_cognition": summary.meta_cognition_complete,
                        "insight_synthesis": summary.insight_synthesis_complete,
                        "adaptive_optimization": summary.adaptive_optimization_complete
                    }
                },
                "top_insights": summary.top_insights,
                "questions_raised": summary.questions_raised,
                "performance_stats": dict(self.phase_performance),
                "enhanced_insights": [
                    {
                        "phase": insight.phase,
                        "type": insight.insight_type,
                        "title": insight.title,
                        "content": insight.content,
                        "confidence": insight.confidence,
                        "keywords": insight.keywords
                    }
                    for insight in insights
                ]
            }

            # Write to reflection log
            with open(self.config.reflection_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, indent=2) + "\n---\n")

        except Exception as e:
            print(f"[reflection] Error logging enhanced reflection: {e}")

    def _store_insights_in_memory(self, insights: List[ReflectionInsight]) -> None:
        """Store reflection insights in memory system."""

        try:
            if hasattr(self.kloros, "memory_enhanced") and self.kloros.memory_enhanced:
                # Create summary of insights for memory storage
                insight_summary = f"Enhanced reflection cycle {self.reflection_cycle_count}: "
                insight_summary += f"Generated {len(insights)} insights across {self.config.reflection_depth} phases. "

                if insights:
                    top_insight = max(insights, key=lambda x: x.confidence)
                    insight_summary += f"Key insight: {top_insight.title} - {top_insight.content[:100]}..."

                # Calculate average confidence from insights
                avg_confidence = sum(i.confidence for i in insights) / len(insights) if insights else 0.5

                # Log to memory as reflection event
                self.kloros.memory_enhanced.memory_logger.log_event(
                    event_type="self_reflection",
                    content=insight_summary,
                    confidence=avg_confidence,
                    metadata={
                        "cycle_number": self.reflection_cycle_count,
                        "insights_count": len(insights),
                        "analysis_depth": self.config.reflection_depth
                    }
                )

        except Exception as e:
            print(f"[reflection] Error storing insights in memory: {e}")

    def _create_error_summary(self, error_msg: str) -> ReflectionSummary:
        """Create error summary when reflection fails."""

        return ReflectionSummary(
            cycle_number=self.reflection_cycle_count,
            analysis_depth=0,
            events_analyzed=0,
            conversations_analyzed=0,
            insights_generated=0,
            high_confidence_insights=0,
            semantic_analysis_complete=False,
            meta_cognition_complete=False,
            insight_synthesis_complete=False,
            adaptive_optimization_complete=False,
            total_processing_time_ms=0.0,
            llm_calls_made=0,
            top_insights=[f"Reflection error: {error_msg}"],
            optimizations_applied=0,
            questions_raised=[]
        )

    def get_reflection_statistics(self) -> Dict[str, Any]:
        """Get comprehensive reflection system statistics."""

        return {
            "total_cycles": self.reflection_cycle_count,
            "total_insights": self.total_insights_generated,
            "config": self.config.to_dict(),
            "phase_performance": dict(self.phase_performance),
            "avg_insights_per_cycle": (
                self.total_insights_generated / max(self.reflection_cycle_count, 1)
            ),
            "system_health": self._assess_system_health()
        }

    def _assess_system_health(self) -> str:
        """Assess overall health of reflection system."""

        if self.reflection_cycle_count == 0:
            return "not_started"

        # Check if all enabled phases are executing
        enabled_phases = self.config.reflection_depth
        executing_phases = sum(1 for phase_stats in self.phase_performance.values()
                             if phase_stats['executions'] > 0)

        if executing_phases == enabled_phases:
            return "excellent"
        elif executing_phases >= enabled_phases * 0.75:
            return "good"
        elif executing_phases >= enabled_phases * 0.5:
            return "moderate"
        else:
            return "needs_attention"

    def reload_configuration(self) -> bool:
        """Reload configuration and reinitialize analyzers if needed."""

        try:
            from .config.reflection_config import reload_config

            old_depth = self.config.reflection_depth
            self.config = reload_config()

            # Reinitialize analyzers if configuration changed significantly
            if self.config.reflection_depth != old_depth:
                print(f"[reflection] Configuration changed: depth {old_depth} -> {self.config.reflection_depth}")

                self.semantic_analyzer = SemanticAnalyzer(self.config, self.kloros)
                self.meta_cognitive_analyzer = MetaCognitiveAnalyzer(self.config, self.kloros)
                self.insight_synthesizer = InsightSynthesizer(self.config, self.kloros)
                self.adaptive_optimizer = AdaptiveOptimizer(self.config, self.kloros)

            return True

        except Exception as e:
            print(f"[reflection] Error reloading configuration: {e}")
            return False

    # =========================================================================
    # Hybrid Introspection Interface Methods
    # =========================================================================

    def start_conversation_introspection(self, conversation_id: str) -> None:
        """Start real-time introspection for a new conversation."""
        self.hybrid_introspection.start_conversation_introspection(conversation_id)

    def analyze_user_input(self, user_input: str) -> List[ReflectionInsight]:
        """Analyze user input for real-time insights."""
        return self.hybrid_introspection.analyze_user_input(user_input)

    def analyze_response_quality(self, response: str, response_time_ms: float) -> List[ReflectionInsight]:
        """Analyze generated response quality for real-time optimization."""
        return self.hybrid_introspection.analyze_response_quality(response, response_time_ms)

    def get_adaptive_parameters(self) -> Dict[str, Any]:
        """Get current adaptive parameters for real-time optimization."""
        return self.hybrid_introspection.get_adaptive_parameters()

    def end_conversation_introspection(self) -> Dict[str, Any]:
        """End conversation introspection and get summary."""
        return self.hybrid_introspection.end_conversation_introspection()

    def get_hybrid_statistics(self) -> Dict[str, Any]:
        """Get statistics about hybrid introspection system."""
        stats = self.get_reflection_statistics()

        # Add hybrid-specific statistics
        adaptive_params = self.get_adaptive_parameters()

        stats["hybrid_introspection"] = {
            "real_time_enabled": True,
            "current_conversation": self.hybrid_introspection.current_conversation_id is not None,
            "adaptive_parameters": adaptive_params,
            "conversation_complexity": self.hybrid_introspection.conversation_complexity_level,
            "dynamic_wake_threshold": self.hybrid_introspection.dynamic_wake_threshold,
            "dynamic_response_style": self.hybrid_introspection.dynamic_response_style
        }

        if self.hybrid_introspection.current_conversation_id:
            stats["hybrid_introspection"]["active_conversation"] = {
                "id": self.hybrid_introspection.current_conversation_id,
                "duration": time.time() - self.hybrid_introspection.conversation_start_time,
                "insights_generated": len(self.hybrid_introspection.real_time_insights),
                "user_inputs": self.hybrid_introspection.conversation_context.get("user_input_count", 0),
                "responses": self.hybrid_introspection.conversation_context.get("response_count", 0)
            }

        return stats