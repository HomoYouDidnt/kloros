"""Triage engine: event → playbook routing."""

import os
from typing import List, Optional
from .playbook_dsl import load_playbooks, find_matching_playbooks, Playbook
from .events import HealEvent


class TriageEngine:
    """Routes heal events to appropriate playbooks."""

    def __init__(self, playbook_path: str = None):
        """Initialize triage engine.

        Args:
            playbook_path: Path to playbooks YAML file
        """
        self.playbook_path = playbook_path or os.getenv(
            "KLR_HEAL_PLAYBOOKS",
            "self_heal_playbooks.yaml"
        )
        self.playbooks = load_playbooks(self.playbook_path)

    def triage(self, event: HealEvent) -> Optional[Playbook]:
        """Find best playbook for an event.

        Args:
            event: HealEvent to triage

        Returns:
            Best matching Playbook or None
        """
        matches = find_matching_playbooks(event, self.playbooks)

        if not matches:
            print(f"[triage] No playbook for {event.source}.{event.kind}")
            return None

        # Return highest ranked match
        best = matches[0]
        print(f"[triage] Matched {event.source}.{event.kind} → {best.name} (rank {best.rank})")
        return best

    def reload_playbooks(self):
        """Reload playbooks from disk."""
        self.playbooks = load_playbooks(self.playbook_path)
