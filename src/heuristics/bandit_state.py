"""
Bandit state persistence for PHASE adaptive controller.

Tracks UCB1 statistics across runs to enable exploration/exploitation balance
with memory, preventing cold-start bias on every controller tick.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class GroupStats:
    """Persistent statistics for a test group."""
    name: str
    trials: int = 0
    total_yield: float = 0.0
    total_cost: float = 0.0
    wins: int = 0  # Times this group had highest UCB score
    last_selected_ts: str = ""  # ISO timestamp


class BanditState:
    """Persistent bandit state with cold-start priors."""

    def __init__(self, state_path: Path = Path("/home/kloros/out/heuristics/bandit_state.json")):
        self.state_path = state_path
        self.groups: Dict[str, GroupStats] = {}
        self.total_selections = 0
        self.exploration_rate = 0.10  # ε-greedy floor

        # Cold-start priors (prevents over-exploit on first run)
        self.prior_mean = 0.5
        self.prior_n = 1

        self.load()

    def load(self) -> None:
        """Load bandit state from disk."""
        if not self.state_path.exists():
            logger.info("No bandit state found, using cold-start priors")
            return

        try:
            with open(self.state_path) as f:
                data = json.load(f)

            self.total_selections = data.get('total_selections', 0)
            self.exploration_rate = data.get('exploration_rate', 0.10)

            for group_data in data.get('groups', []):
                name = group_data['name']
                self.groups[name] = GroupStats(
                    name=name,
                    trials=group_data.get('trials', 0),
                    total_yield=group_data.get('total_yield', 0.0),
                    total_cost=group_data.get('total_cost', 0.0),
                    wins=group_data.get('wins', 0),
                    last_selected_ts=group_data.get('last_selected_ts', '')
                )

            logger.info(f"Loaded bandit state: {len(self.groups)} groups, {self.total_selections} total selections")
        except Exception as e:
            logger.warning(f"Failed to load bandit state: {e}")

    def save(self) -> None:
        """Atomically save bandit state to disk."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'total_selections': self.total_selections,
                'exploration_rate': self.exploration_rate,
                'groups': [asdict(g) for g in self.groups.values()]
            }

            # Atomic write
            temp_path = self.state_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)

            temp_path.replace(self.state_path)
            logger.info(f"Saved bandit state: {len(self.groups)} groups")
        except Exception as e:
            logger.error(f"Failed to save bandit state: {e}")

    def get_or_create(self, name: str) -> GroupStats:
        """Get existing group stats or create with cold-start prior."""
        if name not in self.groups:
            self.groups[name] = GroupStats(
                name=name,
                trials=self.prior_n,
                total_yield=self.prior_mean * self.prior_n,
                total_cost=self.prior_mean * self.prior_n,
                wins=0,
                last_selected_ts=""
            )
        return self.groups[name]

    def update(self, name: str, yield_score: float, cost_score: float, timestamp: str) -> None:
        """Update group statistics after a run."""
        group = self.get_or_create(name)
        group.trials += 1
        group.total_yield += yield_score
        group.total_cost += cost_score
        group.last_selected_ts = timestamp

        self.total_selections += 1

    def record_win(self, name: str) -> None:
        """Record that this group was selected (had highest UCB score)."""
        group = self.get_or_create(name)
        group.wins += 1

    def should_anneal_exploration(self) -> bool:
        """Check if we have enough data to reduce exploration rate."""
        # Anneal after 100 selections and stable performance
        return self.total_selections >= 100

    def get_exploration_rate(self) -> float:
        """Get current exploration rate (ε for ε-greedy)."""
        if self.should_anneal_exploration():
            # Gradually anneal toward 0.03
            target = 0.03
            rate = max(target, self.exploration_rate - 0.01)
            if rate != self.exploration_rate:
                logger.info(f"Annealing exploration: {self.exploration_rate:.3f} → {rate:.3f}")
                self.exploration_rate = rate
        return self.exploration_rate
