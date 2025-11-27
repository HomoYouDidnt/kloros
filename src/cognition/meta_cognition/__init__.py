"""
KLoROS Enhanced Idle Reflection System

A sophisticated multi-phase reflection system that enables genuine self-awareness
and adaptive learning capabilities through progressive analytical layers.

Phases:
1. Semantic Analysis - LLM-powered content understanding
2. Meta-Cognitive Analysis - Self-questioning and performance assessment
3. Cross-Cycle Synthesis - Pattern recognition across time
4. Adaptive Optimization - Self-tuning parameters and behaviors
"""

from .config.reflection_config import ReflectionConfig, get_config, reload_config
from .models.reflection_models import (
    ReflectionInsight, InsightType, ConfidenceLevel,
    ConversationAnalysis, MetaCognitiveState, AdaptiveOptimization,
    ReflectionSummary
)
from .analyzers.semantic_analyzer import SemanticAnalyzer
from .analyzers.meta_cognitive import MetaCognitiveAnalyzer
from .analyzers.insight_synthesizer import InsightSynthesizer
from .analyzers.adaptive_optimizer import AdaptiveOptimizer
from .analyzers.tts_analyzer import TTSQualityAnalyzer

__version__ = "1.0.0"
__author__ = "KLoROS Development Team"

# Main enhanced reflection manager
from .core import EnhancedIdleReflectionManager

__all__ = [
    # Core classes
    'EnhancedIdleReflectionManager',

    # Configuration
    'ReflectionConfig',
    'get_config',
    'reload_config',

    # Models
    'ReflectionInsight',
    'InsightType',
    'ConfidenceLevel',
    'ConversationAnalysis',
    'MetaCognitiveState',
    'AdaptiveOptimization',
    'ReflectionSummary',

    # Analyzers
    'SemanticAnalyzer',
    'MetaCognitiveAnalyzer',
    'InsightSynthesizer',
    'AdaptiveOptimizer',
    'TTSQualityAnalyzer',
]