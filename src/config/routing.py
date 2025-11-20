"""
Adaptive Model Routing with Intent Detection and Manual Overrides.

Replaces keyword heuristics with capability-based routing.
"""

import re
from typing import Optional, Tuple
from src.config.models_config import get_ollama_model_for_mode, get_ollama_url_for_mode


class IntentRouter:
    """Route queries to appropriate models based on intent and capabilities."""

    # Manual override tags (@code, @reason, @fast, @think, @deep)
    OVERRIDE_PATTERN = r'@(code|reason|fast|think|deep|coder)'

    # File operation indicators
    FILE_OPS = [
        r'edit\s+file',
        r'modify\s+\w+\.(py|js|ts|java)',
        r'change\s+.*\.(py|js|ts)',
        r'refactor\s+',
        r'create\s+.*\.(py|js|ts)',
        r'write\s+to\s+file',
    ]

    # Code generation indicators
    CODE_GEN = [
        'write code',
        'write a function',
        'write a script',
        'implement',
        'create a tool',
        'generate code',
        'code for',
        'program',
        'synthesize',
        'build a',
        'create function',
        'make a script',
        'write python',
        'write javascript'
    ]

    # Reasoning indicators (analysis, tradeoffs, explanations)
    REASONING = [
        'analyze',
        'compare',
        'tradeoff',
        'why',
        'explain',
        'how does',
        'what are the implications',
        'consider',
        'evaluate',
        'pros and cons',
        'think harder',
        'think about',
        'ponder',
        'deep analysis'
    ]

    # Short queries (generalist model is fine)
    SHORT_THRESHOLD = 50  # characters

    def __init__(self):
        """Initialize router."""
        self.route_history = []  # For debugging/auditing

    def route(self, transcript: str, explicit_mode: Optional[str] = None) -> Tuple[str, str, str]:
        """
        Route query to appropriate model.

        Args:
            transcript: User query text
            explicit_mode: Explicit mode override (from background tasks, etc.)

        Returns:
            (mode, model, url) tuple
        """
        # Priority 1: Explicit mode parameter (for background/async tasks)
        if explicit_mode:
            model = get_ollama_model_for_mode(explicit_mode)
            url = get_ollama_url_for_mode(explicit_mode)
            self._log_route(transcript, explicit_mode, "explicit_param")
            return (explicit_mode, model, url)

        # Priority 2: Manual override tags (@code, @reason, etc.)
        override_match = re.search(self.OVERRIDE_PATTERN, transcript.lower())
        if override_match:
            tag = override_match.group(1)
            # Map tags to modes
            mode_map = {
                'code': 'code',
                'coder': 'code',
                'reason': 'think',
                'think': 'think',
                'deep': 'deep',
                'fast': 'live'
            }
            mode = mode_map.get(tag, 'live')
            model = get_ollama_model_for_mode(mode)
            url = get_ollama_url_for_mode(mode)
            self._log_route(transcript, mode, f"manual_tag:@{tag}")
            return (mode, model, url)

        # Priority 3: File operation detection
        if any(re.search(pattern, transcript.lower()) for pattern in self.FILE_OPS):
            mode = 'code'
            model = get_ollama_model_for_mode(mode)
            url = get_ollama_url_for_mode(mode)
            self._log_route(transcript, mode, "file_operation")
            return (mode, model, url)

        # Priority 4: Code generation detection
        if any(keyword in transcript.lower() for keyword in self.CODE_GEN):
            mode = 'code'
            model = get_ollama_model_for_mode(mode)
            url = get_ollama_url_for_mode(mode)
            self._log_route(transcript, mode, "code_generation")
            return (mode, model, url)

        # Priority 5: Reasoning/analysis detection
        if any(keyword in transcript.lower() for keyword in self.REASONING):
            mode = 'think'
            model = get_ollama_model_for_mode(mode)
            url = get_ollama_url_for_mode(mode)
            self._log_route(transcript, mode, "reasoning_analysis")
            return (mode, model, url)

        # Priority 6: Short queries → fast generalist
        if len(transcript) < self.SHORT_THRESHOLD:
            mode = 'live'
            model = get_ollama_model_for_mode(mode)
            url = get_ollama_url_for_mode(mode)
            self._log_route(transcript, mode, "short_query")
            return (mode, model, url)

        # Default: generalist model
        mode = 'live'
        model = get_ollama_model_for_mode(mode)
        url = get_ollama_url_for_mode(mode)
        self._log_route(transcript, mode, "default")
        return (mode, model, url)

    def _log_route(self, transcript: str, mode: str, reason: str):
        """Log routing decision for debugging."""
        entry = {
            "transcript_preview": transcript[:80],
            "mode": mode,
            "reason": reason
        }
        self.route_history.append(entry)
        # Keep last 100 routes
        if len(self.route_history) > 100:
            self.route_history.pop(0)

    def get_route_stats(self) -> dict:
        """Get routing statistics."""
        if not self.route_history:
            return {}

        mode_counts = {}
        reason_counts = {}

        for entry in self.route_history:
            mode = entry["mode"]
            reason = entry["reason"]

            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        return {
            "total_routes": len(self.route_history),
            "mode_distribution": mode_counts,
            "reason_distribution": reason_counts
        }


# Singleton instance
_router_instance = None

def get_intent_router() -> IntentRouter:
    """Get singleton router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = IntentRouter()
    return _router_instance
