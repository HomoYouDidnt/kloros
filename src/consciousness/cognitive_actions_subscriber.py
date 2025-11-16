#!/usr/bin/env python3
"""
Cognitive Actions Subscriber - Affective Action Tier 3

Listens for cognitive-level affective signals (MEMORY_PRESSURE, TASK_FAILURE_PATTERN, etc.)
and executes data/memory operations to relieve cognitive load.

Maps affective states → cognitive actions (memory, analysis, integration).
"""

import json
import time
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


def check_emergency_brake() -> bool:
    """Check if emergency brake is active."""
    brake_flag = Path("/tmp/kloros_emergency_brake_active")
    return brake_flag.exists()


class CognitiveActionHandler:
    """Handles cognitive-level autonomous actions."""

    def __init__(self):
        """Initialize cognitive action handler."""
        self.action_log_path = Path("/tmp/kloros_cognitive_actions.log")
        self.last_action_time = {}
        self.action_cooldown = 300.0  # 5 minutes between same action type

        self.memory_store = None
        self.conversation_logger = None
        self._initialize_memory_systems()

    def _initialize_memory_systems(self) -> None:
        """Initialize episodic memory and conversation logging systems."""
        try:
            from src.kloros_memory.storage import MemoryStore
            from src.kloros_memory.models import EpisodeSummary

            self.memory_store = MemoryStore()
            print("[cognitive_actions] Initialized MemoryStore for episodic memory")
        except Exception as e:
            print(f"[cognitive_actions] Warning: Could not initialize MemoryStore: {e}")
            self.memory_store = None

        try:
            from src.memory.chroma_client import get_client, init_collections, get_embedder
            from src.memory.conversation_logger import ConversationLogger

            client = get_client()
            embedder = get_embedder()
            collections = init_collections(client, embedder)
            self.conversation_logger = ConversationLogger(client, collections)
            print("[cognitive_actions] Initialized ConversationLogger for ChromaDB")
        except Exception as e:
            print(f"[cognitive_actions] Warning: Could not initialize ConversationLogger: {e}")
            self.conversation_logger = None

    def can_execute_action(self, action_type: str) -> bool:
        """
        Check if action can be executed (cooldown check).

        Args:
            action_type: Type of action

        Returns:
            True if action can be executed
        """
        last_time = self.last_action_time.get(action_type, 0.0)
        elapsed = time.time() - last_time
        return elapsed >= self.action_cooldown

    def log_action(self, action_type: str, result: str):
        """
        Log executed action.

        Args:
            action_type: Type of action executed
            result: Result description
        """
        self.last_action_time[action_type] = time.time()

        with open(self.action_log_path, 'a') as f:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp} | {action_type} | {result}\n")

    def _get_recent_conversation_turns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent conversation turns from ChromaDB.

        Args:
            limit: Number of recent turns to retrieve

        Returns:
            List of conversation turns
        """
        if not self.conversation_logger:
            return []

        try:
            return self.conversation_logger.get_recent_turns(n=limit)
        except Exception as e:
            print(f"  Error retrieving recent turns: {e}")
            return []

    def _get_older_conversation_turns(self, offset: int = 10, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get older conversation turns from ChromaDB for archival.

        Args:
            offset: Number of turns to skip
            limit: Number of older turns to retrieve

        Returns:
            List of older conversation turns
        """
        if not self.conversation_logger:
            return []

        try:
            all_docs = self.conversation_logger.conversations.get(
                offset=offset,
                limit=limit
            )

            if not all_docs or not all_docs['ids']:
                return []

            turns = []
            for i in range(len(all_docs['ids'])):
                turns.append({
                    'id': all_docs['ids'][i],
                    'document': all_docs['documents'][i],
                    'metadata': all_docs['metadatas'][i]
                })

            return turns
        except Exception as e:
            print(f"  Error retrieving older turns: {e}")
            return []

    def _create_summary_from_turns(self, turns: List[Dict[str, Any]]) -> str:
        """
        Create a contextual summary from conversation turns.

        Args:
            turns: List of conversation turns to summarize

        Returns:
            Summary text
        """
        if not turns:
            return "No content to summarize"

        try:
            summary_parts = []
            summary_parts.append(f"Summarized {len(turns)} conversation turns:")

            user_count = 0
            system_count = 0
            topics = set()

            for turn in turns:
                doc = turn.get('document', '')
                metadata = turn.get('metadata', {})

                if metadata.get('speaker') == 'user':
                    user_count += 1
                    if len(doc) > 10:
                        summary_parts.append(f"- User: {doc[:80]}...")
                elif metadata.get('speaker') == 'system':
                    system_count += 1
                    if len(doc) > 10:
                        summary_parts.append(f"- Response: {doc[:80]}...")

            summary_text = "\n".join(summary_parts[:20])
            return summary_text if summary_text else "Archived context"

        except Exception as e:
            print(f"  Error creating summary: {e}")
            return f"Error summarizing content: {e}"

    def _store_summary_to_episodic_memory(self, summary_record: Dict[str, Any]) -> bool:
        """
        Store a summary to episodic memory system.

        Args:
            summary_record: Dictionary with summary data

        Returns:
            True if storage succeeded
        """
        if not self.memory_store:
            print("  Memory store not available, skipping episodic storage")
            return False

        try:
            from src.kloros_memory.models import EpisodeSummary, EventType
            from src.kloros_memory.models import Event
            import json

            summary_text = summary_record.get('summary', 'Context archived')
            evidence = summary_record.get('evidence', [])
            turns_compressed = summary_record.get('turns_compressed', 0)

            metadata = {
                'reason': summary_record.get('reason', 'memory_pressure'),
                'turns_compressed': turns_compressed,
                'evidence': evidence,
                'archived_at': summary_record.get('timestamp')
            }

            event = Event(
                timestamp=time.time(),
                event_type=EventType.SYSTEM_NOTE,
                content=f"Context archived: {summary_text[:200]}",
                metadata=metadata,
                conversation_id=None
            )

            event_id = self.memory_store.store_event(event)
            print(f"  Stored summary to episodic memory (event_id: {event_id})")
            return event_id is not None

        except Exception as e:
            print(f"  Error storing summary to episodic memory: {e}")
            return False

    def summarize_context(self, evidence: List[str]) -> bool:
        """
        Summarize and archive older conversation context to episodic memory.

        Triggered by AFFECT_MEMORY_PRESSURE signals when token usage is high.
        Compresses older conversation turns to free up working memory while
        preserving information in episodic memory for future retrieval.

        Args:
            evidence: Evidence about memory pressure

        Returns:
            True if action succeeded
        """
        print("\n[cognitive_actions] Executing: Summarize Context")
        print(f"  Evidence: {evidence}")

        try:
            recent = self._get_recent_conversation_turns(limit=10)
            older = self._get_older_conversation_turns(offset=10, limit=50)

            if not older:
                print("  No older context to summarize")
                self.log_action('summarize_context', 'No older context to archive')
                return True

            print(f"  Retrieved {len(recent)} recent turns, {len(older)} older turns")

            summary_text = self._create_summary_from_turns(older)

            summary_record = {
                'timestamp': datetime.now().isoformat(),
                'reason': 'memory_pressure',
                'evidence': evidence,
                'turns_compressed': len(older),
                'summary': summary_text
            }

            success = self._store_summary_to_episodic_memory(summary_record)

            if success:
                print(f"  Successfully archived {len(older)} turns, retained {len(recent)} recent")
                self.log_action(
                    'summarize_context',
                    f'Compressed {len(older)} turns, kept {len(recent)} recent'
                )
                return True
            else:
                print(f"  Partial completion: created summary but storage failed")
                self.log_action(
                    'summarize_context',
                    f'Summary created for {len(older)} turns but storage failed'
                )
                return False

        except Exception as e:
            print(f"  Error during context summarization: {e}")
            import traceback
            traceback.print_exc()
            self.log_action('summarize_context', f'Failed: {e}')
            return False

    def archive_completed_tasks(self, evidence: List[str]) -> bool:
        """
        Archive completed tasks to free up working memory.

        Args:
            evidence: Evidence about memory pressure

        Returns:
            True if action succeeded
        """
        print("\n[cognitive_actions] 📦 Executing: Archive Completed Tasks")
        print(f"  Evidence: {evidence}")

        # TODO: Implement actual task archiving
        print("  → Would identify completed tasks from todo history")
        print("  → Would move them to long-term task archive")
        print("  → Would compress their context for future retrieval")

        self.log_action('archive_tasks', 'Logged intent (implementation pending)')
        return True

    def analyze_failure_patterns(self, root_causes: List[str], actions: List[str]) -> bool:
        """
        Analyze patterns in task failures.

        Args:
            root_causes: Root causes identified
            actions: Suggested autonomous actions

        Returns:
            True if analysis succeeded
        """
        print("\n[cognitive_actions] 🔍 Executing: Analyze Failure Patterns")
        print(f"  Root causes: {root_causes}")
        print(f"  Suggested actions: {actions}")

        # TODO: Implement actual failure pattern analysis
        print("  → Would analyze recent error logs")
        print("  → Would identify common failure modes")
        print("  → Would suggest preventive measures")

        # Log patterns found
        for cause in root_causes:
            if 'task_failures' in cause:
                print(f"  ✓ Pattern detected: {cause}")

        self.log_action('analyze_failures', f'Analyzed {len(root_causes)} root causes')
        return True

    def request_context_expansion(self) -> bool:
        """
        Request context window expansion if possible.

        Returns:
            True if request succeeded
        """
        print("\n[cognitive_actions] 📝 Executing: Request Context Expansion")

        # Check if context expansion is possible
        # For now, just log the request
        print("  → Checking if context window can be expanded...")
        print("  → Would request additional context allocation")
        print("  → Would update context budgets if approved")

        self.log_action('request_context_expansion', 'Request logged')
        return True


# Global handler instance
handler = CognitiveActionHandler()


def handle_memory_pressure(msg: dict):
    """
    Handle AFFECT_MEMORY_PRESSURE signal.

    Memory pressure indicates high token usage or context pressure.
    Execute memory management actions.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[cognitive_actions] ⏸️  Emergency brake active, skipping action")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        print(f"\n[cognitive_actions] 💾 MEMORY_PRESSURE signal (intensity: {intensity:.2f})")

        autonomous_actions = facts.get('autonomous_actions', [])
        evidence = facts.get('evidence', [])

        # Execute memory management actions
        for action_text in autonomous_actions:
            action_lower = action_text.lower()

            if 'summarize' in action_lower and 'context' in action_lower:
                if handler.can_execute_action('summarize_context'):
                    handler.summarize_context(evidence)
                else:
                    print(f"  ⏭️  Skipping (cooldown): {action_text}")

            elif 'archive' in action_lower and 'task' in action_lower:
                if handler.can_execute_action('archive_tasks'):
                    handler.archive_completed_tasks(evidence)
                else:
                    print(f"  ⏭️  Skipping (cooldown): {action_text}")

    except Exception as e:
        print(f"[cognitive_actions] Error handling MEMORY_PRESSURE: {e}")
        import traceback
        traceback.print_exc()


def handle_context_overflow(msg: dict):
    """
    Handle AFFECT_CONTEXT_OVERFLOW signal.

    Context overflow indicates context window is near capacity.
    Request expansion or compress existing context.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[cognitive_actions] ⏸️  Emergency brake active, skipping action")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        print(f"\n[cognitive_actions] 📝 CONTEXT_OVERFLOW signal (intensity: {intensity:.2f})")

        # Try to expand context first, then compress if can't
        if handler.can_execute_action('request_context_expansion'):
            if intensity > 0.9:
                print("  → Intensity critical, requesting context expansion...")
                handler.request_context_expansion()
            else:
                print("  → Moderate pressure, compressing context...")
                handler.summarize_context(facts.get('evidence', []))

    except Exception as e:
        print(f"[cognitive_actions] Error handling CONTEXT_OVERFLOW: {e}")


def handle_task_failure_pattern(msg: dict):
    """
    Handle AFFECT_TASK_FAILURE_PATTERN signal.

    Task failure patterns indicate systematic issues.
    Analyze and suggest improvements.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[cognitive_actions] ⏸️  Emergency brake active, skipping action")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        print(f"\n[cognitive_actions] ❌ TASK_FAILURE_PATTERN signal (intensity: {intensity:.2f})")

        autonomous_actions = facts.get('autonomous_actions', [])
        root_causes = facts.get('root_causes', [])

        # Analyze failure patterns
        if handler.can_execute_action('analyze_failures'):
            handler.analyze_failure_patterns(root_causes, autonomous_actions)

    except Exception as e:
        print(f"[cognitive_actions] Error handling TASK_FAILURE_PATTERN: {e}")


def run_daemon():
    """
    Run cognitive actions subscriber daemon.

    Subscribes to cognitive-level affective signals and executes actions.
    """
    print("[cognitive_actions] Starting Cognitive Actions Subscriber")
    print("[cognitive_actions] Tier 3: Cognitive/memory operations")
    print(f"[cognitive_actions] Action log: {handler.action_log_path}")

    try:
        from kloros.orchestration.chem_bus_v2 import ChemSub

        # Subscribe to cognitive affective signals
        print("[cognitive_actions] Subscribing to AFFECT_MEMORY_PRESSURE...")
        memory_sub = ChemSub(
            topic="AFFECT_MEMORY_PRESSURE",
            on_json=handle_memory_pressure,
            zooid_name="cognitive_actions",
            niche="affective_actions"
        )

        print("[cognitive_actions] Subscribing to AFFECT_CONTEXT_OVERFLOW...")
        context_sub = ChemSub(
            topic="AFFECT_CONTEXT_OVERFLOW",
            on_json=handle_context_overflow,
            zooid_name="cognitive_actions",
            niche="affective_actions"
        )

        print("[cognitive_actions] Subscribing to AFFECT_TASK_FAILURE_PATTERN...")
        failure_sub = ChemSub(
            topic="AFFECT_TASK_FAILURE_PATTERN",
            on_json=handle_task_failure_pattern,
            zooid_name="cognitive_actions",
            niche="affective_actions"
        )

        print("[cognitive_actions] ✅ Cognitive Actions Subscriber ready")
        print("[cognitive_actions] Monitoring for cognitive affective signals...")
        print(f"[cognitive_actions] Action cooldown: {handler.action_cooldown}s")

        # Keep daemon running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[cognitive_actions] Daemon stopped by user")
    except Exception as e:
        print(f"[cognitive_actions] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_daemon()
