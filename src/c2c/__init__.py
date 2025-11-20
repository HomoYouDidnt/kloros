"""
C2C (Cache-to-Cache) Module for KLoROS

Enables semantic communication between LLM subsystems via context transfer.
"""

from .cache_manager import C2CManager, ContextCache, inject_context_into_ollama_call
from .claude_bridge import ClaudeC2CManager, ClaudeSessionState, capture_current_session

__all__ = [
    "C2CManager",
    "ContextCache",
    "inject_context_into_ollama_call",
    "ClaudeC2CManager",
    "ClaudeSessionState",
    "capture_current_session"
]
