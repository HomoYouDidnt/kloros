"""
Configuration management for KLoROS enhanced reflection system.

Manages environment variables and settings for progressive analytical layers.
"""

import os
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ReflectionConfig:
    """Configuration for KLoROS reflection system."""

    # Core reflection settings
    reflection_interval: int = 60 * 30  # 30 minutes (reduced from 15 to minimize wasteful cycles)
    reflection_log_path: str = "/home/kloros/.kloros/reflection.log"

    # Analysis depth (1-4 phases)
    reflection_depth: int = 4

    # Phase controls
    enable_semantic_analysis: bool = True
    enable_meta_cognition: bool = True
    enable_insight_synthesis: bool = True
    enable_adaptive_optimization: bool = True

    # LLM settings
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "qwen2.5:7b-instruct-q4_K_M"
    llama_timeout: int = 60

    # Analysis parameters
    semantic_analysis_lookback_hours: int = 24
    meta_cognition_frequency: int = 3  # Every 3rd reflection cycle
    insight_synthesis_cycles: int = 10  # Look back 10 cycles for patterns
    adaptive_optimization_threshold: float = 0.7  # Confidence threshold for changes

    # Performance tuning
    max_analysis_tokens: int = 1000
    batch_analysis_size: int = 20
    fallback_on_llm_failure: bool = True

    @classmethod
    def _get_ollama_url_from_ssot(cls) -> str:
        """Get Ollama URL from SSOT config."""
        try:
            from src.core.config.models_config import get_ollama_url
            return get_ollama_url() + "/api/generate"
        except Exception:
            return "http://localhost:11434/api/generate"

    @classmethod
    def _get_ollama_model_from_ssot(cls) -> str:
        """Get Ollama model from SSOT config."""
        try:
            from src.core.config.models_config import get_ollama_model
            return get_ollama_model()
        except Exception:
            return "meta-llama/Llama-3.1-8B-Instruct"

    @classmethod
    def from_environment(cls) -> 'ReflectionConfig':
        """Create configuration from environment variables."""

        def get_bool(key: str, default: bool) -> bool:
            value = os.getenv(key)
            if value is None:
                return default
            return value.lower() in ('1', 'true', 'yes', 'on')

        def get_int(key: str, default: int) -> int:
            try:
                value = os.getenv(key, str(default))
                # Strip comments added by hot_reload (e.g., "300  # 5 minutes")
                value = value.split('#')[0].strip()
                return int(value)
            except ValueError:
                return default

        def get_float(key: str, default: float) -> float:
            try:
                value = os.getenv(key, str(default))
                # Strip comments added by hot_reload
                value = value.split('#')[0].strip()
                return float(value)
            except ValueError:
                return default

        return cls(
            # Core settings
            reflection_interval=get_int('KLR_REFLECTION_INTERVAL', 60 * 30),
            reflection_log_path=os.getenv('KLR_REFLECTION_LOG_PATH', "/home/kloros/.kloros/reflection.log"),

            # Analysis depth
            reflection_depth=get_int('KLR_REFLECTION_DEPTH', 4),

            # Phase controls
            enable_semantic_analysis=get_bool('KLR_SEMANTIC_ANALYSIS', True),
            enable_meta_cognition=get_bool('KLR_META_COGNITION', True),
            enable_insight_synthesis=get_bool('KLR_INSIGHT_SYNTHESIS', True),
            enable_adaptive_optimization=get_bool('KLR_ADAPTIVE_OPTIMIZATION', True),

            # LLM settings - use SSOT config as fallback
            ollama_url=os.getenv('KLR_OLLAMA_URL') or cls._get_ollama_url_from_ssot(),
            ollama_model=os.getenv('KLR_OLLAMA_MODEL') or cls._get_ollama_model_from_ssot(),
            llama_timeout=get_int('KLR_LLAMA_TIMEOUT', 60),

            # Analysis parameters
            semantic_analysis_lookback_hours=get_int('KLR_SEMANTIC_LOOKBACK_HOURS', 24),
            meta_cognition_frequency=get_int('KLR_META_COGNITION_FREQUENCY', 3),
            insight_synthesis_cycles=get_int('KLR_INSIGHT_SYNTHESIS_CYCLES', 10),
            adaptive_optimization_threshold=get_float('KLR_ADAPTIVE_OPTIMIZATION_THRESHOLD', 0.7),

            # Performance tuning
            max_analysis_tokens=get_int('KLR_MAX_ANALYSIS_TOKENS', 1000),
            batch_analysis_size=get_int('KLR_BATCH_ANALYSIS_SIZE', 20),
            fallback_on_llm_failure=get_bool('KLR_FALLBACK_ON_LLM_FAILURE', True),
        )

    def get_phase_config(self, phase: int) -> Dict[str, Any]:
        """Get configuration for a specific analysis phase."""
        base_config = {
            'ollama_url': self.ollama_url,
            'ollama_model': self.ollama_model,
            'timeout': self.llama_timeout,
            'max_tokens': self.max_analysis_tokens,
            'fallback_on_failure': self.fallback_on_llm_failure,
        }

        if phase == 1:  # Semantic Analysis
            return {
                **base_config,
                'enabled': self.enable_semantic_analysis and self.reflection_depth >= 1,
                'lookback_hours': self.semantic_analysis_lookback_hours,
                'batch_size': self.batch_analysis_size,
            }

        elif phase == 2:  # Meta-Cognition
            return {
                **base_config,
                'enabled': self.enable_meta_cognition and self.reflection_depth >= 2,
                'frequency': self.meta_cognition_frequency,
            }

        elif phase == 3:  # Insight Synthesis
            return {
                **base_config,
                'enabled': self.enable_insight_synthesis and self.reflection_depth >= 3,
                'synthesis_cycles': self.insight_synthesis_cycles,
            }

        elif phase == 4:  # Adaptive Optimization
            return {
                **base_config,
                'enabled': self.enable_adaptive_optimization and self.reflection_depth >= 4,
                'optimization_threshold': self.adaptive_optimization_threshold,
            }

        else:
            return {'enabled': False}

    def validate(self) -> bool:
        """Validate configuration settings."""
        if self.reflection_depth < 1 or self.reflection_depth > 4:
            return False

        if self.reflection_interval < 60:  # Minimum 1 minute
            return False

        if self.adaptive_optimization_threshold < 0.0 or self.adaptive_optimization_threshold > 1.0:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'reflection_interval': self.reflection_interval,
            'reflection_depth': self.reflection_depth,
            'phases': {
                'semantic_analysis': self.enable_semantic_analysis,
                'meta_cognition': self.enable_meta_cognition,
                'insight_synthesis': self.enable_insight_synthesis,
                'adaptive_optimization': self.enable_adaptive_optimization,
            },
            'llm_settings': {
                'model': self.ollama_model,
                'timeout': self.llama_timeout,
                'max_tokens': self.max_analysis_tokens,
            }
        }


# Global configuration instance
_config = None


def get_config() -> ReflectionConfig:
    """Get the global reflection configuration."""
    global _config
    if _config is None:
        _config = ReflectionConfig.from_environment()
        if not _config.validate():
            print("[reflection] Warning: Invalid configuration detected, using defaults")
            _config = ReflectionConfig()
    return _config


def reload_config() -> ReflectionConfig:
    """Reload configuration from environment."""
    global _config
    _config = None
    return get_config()
