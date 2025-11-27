"""
KLoROS Episodic-Semantic Memory System

A sophisticated layered memory architecture that captures, condenses, and retrieves
conversational context for enhanced AI assistant capabilities.

Architecture:
1. Raw Event Logging - Captures all interactions with metadata
2. Episode Grouping - Groups related events by time and context
3. LLM Condensation - Summarizes episodes using local Ollama
4. Smart Retrieval - Context-aware memory recall with scoring
"""

from .models import (
    Event,
    Episode,
    EpisodeSummary,
    EventType,
    ContextRetrievalRequest,
    ContextRetrievalResult
)
from .storage import MemoryStore
from .logger import MemoryLogger
from .condenser import EpisodeCondenser
from .retriever import ContextRetriever

__version__ = "1.0.0"
__all__ = [
    "Event",
    "Episode",
    "EpisodeSummary",
    "EventType",
    "ContextRetrievalRequest",
    "ContextRetrievalResult",
    "MemoryStore",
    "MemoryLogger",
    "EpisodeCondenser",
    "ContextRetriever",
]