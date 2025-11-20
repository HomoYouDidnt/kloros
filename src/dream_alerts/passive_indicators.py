"""
Passive indicator system for D-REAM alerts.
Provides status files and indicators that KLoROS can check during normal operation.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from .alert_methods import AlertMethod, AlertResult, ImprovementAlert


class PassiveIndicatorAlert(AlertMethod):
    """Passive indicator system - status files and introspection integration."""

    def __init__(self):
        self.status_dir = Path("/home/kloros/.kloros/alerts")
        self.status_file = self.status_dir / "pending_status.json"
        self.history_file = self.status_dir / "alert_history.json"
        self.max_history_entries = 100

        # Ensure status directory exists
        self.status_dir.mkdir(parents=True, exist_ok=True)

    def deliver_alert(self, alert: ImprovementAlert) -> AlertResult:
        """Create passive status indicators for the alert."""

        try:
            # Update status file with new alert
            self._update_status_file(alert)

            # Add to history
            self._add_to_history(alert)

            print(f"[passive] Updated status indicators for alert {alert.request_id}")

            return AlertResult(
                success=True,
                method="passive_indicators",
                delivery_time=datetime.now(),
                awaiting_response=False
            )

        except Exception as e:
            return AlertResult(
                success=False,
                method="passive_indicators",
                error=str(e),
                reason="Failed to update status files"
            )

    def can_deliver_now(self) -> bool:
        """Passive indicators can always be updated."""
        return True

    def get_method_name(self) -> str:
        """Return method name."""
        return "passive_indicators"

    def get_pending_status(self) -> Dict[str, Any]:
        """Get current pending alerts status."""
        if not self.status_file.exists():
            return {"pending_count": 0, "alerts": []}

        try:
            with open(self.status_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[passive] Error reading status file: {e}")
            return {"pending_count": 0, "alerts": []}

    def get_status_summary(self) -> str:
        """Get human-readable status summary."""
        status = self.get_pending_status()
        count = status.get("pending_count", 0)

        if count == 0:
            return "No pending improvements."
        elif count == 1:
            return "1 improvement awaiting approval."
        else:
            return f"{count} improvements awaiting approval."

    def get_introspection_data(self) -> Dict[str, Any]:
        """Get data for KLoROS introspection tools."""
        status = self.get_pending_status()
        history = self._get_recent_history(limit=10)

        return {
            "alert_system_active": True,
            "pending_improvements": status.get("pending_count", 0),
            "recent_alerts": len(history),
            "last_alert_time": history[0]["timestamp"] if history else None,
            "status_summary": self.get_status_summary(),
            "urgency_breakdown": self._get_urgency_breakdown(status.get("alerts", []))
        }

    def remove_alert(self, request_id: str) -> bool:
        """Remove alert from passive indicators (when approved/rejected)."""
        try:
            status = self.get_pending_status()
            alerts = status.get("alerts", [])

            # Remove the alert
            updated_alerts = [a for a in alerts if a.get("request_id") != request_id]

            if len(updated_alerts) != len(alerts):
                # Alert was found and removed
                self._save_status({
                    "pending_count": len(updated_alerts),
                    "alerts": updated_alerts,
                    "last_updated": datetime.now().isoformat()
                })

                print(f"[passive] Removed alert {request_id} from status indicators")
                return True
            else:
                print(f"[passive] Alert {request_id} not found in status indicators")
                return False

        except Exception as e:
            print(f"[passive] Error removing alert {request_id}: {e}")
            return False

    def clear_all_indicators(self) -> bool:
        """Clear all passive indicators (for testing/reset)."""
        try:
            self._save_status({
                "pending_count": 0,
                "alerts": [],
                "last_updated": datetime.now().isoformat()
            })

            print("[passive] Cleared all passive indicators")
            return True

        except Exception as e:
            print(f"[passive] Error clearing indicators: {e}")
            return False

    def _update_status_file(self, alert: ImprovementAlert) -> None:
        """Update the main status file with new alert."""
        current_status = self.get_pending_status()
        alerts = current_status.get("alerts", [])

        # Check if alert already exists
        existing_ids = [a.get("request_id") for a in alerts]
        if alert.request_id not in existing_ids:
            # Add new alert
            alert_dict = {
                "request_id": alert.request_id,
                "description": alert.description,
                "component": alert.component,
                "urgency": alert.urgency,
                "confidence": alert.confidence,
                "detected_at": alert.detected_at.isoformat(),
                "expected_benefit": alert.expected_benefit,
                "risk_level": alert.risk_level
            }

            alerts.append(alert_dict)

            # Save updated status
            self._save_status({
                "pending_count": len(alerts),
                "alerts": alerts,
                "last_updated": datetime.now().isoformat()
            })

    def _save_status(self, status_data: Dict[str, Any]) -> None:
        """Save status data to file."""
        with open(self.status_file, 'w') as f:
            json.dump(status_data, f, indent=2)

    def _add_to_history(self, alert: ImprovementAlert) -> None:
        """Add alert to historical log."""
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "alert_id": alert.request_id,
            "component": alert.component,
            "urgency": alert.urgency,
            "action": "created",
            "description": alert.description[:100] + "..." if len(alert.description) > 100 else alert.description
        }

        # Load existing history
        history = self._get_recent_history(limit=self.max_history_entries - 1)

        # Add new entry at beginning
        history.insert(0, history_entry)

        # Save updated history
        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=2)

    def _get_recent_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent alert history."""
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, 'r') as f:
                history = json.load(f)
                return history[:limit] if isinstance(history, list) else []
        except Exception as e:
            print(f"[passive] Error reading history: {e}")
            return []

    def _get_urgency_breakdown(self, alerts: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get count breakdown by urgency level."""
        breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for alert in alerts:
            urgency = alert.get("urgency", "low")
            if urgency in breakdown:
                breakdown[urgency] += 1

        return breakdown

    def get_urgency_support(self) -> List[str]:
        """Passive indicators support all urgency levels."""
        return ["critical", "high", "medium", "low"]


class KLoROSIntrospectionIntegration:
    """Integration with KLoROS introspection tools."""

    def __init__(self, passive_indicator: PassiveIndicatorAlert):
        self.passive_indicator = passive_indicator

    def add_to_status_report(self, existing_status: Dict[str, Any]) -> Dict[str, Any]:
        """Add alert information to existing KLoROS status reports."""
        alert_data = self.passive_indicator.get_introspection_data()

        # Add alert section to status
        existing_status["d_ream_alerts"] = alert_data

        return existing_status

    def get_alert_summary_for_speech(self) -> Optional[str]:
        """Get alert summary suitable for voice synthesis."""
        status = self.passive_indicator.get_pending_status()
        count = status.get("pending_count", 0)

        if count == 0:
            return None

        urgency_breakdown = self.passive_indicator._get_urgency_breakdown(status.get("alerts", []))

        # Build natural speech summary
        if count == 1:
            alert = status["alerts"][0]
            urgency = alert.get("urgency", "medium")
            return f"I have one {urgency} priority improvement proposal ready for review."
        else:
            critical = urgency_breakdown.get("critical", 0)
            high = urgency_breakdown.get("high", 0)

            if critical > 0:
                return f"I have {count} improvement proposals pending, including {critical} critical priority items."
            elif high > 0:
                return f"I have {count} improvement proposals pending, including {high} high priority items."
            else:
                return f"I have {count} improvement proposals pending for your review."