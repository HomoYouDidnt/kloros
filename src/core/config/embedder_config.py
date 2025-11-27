"""
Embedder model configuration.

DEPRECATED: Use src.config.models_config instead.
This module is kept for backward compatibility only.
"""

from .models_config import (
    get_embedder_model,
    get_embedder_fallbacks as get_fallback_models,
    EMBEDDER_MODEL,
    EMBEDDER_FALLBACKS as FALLBACK_MODELS
)

__all__ = [
    'get_embedder_model',
    'get_fallback_models',
    'EMBEDDER_MODEL',
    'FALLBACK_MODELS'
]
