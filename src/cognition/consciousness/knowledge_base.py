#!/usr/bin/env python3
"""
Knowledge Base - Provides KLoROS with self-awareness about her architecture and capabilities.

This is the foundation for informed autonomous decision-making.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    Provides system knowledge to enable informed autonomous reasoning.

    MVP version: Simple markdown file reader.
    Future: Vector search, semantic queries, dynamic updates.
    """

    def __init__(self, knowledge_dir: Optional[Path] = None):
        """
        Initialize knowledge base.

        Args:
            knowledge_dir: Path to knowledge directory (defaults to consciousness/knowledge)
        """
        if knowledge_dir is None:
            knowledge_dir = Path(__file__).parent / 'knowledge'

        self.knowledge_dir = Path(knowledge_dir)

        if not self.knowledge_dir.exists():
            logger.warning(f"[knowledge_base] Knowledge directory not found: {self.knowledge_dir}")

        logger.info(f"[knowledge_base] Initialized with dir: {self.knowledge_dir}")

    def get_system_context(self, problem_type: str = "memory") -> str:
        """
        Get relevant system knowledge for a problem type.

        Args:
            problem_type: Type of problem (memory, performance, investigation, etc.)

        Returns:
            Formatted system knowledge context
        """
        context_parts = []

        # Always include subsystems (what KLoROS is)
        subsystems = self._load_markdown('architecture/subsystems.md')
        if subsystems:
            context_parts.append("=== SYSTEM ARCHITECTURE ===\n\n" + subsystems)

        # Always include actions registry (what KLoROS can do)
        actions = self._load_markdown('capabilities/actions_registry.md')
        if actions:
            context_parts.append("\n=== AVAILABLE ACTIONS ===\n\n" + actions)

        # TODO: Add problem-specific knowledge based on problem_type
        # e.g., diagnostics/memory_analysis.md for memory problems

        if not context_parts:
            logger.warning("[knowledge_base] No knowledge loaded - returning empty context")
            return ""

        return "\n\n".join(context_parts)

    def get_subsystem_info(self, subsystem_name: str) -> Optional[str]:
        """
        Get detailed information about a specific subsystem.

        Args:
            subsystem_name: Name of subsystem (e.g., 'investigation_consumer')

        Returns:
            Subsystem information or None if not found
        """
        subsystems_doc = self._load_markdown('architecture/subsystems.md')
        if not subsystems_doc:
            return None

        # Simple extraction: Find section for this subsystem
        # TODO: Parse markdown properly with a library
        lines = subsystems_doc.split('\n')
        capture = False
        subsystem_lines = []

        for line in lines:
            if f'### ' in line and subsystem_name.lower() in line.lower():
                capture = True
                subsystem_lines.append(line)
            elif capture and line.startswith('###'):
                break  # Hit next subsystem
            elif capture:
                subsystem_lines.append(line)

        return '\n'.join(subsystem_lines) if subsystem_lines else None

    def get_action_info(self, action_name: str) -> Optional[str]:
        """
        Get information about a specific action.

        Args:
            action_name: Name of action (e.g., 'reduce_investigation_concurrency')

        Returns:
            Action information or None if not found
        """
        actions_doc = self._load_markdown('capabilities/actions_registry.md')
        if not actions_doc:
            return None

        # Extract section for this action
        lines = actions_doc.split('\n')
        capture = False
        action_lines = []

        for line in lines:
            if '###' in line and action_name.lower().replace('_', ' ') in line.lower():
                capture = True
                action_lines.append(line)
            elif capture and line.startswith('###'):
                break
            elif capture:
                action_lines.append(line)

        return '\n'.join(action_lines) if action_lines else None

    def _load_markdown(self, relative_path: str) -> Optional[str]:
        """
        Load a markdown file from the knowledge base.

        Args:
            relative_path: Path relative to knowledge_dir

        Returns:
            File contents or None if not found
        """
        file_path = self.knowledge_dir / relative_path

        if not file_path.exists():
            logger.debug(f"[knowledge_base] File not found: {file_path}")
            return None

        try:
            content = file_path.read_text()
            logger.debug(f"[knowledge_base] Loaded {len(content)} chars from {relative_path}")
            return content
        except Exception as e:
            logger.error(f"[knowledge_base] Failed to load {file_path}: {e}")
            return None


def main():
    """Test knowledge base."""
    logging.basicConfig(level=logging.INFO)

    kb = KnowledgeBase()

    print("\n=== Testing Knowledge Base ===\n")

    # Test 1: Get system context
    print("1. Getting system context for memory problem...")
    context = kb.get_system_context("memory")
    print(f"   Loaded {len(context)} characters of context\n")
    print(context[:500] + "...\n")

    # Test 2: Get specific subsystem info
    print("2. Getting investigation_consumer info...")
    info = kb.get_subsystem_info("investigation_consumer")
    if info:
        print(f"   Found:\n{info[:300]}...\n")
    else:
        print("   Not found\n")

    # Test 3: Get specific action info
    print("3. Getting reduce_investigation_concurrency action info...")
    action_info = kb.get_action_info("reduce_investigation_concurrency")
    if action_info:
        print(f"   Found:\n{action_info}\n")
    else:
        print("   Not found\n")


if __name__ == "__main__":
    main()
