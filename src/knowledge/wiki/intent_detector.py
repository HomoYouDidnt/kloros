#!/usr/bin/env python3
"""
Wiki Intent Detector - Identifies when user queries are about KLoROS's own architecture/capabilities.

Provides intent detection for wiki-aware conversation responses.
Detects when user is asking about KLoROS's own features, modules, and architecture.
"""

import re
import logging
from dataclasses import dataclass
from typing import Set, Optional

logger = logging.getLogger(__name__)


@dataclass
class WikiIntent:
    """Represents a detected wiki intent."""
    intent_type: str
    confidence: float
    keywords: Set[str]


WIKI_INTENTS = {
    "self_explanation": {
        "keywords": {"how do you", "how are you", "what are you", "describe yourself",
                     "tell me about yourself", "explain yourself", "who are you"},
        "patterns": [r"how do you\s+(\w+)", r"what are you", r"describe\s+yourself"]
    },
    "capability_question": {
        "keywords": {"can you", "do you support", "what can you do", "do you have",
                     "can you monitor", "can you track", "what's your", "what are your"},
        "patterns": [r"can you\s+(\w+)", r"do you\s+(support|have)\s+(\w+)"]
    },
    "architecture_question": {
        "keywords": {"what's your architecture", "how are you structured", "what modules",
                     "module x", "capability", "what does", "explain", "how does"},
        "patterns": [r"what does\s+(\w+)\s+(do|support)", r"(module|capability)\s+(\w+)"]
    },
    "module_question": {
        "keywords": {"module", "component", "subsystem", "system", "latency monitor",
                     "gpu monitor", "consciousness", "dream", "reasoning"},
        "patterns": [r"(module|component)\s+([\w_\.]+)", r"what is\s+([\w_\.]+)"]
    }
}


class WikiIntentDetector:
    """Detects when user queries are about KLoROS's own architecture/capabilities."""

    def __init__(self):
        """Initialize the intent detector."""
        self.intent_keywords = self._build_keyword_map()
        logger.info("[wiki_intent] Detector initialized with %d intent types", len(WIKI_INTENTS))

    def _build_keyword_map(self) -> dict:
        """Build a flat keyword to intent mapping for faster lookup."""
        mapping = {}
        for intent_type, intent_def in WIKI_INTENTS.items():
            for keyword in intent_def["keywords"]:
                if keyword not in mapping:
                    mapping[keyword] = []
                mapping[keyword].append(intent_type)
        return mapping

    def detect_wiki_intent(self, query: str) -> Optional[WikiIntent]:
        """
        Detect if user query is asking about KLoROS's own architecture/capabilities.

        Args:
            query: User query string

        Returns:
            WikiIntent if intent detected, None otherwise
        """
        query_lower = query.lower()

        detected_intents = {}
        detected_keywords = set()

        for keyword, intent_types in self.intent_keywords.items():
            if keyword in query_lower:
                detected_keywords.add(keyword)
                for intent_type in intent_types:
                    detected_intents[intent_type] = detected_intents.get(intent_type, 0) + 1

        for intent_type, intent_def in WIKI_INTENTS.items():
            for pattern in intent_def.get("patterns", []):
                if re.search(pattern, query_lower):
                    detected_intents[intent_type] = detected_intents.get(intent_type, 0) + 1

        if not detected_intents:
            return None

        best_intent = max(detected_intents.items(), key=lambda x: x[1])
        intent_type = best_intent[0]
        confidence = min(best_intent[1] / 3.0, 1.0)

        logger.debug(
            "[wiki_intent] Detected %s (confidence: %.2f, keywords: %s)",
            intent_type,
            confidence,
            detected_keywords
        )

        return WikiIntent(
            intent_type=intent_type,
            confidence=confidence,
            keywords=detected_keywords
        )
