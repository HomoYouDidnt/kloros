"""
Next-wake integration alert method for D-REAM system.
Queues improvements for presentation during next natural wake word interaction.
"""

from datetime import datetime
from typing import List, Optional
from .alert_methods import AlertMethod, AlertResult, ImprovementAlert


class NextWakeIntegrationAlert(AlertMethod):
    """Queue improvements for next natural wake word interaction."""

    def __init__(self, kloros_instance=None):
        self.kloros = kloros_instance
        self.pending_queue: List[ImprovementAlert] = []
        self.max_queue_size = 50  # Increased from 3 to handle autonomous D-REAM optimization cycles
        self.last_presentation = None

    def deliver_alert(self, alert: ImprovementAlert) -> AlertResult:
        """Queue alert for next wake interaction."""

        # Deduplicate: skip if similar alert already queued
        if self._is_duplicate(alert):
            return AlertResult(
                success=True,
                method="next_wake_integration",
                delivery_time=datetime.now(),
                awaiting_response=True,
                reason="Duplicate alert already queued"
            )

        # Check if queue is full
        if len(self.pending_queue) >= self.max_queue_size:
            # Make room by removing least important alert
            self._make_room_in_queue(alert)

        # Add to queue
        self.pending_queue.append(alert)

        print(f"[next_wake] Queued alert {alert.request_id} for next wake interaction")
        print(f"[next_wake] Queue size: {len(self.pending_queue)}/{self.max_queue_size}")

        return AlertResult(
            success=True,
            method="next_wake_integration",
            delivery_time=datetime.now(),
            awaiting_response=True
        )

    def can_deliver_now(self) -> bool:
        """Next-wake can always queue alerts (unless queue is full)."""
        return len(self.pending_queue) < self.max_queue_size

    def get_pending_for_presentation(self) -> List[ImprovementAlert]:
        """Get alerts ready for next-wake presentation."""
        return self.pending_queue.copy()

    def mark_presented(self, alert_ids: List[str]) -> None:
        """Mark alerts as presented to user."""
        self.pending_queue = [a for a in self.pending_queue if a.request_id not in alert_ids]
        self.last_presentation = datetime.now()

        print(f"[next_wake] Marked {len(alert_ids)} alerts as presented")
        print(f"[next_wake] Remaining in queue: {len(self.pending_queue)}")

    def format_next_wake_message(self, alerts: List[ImprovementAlert]) -> str:
        """Format message for presentation during next wake."""
        if not alerts:
            return ""

        if len(alerts) == 1:
            alert = alerts[0]
            return f"""Before we continue, I have 1 improvement proposal ready for your review.

            {alert.description}
            Expected benefit: {alert.expected_benefit}
            Risk level: {alert.risk_level}
            Confidence: {int(alert.confidence * 100)}%

            Say 'APPROVE' to accept, 'REJECT' to decline, or 'EXPLAIN' for more details."""

        else:
            # Multiple alerts
            high_priority = [a for a in alerts if a.urgency in ["critical", "high"]]

            message = f"Before we continue, I have {len(alerts)} improvement proposals ready."

            if high_priority:
                message += f" {len(high_priority)} are high priority."

            message += " Would you like to hear about them one by one, or should I list them all briefly?"

            return message

    def get_urgency_support(self) -> List[str]:
        """Next-wake supports all urgency levels except critical (which should interrupt)."""
        return ["high", "medium", "low"]

    def _make_room_in_queue(self, new_alert: ImprovementAlert) -> None:
        """Make room in queue for new alert by removing less important ones."""
        urgency_priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        new_priority = urgency_priority.get(new_alert.urgency, 1)

        # Remove oldest alert with lower priority
        for i, alert in enumerate(self.pending_queue):
            alert_priority = urgency_priority.get(alert.urgency, 1)
            if alert_priority < new_priority:
                removed_alert = self.pending_queue.pop(i)
                print(f"[next_wake] Removed lower priority alert {removed_alert.request_id} to make room")
                return

        # If no lower priority found, remove oldest
        if self.pending_queue:
            removed_alert = self.pending_queue.pop(0)
            print(f"[next_wake] Removed oldest alert {removed_alert.request_id} to make room")

    def get_queue_status(self) -> dict:
        """Get status of next-wake queue."""
        return {
            "pending_count": len(self.pending_queue),
            "max_size": self.max_queue_size,
            "last_presentation": self.last_presentation.isoformat() if self.last_presentation else None,
            "alerts": [alert.request_id for alert in self.pending_queue]
        }

    def _is_duplicate(self, new_alert: ImprovementAlert) -> bool:
        """Check if similar alert already exists in queue."""
        for existing in self.pending_queue:
            # Same component and similar description
            if existing.component == new_alert.component:
                # Simple similarity check: if descriptions share >70% words
                desc1_words = set(existing.description.lower().split())
                desc2_words = set(new_alert.description.lower().split())
                if desc1_words and desc2_words:
                    overlap = len(desc1_words & desc2_words) / len(desc1_words | desc2_words)
                    if overlap > 0.7:
                        return True
        return False