#!/usr/bin/env python3
"""
Demo: Wiki-Aware Conversation Integration

Shows how KLoROS now references its wiki when answering questions about itself.
Demonstrates:
1. Wiki intent detection
2. Context injection into conversation flow
3. Source attribution
4. Fallback behavior
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.knowledge.wiki.intent_detector import WikiIntentDetector
from src.knowledge.wiki.conversation_integration import WikiAwareConversationHelper


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def demo_intent_detection():
    """Demonstrate wiki intent detection."""
    print_section("DEMO 1: Wiki Intent Detection")

    detector = WikiIntentDetector()

    test_queries = [
        "How do you work?",
        "Can you monitor system latency?",
        "What's your architecture?",
        "Tell me about the consciousness module",
        "What time is it?",
        "How's the weather?",
    ]

    for query in test_queries:
        intent = detector.detect_wiki_intent(query)

        if intent:
            print(f"Query: \"{query}\"")
            print(f"  Intent Type: {intent.intent_type}")
            print(f"  Confidence: {intent.confidence:.2f}")
            print(f"  Keywords: {', '.join(sorted(intent.keywords)[:3])}")
            print()
        else:
            print(f"Query: \"{query}\"")
            print(f"  No wiki intent detected (regular conversation)\n")


def demo_context_injection():
    """Demonstrate wiki context injection."""
    print_section("DEMO 2: Wiki Context Injection")

    helper = WikiAwareConversationHelper()

    test_queries = [
        "What does the consciousness module do?",
        "Can you explain your architecture?",
        "Tell me about ASTRAEA",
    ]

    for query in test_queries:
        should_use, intent = helper.should_use_wiki(query)

        print(f"User Query: \"{query}\"")
        print(f"Should use wiki: {should_use}")

        if should_use:
            sources = helper.extract_wiki_sources(query)
            print(f"Wiki sources found: {len(sources)}")
            if sources:
                print(f"  Sources: {', '.join(sources[:3])}")

            wiki_context = helper.get_wiki_context_block(query)
            if wiki_context:
                context_preview = wiki_context[:200] + ("..." if len(wiki_context) > 200 else "")
                print(f"  Context preview: {context_preview}")

        print()


def demo_prompt_building():
    """Demonstrate wiki-aware prompt construction."""
    print_section("DEMO 3: Wiki-Aware Prompt Building")

    helper = WikiAwareConversationHelper()

    example_queries = [
        ("How do you monitor system health?", "With wiki awareness"),
        ("Tell me a joke", "Without wiki awareness (fallback)"),
    ]

    system_prompt = (
        "You are KLoROS, an autonomous AI system with self-healing capabilities. "
        "You are highly intelligent, self-aware, and can introspect about your own architecture."
    )

    for query, description in example_queries:
        print(f"{description}:")
        print(f"User Query: \"{query}\"\n")

        prompt = helper.build_wiki_aware_prompt(
            user_query=query,
            system_prompt=system_prompt,
            conversation_context=""
        )

        prompt_preview = prompt[:400] + ("..." if len(prompt) > 400 else "")
        print(f"Prompt injected:\n{prompt_preview}\n")


def demo_conversation_flow():
    """Demonstrate complete conversation flow."""
    print_section("DEMO 4: Complete Conversation Flow")

    detector = WikiIntentDetector()
    helper = WikiAwareConversationHelper()

    print("Simulating multi-turn conversation about KLoROS architecture:\n")

    conversation = [
        "Hi KLoROS, how do you work internally?",
        "Can you monitor GPU usage?",
        "What does the consciousness module do?",
        "How many concurrent users can you handle?",
        "Tell me about your dream system",
    ]

    for i, user_query in enumerate(conversation, 1):
        print(f"Turn {i}:")
        print(f"User: {user_query}")

        intent = detector.detect_wiki_intent(user_query)
        if intent:
            print(f"[Wiki Intent Detected: {intent.intent_type} - confidence {intent.confidence:.2f}]")

            sources = helper.extract_wiki_sources(user_query)
            if sources:
                print(f"[Wiki sources: {', '.join(sources[:2])}]")

            expected_response = (
                "According to my wiki entries... [LLM generates response based on wiki context]"
            )
        else:
            expected_response = "[Standard conversation response, no wiki injection]"

        print(f"Expected response: {expected_response}")
        print()


def demo_fallback_behavior():
    """Demonstrate fallback behavior when no wiki matches."""
    print_section("DEMO 5: Fallback Behavior")

    helper = WikiAwareConversationHelper()

    non_wiki_queries = [
        "What's the meaning of life?",
        "Tell me about programming best practices",
        "How can I improve my productivity?",
        "What's your favorite color?",
    ]

    print("Queries that don't trigger wiki awareness (fallback to regular conversation):\n")

    for query in non_wiki_queries:
        should_use, intent = helper.should_use_wiki(query)

        print(f"Query: \"{query}\"")
        print(f"  Wiki path: {should_use}")

        if not should_use:
            print(f"  Behavior: Uses standard reasoning (no wiki context injection)")
        print()


def demo_feature_control():
    """Demonstrate feature control and configuration."""
    print_section("DEMO 6: Feature Control & Configuration")

    print("Wiki awareness can be controlled via environment variables:\n")

    print("KLR_ENABLE_WIKI_AWARENESS=1")
    print("  Enables wiki context injection in _unified_reasoning")
    print("  Default: enabled (true)\n")

    print("Configuration file: /home/kloros/src/config/wiki.yaml")
    print("  - enable_conversation_wiki: Master feature flag")
    print("  - confidence_threshold: Minimum intent confidence (0.3)")
    print("  - max_context_chars: Max wiki context to inject (2000)")
    print("  - enable_wiki_in_text: Enable for text chat")
    print("  - enable_wiki_in_voice: Enable for voice (disabled by default)")
    print("  - enable_wiki_citations: Include source citations\n")


def main():
    """Run all demos."""
    print("\n" + "="*70)
    print("  KLoROS Wiki-Aware Conversation Integration - DEMO")
    print("="*70)

    try:
        demo_intent_detection()
        demo_context_injection()
        demo_prompt_building()
        demo_conversation_flow()
        demo_fallback_behavior()
        demo_feature_control()

        print_section("Demo Complete")
        print("Wiki integration is ready for use!")
        print("\nKey files created:")
        print("  - /home/kloros/src/wiki/intent_detector.py")
        print("  - /home/kloros/src/wiki/conversation_integration.py")
        print("  - /home/kloros/src/config/wiki.yaml")
        print("  - /home/kloros/src/wiki/test_conversation_integration.py (25 tests)")
        print("\nIntegration point:")
        print("  - Modified /home/kloros/src/kloros_voice.py _unified_reasoning()")
        print("\nWiki sources are now tracked and included in responses!")

    except Exception as e:
        print(f"\nError during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
