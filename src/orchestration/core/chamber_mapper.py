#!/usr/bin/env python3
"""
Chamber Mapper - Maps Curiosity Questions to D-REAM Experiments

GLaDOS's test chamber selection system. Analyzes curiosity questions
and selects the appropriate Aperture test chamber (D-REAM experiment).
"""

import logging
from typing import Optional, Dict, Any, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)

class _StubDreamConfig:
    """Stub config when D-REAM is deprecated/unavailable."""
    def list_experiment_names(self) -> List[str]:
        return []
    def get_experiment(self, name: str) -> Optional[Dict]:
        return None
    def get_enabled_experiments(self) -> List[Dict]:
        return []

def get_dream_config():
    """Stub - D-REAM deprecated, returns empty config."""
    logger.debug("[chamber_mapper] D-REAM deprecated, using stub config")
    return _StubDreamConfig()


class ChamberMapper:
    """
    Maps curiosity questions to appropriate D-REAM experiments (test chambers).

    Uses keyword matching and semantic analysis to select the right chamber
    for a given question.
    """

    # Keyword patterns mapping to experiment names
    CHAMBER_KEYWORDS = {
        # Conversation optimization
        "conv_quality_spica": [
            "conversation", "chat", "dialogue", "talk", "speak",
            "intent", "context", "turn", "response quality"
        ],

        # Code repair
        "spica_repairlab": [
            "repair", "fix", "bug", "debug", "code quality",
            "patch", "error", "syntax", "compile"
        ],

        # TTS optimization
        "spica_tts": [
            "tts", "text-to-speech", "voice", "audio quality",
            "speech synthesis", "pronunciation", "voice model"
        ],

        # Turn management
        "spica_turns": [
            "turn management", "vad", "voice activity",
            "interrupt", "barge-in", "silence detection"
        ],

        # Planning strategies
        "spica_planning": [
            "planning", "strategy", "plan", "goal",
            "reasoning", "decision making", "search"
        ],

        # System health
        "spica_system_health": [
            "health", "monitoring", "metrics", "cpu",
            "memory", "disk", "performance monitoring"
        ],

        # Tool generation
        "spica_toolgen": [
            "tool", "generate", "synthesis", "create tool",
            "toolgen", "autonomous tool"
        ],

        # RAG optimization
        "rag_opt_spica": [
            "rag", "retrieval", "context", "embedding",
            "chunk", "similarity", "rerank"
        ],

        # GPU allocation
        "spica_gpu_allocation": [
            "gpu", "allocation", "memory", "vram",
            "vllm", "whisper", "model loading"
        ]
    }

    def __init__(self):
        """Initialize chamber mapper with D-REAM config."""
        self.config = get_dream_config()
        logger.info(f"[chamber_mapper] Initialized with {len(self.config.list_experiment_names())} experiments")

    def map_question_to_chamber(self, question: str, question_id: str = "") -> Optional[str]:
        """
        Map a curiosity question to the most appropriate D-REAM experiment.

        Args:
            question: Curiosity question text
            question_id: Question ID (e.g., "discover.module.registry")

        Returns:
            Experiment name or None if no match
        """
        question_lower = question.lower()

        # Check if question_id indicates module discovery (not a chamber question)
        if question_id.startswith("discover.module."):
            logger.info(f"[chamber_mapper] Question {question_id} is module discovery, not chamber task")
            return None

        # Score each chamber by keyword matches
        scores = {}
        for chamber_name, keywords in self.CHAMBER_KEYWORDS.items():
            # Only consider enabled chambers
            experiment = self.config.get_experiment(chamber_name)
            if not experiment or not experiment.get("enabled", False):
                continue

            score = 0
            for keyword in keywords:
                if keyword in question_lower:
                    score += 1

            if score > 0:
                scores[chamber_name] = score

        if not scores:
            logger.warning(f"[chamber_mapper] No chamber match for question: {question}")
            return None

        # Return highest scoring chamber
        best_chamber = max(scores.items(), key=lambda x: x[1])
        chamber_name, score = best_chamber

        logger.info(f"[chamber_mapper] Mapped question to {chamber_name} (score={score})")
        logger.info(f"[chamber_mapper] Question: {question[:100]}...")

        return chamber_name

    def get_default_chamber(self) -> Optional[str]:
        """
        Get default fallback chamber for unmatched questions.

        Returns:
            Default experiment name or None
        """
        # Try conversation as default (most general)
        if self.config.get_experiment("conv_quality_spica"):
            return "conv_quality_spica"

        # Fallback to first enabled experiment
        enabled = self.config.get_enabled_experiments()
        if enabled:
            return enabled[0]["name"]

        return None

    def get_chamber_description(self, chamber_name: str) -> str:
        """
        Get human-readable description of what a chamber tests.

        Args:
            chamber_name: Experiment name

        Returns:
            Description string
        """
        descriptions = {
            "conv_quality_spica": "Conversation quality (intent accuracy, response quality, context retention, latency)",
            "spica_repairlab": "Code repair skills (compile success, test pass rate, patch quality)",
            "spica_tts": "Text-to-speech optimization (audio quality, latency, WER)",
            "spica_turns": "Turn management (VAD accuracy, false triggers, interrupt handling)",
            "spica_planning": "Planning strategies (plan quality, latency, success rate)",
            "spica_system_health": "System health monitoring (detection accuracy, false alarms, overhead)",
            "spica_toolgen": "Autonomous tool synthesis (correctness, safety, performance, robustness)",
            "rag_opt_spica": "RAG optimization (context recall, precision, latency)",
            "spica_gpu_allocation": "GPU resource allocation (STT/LLM latency, utilization, OOM prevention)"
        }
        return descriptions.get(chamber_name, f"Chamber: {chamber_name}")


# Singleton instance
_chamber_mapper = None


def get_chamber_mapper() -> ChamberMapper:
    """Get singleton chamber mapper instance."""
    global _chamber_mapper
    if _chamber_mapper is None:
        _chamber_mapper = ChamberMapper()
    return _chamber_mapper
