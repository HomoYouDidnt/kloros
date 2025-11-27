"""Planner component for AgentFlow."""
from typing import Dict, Any, List, Optional
import hashlib
import time


class SimplePlanner:
    """Simple policy-based planner with ACE hint integration and RA³ macro support."""

    def __init__(self, memory=None, config: Dict[str, Any] = None):
        """Initialize planner.

        Args:
            memory: Episodic memory adapter
            config: Configuration dict
        """
        self.memory = memory
        self.config = config or {}
        self.episode_buffer = []

        # RA³ macro support
        self.ra3_enabled = False
        self.macro_policy = None
        ra3_config = self.config.get("ra3", {})

        if ra3_config.get("enabled", False):
            try:
                from src.knowledge.ra3.library import get_default_library
                from src.knowledge.ra3.policy import MacroPolicy

                library = get_default_library()
                self.macro_policy = MacroPolicy(library, config=ra3_config)
                self.ra3_enabled = True
                print(f"[planner] RA³ enabled with {len(library.macros)} macros")
            except Exception as e:
                print(f"[planner] Failed to load RA³: {e}")
                self.ra3_enabled = False

    def decide(self, state: Dict[str, Any], task_spec: Dict[str, Any],
               hints: Optional[List[str]] = None) -> Dict[str, Any]:
        """Make a decision based on state, task, and hints.

        Args:
            state: Current state
            task_spec: Task specification
            hints: ACE bullets (hints) for this task

        Returns:
            Decision dict with tool, args, rationale
        """
        query = task_spec.get("query", "")
        hints = hints or []

        # Try RA³ macro selection first
        if self.ra3_enabled and self.macro_policy:
            macro_selection = self.macro_policy.select(state, task_spec, hints)

            if macro_selection.macro_id is not None:
                # Use macro
                print(f"[planner] Selected macro: {macro_selection.macro.name} (confidence: {macro_selection.confidence:.2f})")
                return {
                    "tool": "macro",
                    "args": {
                        "macro_id": macro_selection.macro_id,
                        "macro": macro_selection.macro,
                        "params": macro_selection.params
                    },
                    "rationale": f"Using macro '{macro_selection.macro.name}': {macro_selection.reason}",
                    "confidence": macro_selection.confidence,
                    "done": True,
                    "hints_used": hints,
                    "is_macro": True
                }

        # Fallback to primitive planning
        decision = {
            "tool": "rag_query",  # Default to RAG query
            "args": {"query": query},
            "rationale": f"Primitive planning with {len(hints)} hints",
            "confidence": 0.8,
            "done": True,
            "hints_used": hints,
            "is_macro": False
        }

        return decision

    def update_with_flow_grpo(self, episodes: List[Any]) -> str:
        """Update planner policy using Flow-GRPO.

        Args:
            episodes: List of EpisodeRecord objects

        Returns:
            Checkpoint ID
        """
        # Simplified implementation - in production, would do actual policy updates
        self.episode_buffer.extend(episodes)

        # Generate checkpoint ID
        timestamp = int(time.time())
        checkpoint_id = f"planner_ckpt_{timestamp}"

        print(f"[flow-grpo] Updated planner with {len(episodes)} episodes")
        print(f"[flow-grpo] Checkpoint: {checkpoint_id}")

        return checkpoint_id
