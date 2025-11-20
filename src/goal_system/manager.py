"""
Goal Manager - Registry and Lifecycle Management

Provides centralized goal tracking with CRUD operations,
hierarchical goal management, and consciousness integration.
"""

import logging
from typing import Dict, List, Optional, Callable, Set
from pathlib import Path
import json
import time

from .models import Goal, GoalState, GoalProperties

logger = logging.getLogger(__name__)


class GoalManager:
    """
    Central registry for goal tracking and management.

    Responsibilities:
        - Goal CRUD operations
        - Hierarchical goal relationships (parent/subgoals)
        - Progress tracking and delta computation
        - Event emission for consciousness integration
        - Persistence to disk
    """

    def __init__(self, persistence_path: Optional[Path] = None):
        """
        Initialize goal manager.

        Args:
            persistence_path: Optional path for goal state persistence
        """
        self.goals: Dict[str, Goal] = {}
        self.persistence_path = persistence_path or Path("/home/kloros/.kloros/goals.json")

        # Event callbacks for consciousness integration
        self.event_callbacks: List[Callable[[str, Dict], None]] = []

        # Try to load persisted goals
        self._load_goals()

        logger.info(f"[goal_manager] Initialized with {len(self.goals)} goals")

    def register_event_callback(self, callback: Callable[[str, Dict], None]):
        """
        Register callback for goal events.

        Callbacks receive (event_type, metadata) and can trigger
        consciousness system updates.

        Args:
            callback: Function to call on goal events
        """
        self.event_callbacks.append(callback)

    def _emit_event(self, event_type: str, goal: Goal, metadata: Optional[Dict] = None):
        """
        Emit goal event to all registered callbacks.

        Args:
            event_type: Event type (goal_set, goal_progress, etc.)
            goal: Goal that triggered the event
            metadata: Additional event context
        """
        event_metadata = metadata or {}
        event_metadata['goal_id'] = goal.id
        event_metadata['goal_description'] = goal.description
        event_metadata['goal_state'] = goal.state.value
        event_metadata['goal_progress'] = goal.progress
        event_metadata['goal_pressure'] = goal.homeostatic_pressure

        for callback in self.event_callbacks:
            try:
                callback(event_type, event_metadata)
            except Exception as e:
                logger.error(f"[goal_manager] Event callback failed: {e}")

    def create_goal(
        self,
        goal_id: str,
        description: str,
        properties: Optional[GoalProperties] = None,
        parent_id: Optional[str] = None,
        auto_activate: bool = False
    ) -> Goal:
        """
        Create a new goal.

        Args:
            goal_id: Unique identifier
            description: Human-readable description
            properties: Goal properties (alignment, novelty, etc.)
            parent_id: Optional parent goal ID for hierarchy
            auto_activate: Immediately activate goal

        Returns:
            Created goal

        Raises:
            ValueError: If goal_id already exists
        """
        if goal_id in self.goals:
            raise ValueError(f"Goal {goal_id} already exists")

        goal = Goal(
            id=goal_id,
            description=description,
            properties=properties or GoalProperties(),
            parent_id=parent_id
        )

        self.goals[goal_id] = goal

        # Link to parent if specified
        if parent_id and parent_id in self.goals:
            self.goals[parent_id].add_subgoal(goal_id)

        # Emit event
        self._emit_event("goal_set", goal, {
            'auto_activate': auto_activate
        })

        if auto_activate:
            goal.activate()
            self._emit_event("goal_activated", goal)

        self._save_goals()

        logger.info(f"[goal_manager] Created goal: {goal_id} - {description}")
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get goal by ID."""
        return self.goals.get(goal_id)

    def update_progress(
        self,
        goal_id: str,
        new_progress: float,
        emit_events: bool = True
    ) -> Optional[Goal]:
        """
        Update goal progress.

        Args:
            goal_id: Goal to update
            new_progress: New progress value (0.0 to 1.0)
            emit_events: Emit progress/completion events

        Returns:
            Updated goal or None if not found
        """
        goal = self.goals.get(goal_id)
        if not goal:
            logger.warning(f"[goal_manager] Goal {goal_id} not found")
            return None

        old_progress = goal.progress
        old_state = goal.state

        goal.update_progress(new_progress)

        if emit_events:
            # Emit progress event
            self._emit_event("goal_progress", goal, {
                'old_progress': old_progress,
                'new_progress': goal.progress,
                'progress_delta': goal.progress_delta
            })

            # Emit completion event if just completed
            if goal.state == GoalState.COMPLETED and old_state != GoalState.COMPLETED:
                self._emit_event("goal_completed", goal)

        self._save_goals()
        return goal

    def block_goal(self, goal_id: str, reason: Optional[str] = None) -> Optional[Goal]:
        """Mark goal as blocked."""
        goal = self.goals.get(goal_id)
        if not goal:
            return None

        goal.block(reason)
        self._emit_event("goal_blocked", goal, {'reason': reason})
        self._save_goals()

        logger.info(f"[goal_manager] Goal {goal_id} blocked: {reason}")
        return goal

    def unblock_goal(self, goal_id: str) -> Optional[Goal]:
        """Unblock a blocked goal."""
        goal = self.goals.get(goal_id)
        if not goal or goal.state != GoalState.BLOCKED:
            return None

        goal.state = GoalState.ACTIVE
        self._emit_event("goal_unblocked", goal)
        self._save_goals()

        logger.info(f"[goal_manager] Goal {goal_id} unblocked")
        return goal

    def pause_goal(self, goal_id: str) -> Optional[Goal]:
        """Pause an active goal."""
        goal = self.goals.get(goal_id)
        if not goal:
            return None

        goal.pause()
        self._emit_event("goal_paused", goal)
        self._save_goals()
        return goal

    def resume_goal(self, goal_id: str) -> Optional[Goal]:
        """Resume a paused goal."""
        goal = self.goals.get(goal_id)
        if not goal:
            return None

        goal.resume()
        self._emit_event("goal_resumed", goal)
        self._save_goals()
        return goal

    def abandon_goal(self, goal_id: str, reason: Optional[str] = None) -> Optional[Goal]:
        """Abandon a goal."""
        goal = self.goals.get(goal_id)
        if not goal:
            return None

        goal.abandon(reason)
        self._emit_event("goal_abandoned", goal, {'reason': reason})
        self._save_goals()

        logger.info(f"[goal_manager] Goal {goal_id} abandoned: {reason}")
        return goal

    def fail_goal(self, goal_id: str, reason: Optional[str] = None) -> Optional[Goal]:
        """Mark goal as failed."""
        goal = self.goals.get(goal_id)
        if not goal:
            return None

        goal.fail(reason)
        self._emit_event("goal_failed", goal, {'reason': reason})
        self._save_goals()

        logger.info(f"[goal_manager] Goal {goal_id} failed: {reason}")
        return goal

    def delete_goal(self, goal_id: str, recursive: bool = False) -> bool:
        """
        Delete a goal.

        Args:
            goal_id: Goal to delete
            recursive: Also delete all subgoals

        Returns:
            True if deleted
        """
        goal = self.goals.get(goal_id)
        if not goal:
            return False

        # Handle subgoals
        if recursive and goal.subgoal_ids:
            for subgoal_id in list(goal.subgoal_ids):
                self.delete_goal(subgoal_id, recursive=True)

        # Remove from parent
        if goal.parent_id and goal.parent_id in self.goals:
            parent = self.goals[goal.parent_id]
            parent.remove_subgoal(goal_id)

        # Delete
        del self.goals[goal_id]
        self._save_goals()

        logger.info(f"[goal_manager] Deleted goal: {goal_id}")
        return True

    def get_active_goals(self) -> List[Goal]:
        """Get all active goals."""
        return [g for g in self.goals.values() if g.is_active]

    def get_completed_goals(self) -> List[Goal]:
        """Get all completed goals."""
        return [g for g in self.goals.values() if g.state == GoalState.COMPLETED]

    def get_blocked_goals(self) -> List[Goal]:
        """Get all blocked goals."""
        return [g for g in self.goals.values() if g.state == GoalState.BLOCKED]

    def get_top_level_goals(self) -> List[Goal]:
        """Get goals without parents."""
        return [g for g in self.goals.values() if g.parent_id is None]

    def get_subgoals(self, goal_id: str, recursive: bool = False) -> List[Goal]:
        """
        Get subgoals of a goal.

        Args:
            goal_id: Parent goal ID
            recursive: Include all descendants

        Returns:
            List of subgoals
        """
        goal = self.goals.get(goal_id)
        if not goal:
            return []

        subgoals = [self.goals[sid] for sid in goal.subgoal_ids if sid in self.goals]

        if recursive:
            for subgoal in list(subgoals):
                subgoals.extend(self.get_subgoals(subgoal.id, recursive=True))

        return subgoals

    def search_goals(
        self,
        query: Optional[str] = None,
        state: Optional[GoalState] = None,
        min_progress: Optional[float] = None,
        max_progress: Optional[float] = None,
        min_pressure: Optional[float] = None
    ) -> List[Goal]:
        """
        Search goals with filters.

        Args:
            query: Text search in description
            state: Filter by goal state
            min_progress: Minimum progress
            max_progress: Maximum progress
            min_pressure: Minimum homeostatic pressure

        Returns:
            Matching goals
        """
        results = list(self.goals.values())

        if query:
            query_lower = query.lower()
            results = [g for g in results if query_lower in g.description.lower()]

        if state:
            results = [g for g in results if g.state == state]

        if min_progress is not None:
            results = [g for g in results if g.progress >= min_progress]

        if max_progress is not None:
            results = [g for g in results if g.progress <= max_progress]

        if min_pressure is not None:
            results = [g for g in results if g.homeostatic_pressure >= min_pressure]

        return results

    def get_total_homeostatic_pressure(self) -> float:
        """
        Calculate total homeostatic pressure across all active goals.

        Returns:
            Combined pressure (0.0 to N where N = number of active goals)
        """
        active_goals = self.get_active_goals()
        return sum(g.homeostatic_pressure for g in active_goals)

    def get_goal_progress_deltas(self) -> Dict[str, float]:
        """
        Get progress deltas for all active goals.

        Returns:
            Dict of {goal_id: progress_delta}
        """
        return {
            g.id: g.progress_delta
            for g in self.get_active_goals()
        }

    def _save_goals(self):
        """Persist goals to disk."""
        if not self.persistence_path:
            return

        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'goals': {gid: g.to_dict() for gid, g in self.goals.items()},
                'saved_at': time.time()
            }

            with open(self.persistence_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[goal_manager] Failed to save goals: {e}")

    def _load_goals(self):
        """Load goals from disk."""
        if not self.persistence_path or not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path, 'r') as f:
                data = json.load(f)

            # Reconstruct goals (simplified - full reconstruction would need more)
            for gid, gdata in data.get('goals', {}).items():
                goal = Goal(
                    id=gdata['id'],
                    description=gdata['description'],
                    state=GoalState(gdata['state']),
                    progress=gdata['progress']
                )
                # Restore other fields as needed
                self.goals[gid] = goal

            logger.info(f"[goal_manager] Loaded {len(self.goals)} goals from disk")
        except Exception as e:
            logger.error(f"[goal_manager] Failed to load goals: {e}")

    def get_status_summary(self) -> Dict:
        """Get summary of goal system status."""
        return {
            'total_goals': len(self.goals),
            'active_goals': len(self.get_active_goals()),
            'completed_goals': len(self.get_completed_goals()),
            'blocked_goals': len(self.get_blocked_goals()),
            'total_pressure': self.get_total_homeostatic_pressure(),
            'top_level_goals': len(self.get_top_level_goals())
        }
