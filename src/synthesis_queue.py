"""
Tool Synthesis Queue - User Notification System

Manages autonomous tool synthesis proposals generated during reflection.
Level 2 autonomy: Detect opportunities, queue for user approval.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class SynthesisQueue:
    """Manages queued tool synthesis proposals."""

    def __init__(self, queue_file: str = "/home/kloros/.kloros/synthesis_queue.jsonl"):
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)

    def add_proposal(self, tool_name: str, description: str, requirements: str,
                    source: str = "reflection", confidence: float = 0.0,
                    insight_id: str = None) -> str:
        """
        Add a tool synthesis proposal to the queue.

        Args:
            tool_name: Proposed tool name
            description: What the tool should do
            requirements: Detailed requirements
            source: Where this proposal came from (reflection, user, etc.)
            confidence: Confidence score (0.0-1.0)
            insight_id: Optional ID linking to reflection insight

        Returns:
            Proposal ID
        """
        proposal_id = f"proposal_{int(time.time() * 1000)}"

        proposal = {
            "id": proposal_id,
            "tool_name": tool_name,
            "description": description,
            "requirements": requirements,
            "source": source,
            "confidence": confidence,
            "insight_id": insight_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "reviewed_at": None,
            "synthesized_at": None
        }

        # Append to JSONL queue
        with open(self.queue_file, 'a') as f:
            f.write(json.dumps(proposal) + "\n")

        print(f"[synthesis_queue] ✅ Added proposal: {tool_name} (confidence: {confidence:.2f})")
        return proposal_id

    def get_pending_proposals(self) -> List[Dict]:
        """Get all pending proposals waiting for user review."""
        if not self.queue_file.exists():
            return []

        pending = []
        with open(self.queue_file, 'r') as f:
            for line in f:
                if line.strip():
                    proposal = json.loads(line)
                    if proposal.get('status') == 'pending':
                        pending.append(proposal)

        return pending

    def get_proposal_by_id(self, proposal_id: str) -> Optional[Dict]:
        """Get a specific proposal by ID."""
        if not self.queue_file.exists():
            return None

        with open(self.queue_file, 'r') as f:
            for line in f:
                if line.strip():
                    proposal = json.loads(line)
                    if proposal.get('id') == proposal_id:
                        return proposal
        return None

    def update_proposal_status(self, proposal_id: str, status: str) -> bool:
        """
        Update proposal status.

        Args:
            proposal_id: Proposal to update
            status: New status (approved, rejected, synthesized, failed)

        Returns:
            True if updated successfully
        """
        if not self.queue_file.exists():
            return False

        # Read all proposals
        proposals = []
        with open(self.queue_file, 'r') as f:
            for line in f:
                if line.strip():
                    proposals.append(json.loads(line))

        # Update target proposal
        found = False
        for proposal in proposals:
            if proposal['id'] == proposal_id:
                proposal['status'] = status
                proposal['reviewed_at'] = datetime.utcnow().isoformat() + "Z"
                found = True
                break

        if not found:
            return False

        # Rewrite file
        with open(self.queue_file, 'w') as f:
            for proposal in proposals:
                f.write(json.dumps(proposal) + "\n")

        return True

    def clear_old_proposals(self, days: int = 30) -> int:
        """Remove old proposals older than N days."""
        if not self.queue_file.exists():
            return 0

        cutoff = time.time() - (days * 24 * 3600)
        kept = []
        removed = 0

        with open(self.queue_file, 'r') as f:
            for line in f:
                if line.strip():
                    proposal = json.loads(line)
                    created_ts = datetime.fromisoformat(
                        proposal['created_at'].rstrip('Z')
                    ).timestamp()

                    if created_ts > cutoff:
                        kept.append(proposal)
                    else:
                        removed += 1

        # Rewrite with kept proposals
        with open(self.queue_file, 'w') as f:
            for proposal in kept:
                f.write(json.dumps(proposal) + "\n")

        if removed > 0:
            print(f"[synthesis_queue] Cleaned {removed} old proposals (>{days} days)")

        return removed

    def get_queue_summary(self) -> Dict:
        """Get summary statistics about the queue."""
        if not self.queue_file.exists():
            return {
                "total": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "synthesized": 0
            }

        stats = {
            "total": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "synthesized": 0,
            "failed": 0
        }

        with open(self.queue_file, 'r') as f:
            for line in f:
                if line.strip():
                    proposal = json.loads(line)
                    stats['total'] += 1
                    status = proposal.get('status', 'pending')
                    if status in stats:
                        stats[status] += 1

        return stats
