"""Outcomes logging for learning loop."""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


class OutcomesLogger:
    """Logs healing outcomes for learning."""

    def __init__(self, log_path: Optional[str] = None):
        """Initialize outcomes logger.

        Args:
            log_path: Path to outcomes log file (JSONL format)
        """
        self.log_path = Path(
            log_path or os.getenv(
                "KLR_HEAL_OUTCOMES",
                "/tmp/kloros_heal_outcomes.jsonl"
            )
        )

        # Ensure log directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_outcome(
        self,
        event,
        playbook,
        success: bool,
        reason: Optional[str] = None
    ):
        """Log the outcome of a healing attempt.

        Args:
            event: HealEvent that was processed
            playbook: Playbook that was executed
            success: Whether healing succeeded
            reason: Optional reason for failure
        """
        outcome = {
            "timestamp": datetime.now().isoformat(),
            "event_id": event.id,
            "event_source": event.source,
            "event_kind": event.kind,
            "event_severity": event.severity,
            "playbook_name": playbook.name,
            "playbook_rank": playbook.rank,
            "success": success,
            "reason": reason,
        }

        try:
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(outcome) + '\n')
        except Exception as e:
            print(f"[outcomes] Failed to log outcome: {e}")

    def get_playbook_stats(self, playbook_name: str) -> dict:
        """Get success statistics for a playbook.

        Args:
            playbook_name: Name of playbook to analyze

        Returns:
            Dict with success_count, failure_count, success_rate
        """
        if not self.log_path.exists():
            return {"success_count": 0, "failure_count": 0, "success_rate": 0.0}

        success_count = 0
        failure_count = 0

        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    outcome = json.loads(line)
                    if outcome.get("playbook_name") == playbook_name:
                        if outcome.get("success"):
                            success_count += 1
                        else:
                            failure_count += 1
        except Exception as e:
            print(f"[outcomes] Failed to read outcomes: {e}")

        total = success_count + failure_count
        success_rate = success_count / total if total > 0 else 0.0

        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_rate
        }
