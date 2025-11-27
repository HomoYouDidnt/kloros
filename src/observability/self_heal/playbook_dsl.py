"""Playbook DSL for declarative healing recipes."""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional


class Playbook:
    """Healing playbook with match conditions and actions."""

    def __init__(self, data: Dict[str, Any]):
        """Initialize playbook from dict.

        Args:
            data: Playbook definition dict
        """
        self.name = data.get("name", "unnamed")
        self.rank = data.get("rank", 50)
        self.match = data.get("match", {})
        self.steps = data.get("steps", [])
        self.canary_scope = data.get("canary_scope")
        self.validate = data.get("validate", {})

    def matches_event(self, event) -> bool:
        """Check if this playbook matches an event.

        Args:
            event: HealEvent to check

        Returns:
            True if playbook matches event
        """
        return event.matches(self.match)

    def __repr__(self) -> str:
        return f"<Playbook {self.name} rank={self.rank}>"


def load_playbooks(path: str) -> List[Playbook]:
    """Load playbooks from YAML file.

    Args:
        path: Path to playbooks YAML file

    Returns:
        List of Playbook objects, sorted by rank (descending)
    """
    playbook_file = Path(path)

    if not playbook_file.exists():
        print(f"[playbook_dsl] Playbook file not found: {path}")
        return []

    try:
        with open(playbook_file, 'r') as f:
            data = yaml.safe_load(f)

        playbooks = []
        for pb_data in data.get("playbooks", []):
            playbooks.append(Playbook(pb_data))

        # Sort by rank (highest first)
        playbooks.sort(key=lambda p: p.rank, reverse=True)

        print(f"[playbook_dsl] Loaded {len(playbooks)} playbooks from {path}")
        return playbooks

    except Exception as e:
        print(f"[playbook_dsl] Failed to load playbooks: {e}")
        return []


def find_matching_playbooks(event, playbooks: List[Playbook]) -> List[Playbook]:
    """Find all playbooks that match an event.

    Args:
        event: HealEvent to match
        playbooks: List of available playbooks

    Returns:
        List of matching playbooks, sorted by rank
    """
    matches = [pb for pb in playbooks if pb.matches_event(event)]
    return sorted(matches, key=lambda p: p.rank, reverse=True)
