"""
Topic tracking for KLoROS conversations.

Maintains awareness of conversation topics to improve context and coherence.
"""

import re
from typing import List, Tuple, Set
from collections import Counter


class TopicTracker:
    """Tracks conversation topics to maintain context and coherence."""

    def __init__(self, max_keywords: int = 50):
        """
        Initialize topic tracker.

        Args:
            max_keywords: Maximum number of keywords to track
        """
        self.max_keywords = max_keywords
        self.keyword_counter = Counter()
        self.recent_entities = []  # Track capitalized words (likely entities)
        self.conversation_turns = 0

        # Common stopwords to filter out
        self.stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'should', 'could', 'may', 'might', 'can', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'when',
            'where', 'who', 'why', 'how', 'all', 'each', 'every', 'both', 'few',
            'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
            'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now', 'then',
            'about', 'into', 'through', 'during', 'before', 'after', 'above',
            'below', 'between', 'under', 'again', 'further', 'once', 'here',
            'there', 'also', 'its', 'my', 'your', 'our', 'their'
        }

        # Technical suffixes that indicate important terms
        self.technical_suffixes = {
            'tion', 'ment', 'ness', 'ity', 'er', 'or', 'ist', 'ism',
            'able', 'ible', 'al', 'ial', 'ed', 'ing', 'ly'
        }

    def add_text(self, text: str, is_user: bool = False):
        """
        Add text to topic tracking.

        Args:
            text: The text to analyze for topics
            is_user: Whether this is user input (for weighting)
        """
        if not text.strip():
            return

        self.conversation_turns += 1

        # Extract and track keywords
        keywords = self._extract_keywords(text)
        # Weight user inputs slightly higher (they set the topic)
        weight = 1.5 if is_user else 1.0
        for keyword in keywords:
            self.keyword_counter[keyword] += weight

        # Extract potential named entities (capitalized words/phrases)
        entities = self._extract_entities(text)
        self.recent_entities.extend(entities)

        # Keep only recent entities (last 20)
        if len(self.recent_entities) > 20:
            self.recent_entities = self.recent_entities[-20:]

        # Prevent keyword counter from growing too large
        if len(self.keyword_counter) > self.max_keywords * 2:
            # Keep only top keywords
            top_keywords = dict(self.keyword_counter.most_common(self.max_keywords))
            self.keyword_counter = Counter(top_keywords)

    def get_current_topics(self, n: int = 5) -> List[Tuple[str, float]]:
        """
        Get the top N current topics.

        Args:
            n: Number of top topics to return

        Returns:
            List of (keyword, score) tuples
        """
        return self.keyword_counter.most_common(n)

    def get_topic_summary(self, include_entities: bool = True) -> str:
        """
        Get a formatted summary of current conversation topics.

        Args:
            include_entities: Whether to include named entities in summary

        Returns:
            Human-readable topic summary string
        """
        topics = self.get_current_topics(5)

        if not topics and not self.recent_entities:
            return ""

        parts = []

        # Add main topics
        if topics:
            topic_words = [word for word, count in topics]
            parts.append(f"Topics: {', '.join(topic_words)}")

        # Add entities if requested
        if include_entities and self.recent_entities:
            # Get unique recent entities (maintain order)
            unique_entities = []
            seen = set()
            for entity in reversed(self.recent_entities):
                if entity.lower() not in seen:
                    unique_entities.append(entity)
                    seen.add(entity.lower())
                if len(unique_entities) >= 3:
                    break
            unique_entities.reverse()

            if unique_entities:
                parts.append(f"Entities: {', '.join(unique_entities)}")

        return " | ".join(parts)

    def get_context_for_prompt(self) -> str:
        """
        Get topic context formatted for inclusion in LLM prompt.

        Returns:
            Formatted topic context string
        """
        if not self.keyword_counter and not self.recent_entities:
            return ""

        summary = self.get_topic_summary(include_entities=True)
        return f"[Conversation context: {summary}]"

    def clear(self):
        """Clear topic tracking (for new conversation)."""
        self.keyword_counter.clear()
        self.recent_entities.clear()
        self.conversation_turns = 0

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract meaningful keywords from text.

        Args:
            text: Input text

        Returns:
            List of keywords
        """
        # Convert to lowercase and extract words
        words = re.findall(r'\b[a-z]+\b', text.lower())

        # Filter stopwords and very short words
        keywords = [
            word for word in words
            if word not in self.stopwords and len(word) > 3
        ]

        # Boost technical terms
        boosted_keywords = []
        for word in keywords:
            boosted_keywords.append(word)
            # Add duplicates for technical-looking words (simple heuristic)
            if any(word.endswith(suffix) for suffix in self.technical_suffixes):
                boosted_keywords.append(word)

        return boosted_keywords

    def _extract_entities(self, text: str) -> List[str]:
        """
        Extract potential named entities (capitalized words).

        Simple heuristic: words that start with capital letter and aren't
        at sentence start.

        Args:
            text: Input text

        Returns:
            List of potential entity names
        """
        entities = []

        # Split into sentences
        sentences = re.split(r'[.!?]+', text)

        for sentence in sentences:
            words = sentence.split()
            # Skip first word of each sentence (might be capitalized for grammar)
            for word in words[1:]:
                # Check if word starts with capital and has at least 2 chars
                if word and word[0].isupper() and len(word) > 1:
                    # Clean punctuation
                    clean_word = re.sub(r'[^\w]', '', word)
                    if clean_word:
                        entities.append(clean_word)

        return entities
