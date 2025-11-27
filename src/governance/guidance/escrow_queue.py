"""Action escrow queue for risky operations requiring approval."""
import json
import time
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EscrowedAction:
    """Represents an action awaiting approval."""

    id: str
    tool_name: str
    args: Dict[str, Any]
    risk_score: float
    risk_tags: List[str]
    reason: str
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"  # pending, approved, denied
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "args": self.args,
            "risk_score": self.risk_score,
            "risk_tags": self.risk_tags,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EscrowedAction':
        """Create from dictionary."""
        return cls(**data)


class ActionEscrow:
    """Manages escrowed actions requiring approval."""

    def __init__(self, queue_path: Optional[str] = None):
        """Initialize action escrow.

        Args:
            queue_path: Path to escrow queue file
        """
        self.queue_path = queue_path or os.path.expanduser("~/.kloros/escrow_queue.jsonl")
        os.makedirs(os.path.dirname(self.queue_path), exist_ok=True)

    def enqueue(
        self,
        tool_name: str,
        args: Dict[str, Any],
        risk_score: float,
        risk_tags: List[str],
        reason: str
    ) -> EscrowedAction:
        """Add action to escrow queue.

        Args:
            tool_name: Name of tool to execute
            args: Tool arguments
            risk_score: Risk assessment score
            risk_tags: Risk classification tags
            reason: Reason for escrow

        Returns:
            Escrowed action record
        """
        import uuid

        action = EscrowedAction(
            id=str(uuid.uuid4())[:8],
            tool_name=tool_name,
            args=args,
            risk_score=risk_score,
            risk_tags=risk_tags,
            reason=reason
        )

        # Append to queue
        with open(self.queue_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(action.to_dict()) + "\n")

        return action

    def get_pending(self, limit: int = 100) -> List[EscrowedAction]:
        """Get pending actions from queue.

        Args:
            limit: Maximum number of actions to return

        Returns:
            List of pending actions
        """
        if not os.path.exists(self.queue_path):
            return []

        pending = []
        with open(self.queue_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                action = EscrowedAction.from_dict(json.loads(line))
                if action.status == "pending":
                    pending.append(action)
                    if len(pending) >= limit:
                        break

        return pending

    def get_all(self, status: Optional[str] = None) -> List[EscrowedAction]:
        """Get all actions, optionally filtered by status.

        Args:
            status: Filter by status (pending, approved, denied)

        Returns:
            List of actions
        """
        if not os.path.exists(self.queue_path):
            return []

        actions = []
        with open(self.queue_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                action = EscrowedAction.from_dict(json.loads(line))
                if status is None or action.status == status:
                    actions.append(action)

        return actions

    def approve(self, action_id: str, reviewer: str = "system") -> bool:
        """Approve an escrowed action.

        Args:
            action_id: ID of action to approve
            reviewer: Who approved the action

        Returns:
            True if approved, False if not found
        """
        return self._update_status(action_id, "approved", reviewer)

    def deny(self, action_id: str, reviewer: str = "system") -> bool:
        """Deny an escrowed action.

        Args:
            action_id: ID of action to deny
            reviewer: Who denied the action

        Returns:
            True if denied, False if not found
        """
        return self._update_status(action_id, "denied", reviewer)

    def _update_status(self, action_id: str, status: str, reviewer: str) -> bool:
        """Update action status.

        Args:
            action_id: Action ID
            status: New status
            reviewer: Reviewer name

        Returns:
            True if updated
        """
        if not os.path.exists(self.queue_path):
            return False

        # Read all actions
        actions = []
        updated = False
        with open(self.queue_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                action = EscrowedAction.from_dict(json.loads(line))
                if action.id == action_id and action.status == "pending":
                    action.status = status
                    action.reviewed_by = reviewer
                    action.reviewed_at = time.time()
                    updated = True
                actions.append(action)

        if not updated:
            return False

        # Write back
        with open(self.queue_path, "w", encoding="utf-8") as f:
            for action in actions:
                f.write(json.dumps(action.to_dict()) + "\n")

        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get escrow queue statistics.

        Returns:
            Statistics dict
        """
        if not os.path.exists(self.queue_path):
            return {
                "total": 0,
                "pending": 0,
                "approved": 0,
                "denied": 0
            }

        stats = {"total": 0, "pending": 0, "approved": 0, "denied": 0}
        with open(self.queue_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                action = EscrowedAction.from_dict(json.loads(line))
                stats["total"] += 1
                stats[action.status] += 1

        return stats


# Global escrow instance
_escrow = ActionEscrow()


def enqueue_action(
    tool_name: str,
    args: Dict[str, Any],
    risk_score: float,
    risk_tags: List[str],
    reason: str
) -> EscrowedAction:
    """Enqueue action to escrow (convenience function).

    Args:
        tool_name: Tool name
        args: Tool arguments
        risk_score: Risk score
        risk_tags: Risk tags
        reason: Reason for escrow

    Returns:
        Escrowed action
    """
    return _escrow.enqueue(tool_name, args, risk_score, risk_tags, reason)


def get_pending_actions(limit: int = 100) -> List[EscrowedAction]:
    """Get pending actions (convenience function).

    Args:
        limit: Maximum actions to return

    Returns:
        List of pending actions
    """
    return _escrow.get_pending(limit)
