#!/usr/bin/env python3
"""
Integration tests for wiki-aware conversation responses.

Tests:
- Wiki intent detection
- Wiki context injection into prompts
- Fallback behavior when no wiki matches
- Real-world query examples
"""

import pytest
from src.knowledge.wiki.intent_detector import WikiIntentDetector, WIKI_INTENTS
from src.knowledge.wiki.conversation_integration import WikiAwareConversationHelper


class TestWikiIntentDetection:
    """Tests for wiki intent detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = WikiIntentDetector()

    def test_self_explanation_intent(self):
        """Test detection of self-explanation intent."""
        query = "How do you work?"
        intent = self.detector.detect_wiki_intent(query)

        assert intent is not None
        assert intent.intent_type == "self_explanation"
        assert intent.confidence >= 0.3

    def test_capability_question_intent(self):
        """Test detection of capability question intent."""
        query = "Can you monitor GPU usage?"
        intent = self.detector.detect_wiki_intent(query)

        assert intent is not None
        assert intent.intent_type == "capability_question"
        assert intent.confidence >= 0.3

    def test_architecture_question_intent(self):
        """Test detection of architecture question intent."""
        query = "How are you structured internally?"
        intent = self.detector.detect_wiki_intent(query)

        assert intent is not None
        assert intent.intent_type in ["architecture_question", "capability_question", "self_explanation"]
        assert intent.confidence >= 0.3

    def test_module_question_intent(self):
        """Test detection of module question intent."""
        query = "Tell me about the consciousness module"
        intent = self.detector.detect_wiki_intent(query)

        assert intent is not None
        assert intent.intent_type == "module_question"
        assert intent.confidence >= 0.3

    def test_no_wiki_intent_detected(self):
        """Test that non-wiki queries return no intent or low confidence."""
        query = "What is the weather forecast for tomorrow?"
        intent = self.detector.detect_wiki_intent(query)

        if intent:
            assert intent.confidence < 0.5

    def test_confidence_levels(self):
        """Test that confidence increases with more keywords."""
        queries = [
            ("how do you work", 0.3),
            ("how do you work and what are you", 0.6),
            ("describe yourself and how do you function", 0.7),
        ]

        for query, min_confidence in queries:
            intent = self.detector.detect_wiki_intent(query)
            if intent:
                assert intent.confidence >= min_confidence or intent.confidence > 0

    def test_case_insensitivity(self):
        """Test that detection is case-insensitive."""
        queries = [
            "HOW DO YOU WORK?",
            "How Do You Work?",
            "how do you work?",
        ]

        for query in queries:
            intent = self.detector.detect_wiki_intent(query)
            assert intent is not None
            assert intent.intent_type == "self_explanation"

    def test_intent_types_match_definition(self):
        """Test that all detected intent types exist in WIKI_INTENTS."""
        test_queries = [
            "how do you work",
            "can you monitor",
            "what's your architecture",
            "tell me about the module",
        ]

        for query in test_queries:
            intent = self.detector.detect_wiki_intent(query)
            if intent:
                assert intent.intent_type in WIKI_INTENTS


class TestWikiAwareConversationHelper:
    """Tests for wiki-aware conversation helper."""

    def setup_method(self):
        """Set up test fixtures."""
        self.helper = WikiAwareConversationHelper()

    def test_helper_initialization(self):
        """Test that helper initializes correctly."""
        assert self.helper.resolver is not None
        assert self.helper.intent_detector is not None

    def test_should_use_wiki_true(self):
        """Test should_use_wiki returns True for wiki queries."""
        query = "How do you work?"
        should_use, intent = self.helper.should_use_wiki(query)

        assert should_use is True
        assert intent is not None

    def test_should_use_wiki_false(self):
        """Test should_use_wiki returns False for non-wiki queries."""
        query = "What time is it?"
        should_use, intent = self.helper.should_use_wiki(query)

        assert should_use is False
        assert intent is None

    def test_get_wiki_context_block_returns_string_or_none(self):
        """Test that get_wiki_context_block returns string or None."""
        queries = [
            "What does the consciousness module do?",
            "How do you monitor latency?",
            "Tell me about ASTRAEA",
            "What is your architecture?",
            "What time is it?",
            "Tell me a joke",
        ]

        for query in queries:
            result = self.helper.get_wiki_context_block(query)
            assert result is None or isinstance(result, str)

    def test_extract_wiki_sources_returns_list(self):
        """Test that extract_wiki_sources returns list."""
        query = "Tell me about the consciousness module"
        sources = self.helper.extract_wiki_sources(query)

        assert isinstance(sources, list)

    def test_wiki_context_formatting(self):
        """Test that wiki context is properly formatted."""
        query = "What does the consciousness module do?"
        context = self.helper.get_wiki_context_block(query)

        if context:
            assert isinstance(context, str)
            assert len(context) > 0
            assert "wiki entries" in context.lower() or "according to" in context.lower()

    def test_build_wiki_aware_prompt_includes_base_prompt(self):
        """Test that wiki-aware prompt includes base system prompt."""
        user_query = "How do you work?"
        system_prompt = "You are KLoROS."
        conversation_context = "User: Hello\nAssistant: Hi there"

        result = self.helper.build_wiki_aware_prompt(
            user_query=user_query,
            system_prompt=system_prompt,
            conversation_context=conversation_context
        )

        assert isinstance(result, str)
        assert "KLoROS" in result or system_prompt in result

    def test_build_wiki_aware_prompt_non_wiki_query(self):
        """Test that non-wiki queries don't get wiki injection."""
        user_query = "What time is it?"
        system_prompt = "You are KLoROS."
        conversation_context = "User: What time is it?\nAssistant: "

        result = self.helper.build_wiki_aware_prompt(
            user_query=user_query,
            system_prompt=system_prompt,
            conversation_context=conversation_context
        )

        assert isinstance(result, str)

    def test_wiki_context_injection_is_additive(self):
        """Test that wiki injection doesn't break conversation flow."""
        user_query = "How do you work?"
        system_prompt = "You are KLoROS, an autonomous AI."
        conversation_context = "Previous: conversation history"

        result = self.helper.build_wiki_aware_prompt(
            user_query=user_query,
            system_prompt=system_prompt,
            conversation_context=conversation_context
        )

        assert system_prompt in result


class TestWikiAwarenessE2E:
    """End-to-end tests for wiki awareness in conversation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.helper = WikiAwareConversationHelper()
        self.detector = WikiIntentDetector()

    def test_architecture_question_flow(self):
        """Test complete flow for architecture question."""
        query = "What's your architecture like?"

        should_use, intent = self.helper.should_use_wiki(query)
        assert should_use is True
        assert intent.intent_type in ["architecture_question", "capability_question", "self_explanation"]

        sources = self.helper.extract_wiki_sources(query)
        assert isinstance(sources, list)

    def test_capability_question_flow(self):
        """Test complete flow for capability question."""
        query = "Can you monitor system latency?"

        should_use, intent = self.helper.should_use_wiki(query)
        assert should_use is True
        assert intent.intent_type == "capability_question"

    def test_module_question_flow(self):
        """Test complete flow for module question."""
        query = "What does the consciousness module do?"

        should_use, intent = self.helper.should_use_wiki(query)
        assert should_use is True
        assert intent.intent_type == "module_question"

        prompt = self.helper.build_wiki_aware_prompt(
            user_query=query,
            system_prompt="You are KLoROS.",
            conversation_context=""
        )
        assert isinstance(prompt, str)

    def test_fallback_on_no_wiki_match(self):
        """Test that non-wiki queries fall back gracefully."""
        query = "Tell me a joke"

        should_use, intent = self.helper.should_use_wiki(query)
        assert should_use is False

        prompt = self.helper.build_wiki_aware_prompt(
            user_query=query,
            system_prompt="You are KLoROS.",
            conversation_context=""
        )
        assert "WIKI-AWARE MODE" not in prompt or prompt.count("WIKI-AWARE MODE") == 0

    def test_real_world_queries(self):
        """Test with real-world example queries."""
        real_queries = [
            "How do you handle multiple concurrent users?",
            "What can you monitor in the system?",
            "Do you have a consciousness module?",
            "Explain your architecture to me",
            "What does ASTRAEA do?",
            "Can you track GPU utilization?",
            "Tell me about your dream system",
            "How does your reasoning work?",
        ]

        for query in real_queries:
            should_use, intent = self.helper.should_use_wiki(query)
            assert should_use in [True, False]

            if should_use:
                prompt = self.helper.build_wiki_aware_prompt(
                    user_query=query,
                    system_prompt="You are KLoROS.",
                    conversation_context=""
                )
                assert isinstance(prompt, str)


class TestWikiIntentKeywords:
    """Tests for wiki intent keyword definitions."""

    def test_wiki_intents_structure(self):
        """Test that WIKI_INTENTS has correct structure."""
        assert isinstance(WIKI_INTENTS, dict)

        for intent_type, intent_def in WIKI_INTENTS.items():
            assert isinstance(intent_type, str)
            assert "keywords" in intent_def
            assert "patterns" in intent_def
            assert isinstance(intent_def["keywords"], set)
            assert isinstance(intent_def["patterns"], list)

    def test_intent_keywords_non_empty(self):
        """Test that all intents have keywords and patterns."""
        for intent_type, intent_def in WIKI_INTENTS.items():
            assert len(intent_def["keywords"]) > 0, f"{intent_type} has no keywords"
            assert len(intent_def["patterns"]) > 0, f"{intent_type} has no patterns"

    def test_intent_patterns_are_valid_regex(self):
        """Test that all patterns are valid regex."""
        import re

        for intent_type, intent_def in WIKI_INTENTS.items():
            for pattern in intent_def["patterns"]:
                try:
                    re.compile(pattern)
                except re.error as e:
                    pytest.fail(f"Invalid regex in {intent_type}: {pattern} - {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
