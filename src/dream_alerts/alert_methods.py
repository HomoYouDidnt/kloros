"""
Alert method base classes and data structures for D-REAM alert system.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
import time


@dataclass
class ImprovementAlert:
    """Data structure for improvement alerts."""

    request_id: str
    description: str
    component: str
    expected_benefit: str
    risk_level: str
    confidence: float
    urgency: str
    detected_at: datetime

    @classmethod
    def from_improvement(cls, improvement: Dict[str, Any]) -> 'ImprovementAlert':
        """Create alert from improvement dictionary."""

        # Calculate urgency based on confidence and component
        confidence = improvement.get('confidence', 0.5)
        if confidence >= 0.9:
            urgency = "critical"
        elif confidence >= 0.7:
            urgency = "high"
        elif confidence >= 0.5:
            urgency = "medium"
        else:
            urgency = "low"

        return cls(
            request_id=improvement.get('task_id', f"alert_{int(time.time())}"),
            description=improvement.get('description', 'System optimization'),
            component=improvement.get('component', 'system'),
            expected_benefit=improvement.get('expected_benefit', 'Performance improvement'),
            risk_level=improvement.get('risk_level', 'medium'),
            confidence=confidence,
            urgency=urgency,
            detected_at=datetime.now()
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'request_id': self.request_id,
            'description': self.description,
            'component': self.component,
            'expected_benefit': self.expected_benefit,
            'risk_level': self.risk_level,
            'confidence': self.confidence,
            'urgency': self.urgency,
            'detected_at': self.detected_at.isoformat()
        }


@dataclass
class AlertResult:
    """Result of alert delivery attempt."""

    success: bool
    method: str
    delivery_time: Optional[datetime] = None
    error: Optional[str] = None
    reason: Optional[str] = None
    awaiting_response: bool = False
    fallback_recommended: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'success': self.success,
            'method': self.method,
            'delivery_time': self.delivery_time.isoformat() if self.delivery_time else None,
            'error': self.error,
            'reason': self.reason,
            'awaiting_response': self.awaiting_response,
            'fallback_recommended': self.fallback_recommended
        }


class AlertMethod(ABC):
    """Abstract base class for all alert delivery methods."""

    @abstractmethod
    def deliver_alert(self, alert: ImprovementAlert) -> AlertResult:
        """
        Deliver alert using this method.

        Args:
            alert: The improvement alert to deliver

        Returns:
            AlertResult with delivery status and details
        """
        pass

    @abstractmethod
    def can_deliver_now(self) -> bool:
        """
        Check if this method is currently available for delivery.

        Returns:
            bool: True if method can deliver alerts now
        """
        pass

    def get_urgency_support(self) -> List[str]:
        """
        Return supported urgency levels for this method.

        Returns:
            List of supported urgency levels
        """
        return ["critical", "high", "medium", "low"]

    def get_method_name(self) -> str:
        """Return human-readable method name."""
        return self.__class__.__name__


class AlertQueue:
    """Queue for managing pending alerts with persistent storage."""

    def __init__(self, queue_file: str = "/home/kloros/.kloros/approval_queue.json"):
        self.queue_file = queue_file
        self.pending: List[ImprovementAlert] = []
        self.max_size = 10
        self._load_from_disk()

    def _load_from_disk(self):
        """Load pending alerts from disk."""
        try:
            import os
            if os.path.exists(self.queue_file):
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                    for item in data:
                        # Reconstruct ImprovementAlert from dict
                        alert = ImprovementAlert(
                            request_id=item['request_id'],
                            description=item['description'],
                            component=item['component'],
                            expected_benefit=item['expected_benefit'],
                            risk_level=item['risk_level'],
                            confidence=item['confidence'],
                            urgency=item['urgency'],
                            detected_at=datetime.fromisoformat(item['detected_at'])
                        )
                        self.pending.append(alert)
        except Exception as e:
            print(f"[alert_queue] Failed to load from disk: {e}")

    def _save_to_disk(self):
        """Save pending alerts to disk."""
        try:
            import os
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            with open(self.queue_file, 'w') as f:
                data = [alert.to_dict() for alert in self.pending]
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[alert_queue] Failed to save to disk: {e}")

    def add_alert(self, alert: ImprovementAlert) -> bool:
        """Add alert to queue and persist."""
        if len(self.pending) >= self.max_size:
            # Remove oldest low-priority alert to make room
            self._make_room_for_alert(alert)

        self.pending.append(alert)
        self._save_to_disk()
        return True

    def get_pending_by_urgency(self, urgency: str) -> List[ImprovementAlert]:
        """Get pending alerts of specific urgency."""
        return [alert for alert in self.pending if alert.urgency == urgency]

    def remove_alert(self, request_id: str) -> bool:
        """Remove alert from queue by ID and persist."""
        original_length = len(self.pending)
        self.pending = [alert for alert in self.pending if alert.request_id != request_id]
        removed = len(self.pending) < original_length
        if removed:
            self._save_to_disk()
        return removed

    def _make_room_for_alert(self, new_alert: ImprovementAlert) -> None:
        """Make room in queue for new alert by removing less important ones using VOI."""
        try:
            from src.reasoning_coordinator import get_reasoning_coordinator
            coordinator = get_reasoning_coordinator()

            # Calculate VOI for new alert
            new_voi = coordinator.calculate_voi({
                'action': f'Surface alert: {new_alert.request_id}',
                'urgency': new_alert.urgency,
                'risk_level': new_alert.risk_level,
                'confidence': new_alert.confidence,
                'expected_benefit': new_alert.expected_benefit
            })

            # Calculate VOI for all pending alerts
            alert_vois = []
            for alert in self.pending:
                voi = coordinator.calculate_voi({
                    'action': f'Surface alert: {alert.request_id}',
                    'urgency': alert.urgency,
                    'risk_level': alert.risk_level,
                    'confidence': alert.confidence,
                    'expected_benefit': alert.expected_benefit
                })
                alert_vois.append((alert, voi))

            # Remove alert with lowest VOI if it's lower than new alert's VOI
            if alert_vois:
                alert_vois.sort(key=lambda x: x[1])  # Sort by VOI (lowest first)
                lowest_alert, lowest_voi = alert_vois[0]
                if lowest_voi < new_voi:
                    self.pending.remove(lowest_alert)
                    print(f"[alerts] 🧠 Removed lower VOI alert {lowest_alert.request_id} (VOI: {lowest_voi:.3f} < {new_voi:.3f})")
                    return

        except Exception as e:
            print(f"[alerts] ⚠️ VOI calculation failed, using heuristic priority: {e}")
            # Fallback to heuristic
            urgency_priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            new_priority = urgency_priority.get(new_alert.urgency, 1)

            for i, alert in enumerate(self.pending):
                alert_priority = urgency_priority.get(alert.urgency, 1)
                if alert_priority < new_priority:
                    self.pending.pop(i)
                    return

        # If no lower priority found, remove oldest
        if self.pending:
            self.pending.pop(0)


class AlertHistory:
    """Track history of alert deliveries and responses."""

    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.max_history = 1000

    def record_delivery(self, alert: ImprovementAlert, result: AlertResult) -> None:
        """Record alert delivery attempt."""
        record = {
            'timestamp': datetime.now().isoformat(),
            'alert': alert.to_dict(),
            'result': result.to_dict(),
            'type': 'delivery'
        }

        self._add_record(record)

    def record_response(self, request_id: str, response: str, action: str) -> None:
        """Record user response to alert."""
        record = {
            'timestamp': datetime.now().isoformat(),
            'request_id': request_id,
            'response': response,
            'action': action,
            'type': 'response'
        }

        self._add_record(record)

    def record_deployment(self, request_id: str, deployment_result, success: bool) -> None:
        """Record deployment attempt for approved improvement."""
        record = {
            'timestamp': datetime.now().isoformat(),
            'request_id': request_id,
            'success': success,
            'deployment_data': {
                'changes_applied': deployment_result.changes_applied if hasattr(deployment_result, 'changes_applied') else [],
                'backup_path': deployment_result.backup_path if hasattr(deployment_result, 'backup_path') else None,
                'error_message': deployment_result.error_message if hasattr(deployment_result, 'error_message') else None,
                'rollback_performed': deployment_result.rollback_performed if hasattr(deployment_result, 'rollback_performed') else False
            },
            'type': 'deployment'
        }

        self._add_record(record)

    def get_recent_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent history records."""
        return self.history[-limit:] if limit < len(self.history) else self.history

    def get_delivery_stats(self) -> Dict[str, Any]:
        """Calculate delivery statistics."""
        deliveries = [r for r in self.history if r.get('type') == 'delivery']

        if not deliveries:
            return {"total": 0, "success_rate": 0.0}

        successful = sum(1 for d in deliveries if d.get('result', {}).get('success', False))

        return {
            "total": len(deliveries),
            "successful": successful,
            "success_rate": successful / len(deliveries),
            "by_method": self._calculate_method_stats(deliveries)
        }

    def get_deployment_stats(self) -> Dict[str, Any]:
        """Calculate deployment statistics."""
        deployments = [r for r in self.history if r.get('type') == 'deployment']

        if not deployments:
            return {"total": 0, "success_rate": 0.0}

        successful = sum(1 for d in deployments if d.get('success', False))

        return {
            "total": len(deployments),
            "successful": successful,
            "success_rate": successful / len(deployments),
            "rollbacks": sum(1 for d in deployments if d.get('deployment_data', {}).get('rollback_performed', False))
        }

    def _add_record(self, record: Dict[str, Any]) -> None:
        """Add record to history with size limiting."""
        self.history.append(record)

        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def _calculate_method_stats(self, deliveries: List[Dict]) -> Dict[str, Dict]:
        """Calculate statistics by delivery method."""
        stats = {}

        for delivery in deliveries:
            method = delivery.get('result', {}).get('method', 'unknown')
            success = delivery.get('result', {}).get('success', False)

            if method not in stats:
                stats[method] = {"total": 0, "successful": 0}

            stats[method]["total"] += 1
            if success:
                stats[method]["successful"] += 1

        # Calculate success rates
        for method_stats in stats.values():
            if method_stats["total"] > 0:
                method_stats["success_rate"] = method_stats["successful"] / method_stats["total"]
            else:
                method_stats["success_rate"] = 0.0

        return stats