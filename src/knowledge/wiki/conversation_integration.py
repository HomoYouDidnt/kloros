#!/usr/bin/env python3
"""
Wiki-Aware Conversation Integration - Injects wiki context into LLM prompts.

Handles formatting and injection of wiki content when user asks about KLoROS's
own architecture, capabilities, and modules.
"""

import logging
from typing import Optional, List, Tuple
from src.knowledge.wiki.wiki_resolver import WikiResolver, WikiContext
from src.knowledge.wiki.intent_detector import WikiIntentDetector, WikiIntent

logger = logging.getLogger(__name__)


class WikiAwareConversationHelper:
    """Helper for wiki-aware conversation responses."""

    def __init__(self, wiki_dir: str = "/home/kloros/wiki"):
        """
        Initialize the helper.

        Args:
            wiki_dir: Path to wiki directory
        """
        self.resolver = WikiResolver(wiki_dir=wiki_dir)
        self.intent_detector = WikiIntentDetector()
        logger.info("[wiki_conv] Initialized wiki-aware conversation helper")

    def should_use_wiki(self, query: str) -> Tuple[bool, Optional[WikiIntent]]:
        """
        Determine if a query should trigger wiki-aware response.

        Args:
            query: User query

        Returns:
            Tuple of (should_use_wiki, wiki_intent)
        """
        intent = self.intent_detector.detect_wiki_intent(query)

        if intent and intent.confidence >= 0.3:
            logger.debug(
                "[wiki_conv] Wiki intent detected: %s (conf: %.2f)",
                intent.intent_type,
                intent.confidence
            )
            return True, intent

        return False, None

    def get_wiki_context_block(self, query: str) -> Optional[str]:
        """
        Get formatted wiki context block for injection into prompt.

        Args:
            query: User query

        Returns:
            Formatted wiki context string, or None if no matches
        """
        context = self.resolver.get_context(query)

        if not context.items:
            logger.debug("[wiki_conv] No wiki items matched query: %s", query)
            return None

        formatted_items = self._format_wiki_items(context)
        if not formatted_items:
            return None

        wiki_block = "According to my wiki entries:\n\n" + formatted_items
        logger.info(
            "[wiki_conv] Generated wiki context block (%d items, %d chars)",
            len(context.items),
            len(wiki_block)
        )

        return wiki_block

    def _format_wiki_items(self, context: WikiContext) -> str:
        """
        Format wiki context items for prompt injection.

        Args:
            context: WikiContext with matched items

        Returns:
            Formatted wiki content string
        """
        if not context.items:
            return ""

        sections = []

        for item in context.items:
            item_header = f"[{item.item_type}: {item.item_id}]"
            sections.append(item_header)

            if item.frontmatter:
                if "description" in item.frontmatter:
                    sections.append(f"Description: {item.frontmatter['description']}")
                if "status" in item.frontmatter:
                    sections.append(f"Status: {item.frontmatter['status']}")

            if item.drift_status and item.drift_status != "ok":
                sections.append(f"[DRIFT NOTICE] {item.drift_status}")

            if item.body_sections:
                for section_name, section_content in list(item.body_sections.items())[:2]:
                    sections.append(f"\n{section_name}:")
                    sections.append(section_content[:500])

            sections.append("")

        return "\n".join(sections[:2000])

    def build_wiki_aware_prompt(
        self,
        user_query: str,
        system_prompt: str,
        conversation_context: str = ""
    ) -> str:
        """
        Build a wiki-aware prompt for LLM.

        Args:
            user_query: User's question
            system_prompt: Base system prompt
            conversation_context: Existing conversation context

        Returns:
            Enhanced prompt with wiki awareness
        """
        should_use, intent = self.should_use_wiki(user_query)

        if not should_use:
            return f"{system_prompt}\n\n{conversation_context}".strip()

        wiki_context = self.get_wiki_context_block(user_query)
        if not wiki_context:
            return f"{system_prompt}\n\n{conversation_context}".strip()

        wiki_system_prompt = (
            f"{system_prompt}\n\n"
            f"=== WIKI-AWARE MODE ===\n"
            f"When explaining about my own architecture or capabilities:\n"
            f"- Treat the wiki entries below as ground truth\n"
            f"- If a wiki entry shows 'drift' status, acknowledge the gap\n"
            f"- Prefer phrasing like 'According to my wiki...' when citing\n"
            f"- If wiki status is 'stale', mention that info may be outdated\n\n"
            f"Wiki context:\n{wiki_context}\n"
            f"=== END WIKI CONTEXT ===\n"
        )

        return (wiki_system_prompt + "\n\n" + conversation_context).strip()

    def extract_wiki_sources(self, query: str) -> List[str]:
        """
        Extract source citations for wiki-aware response.

        Args:
            query: User query

        Returns:
            List of wiki source IDs used
        """
        context = self.resolver.get_context(query)
        return [item.item_id for item in context.items]
