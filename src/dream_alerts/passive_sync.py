"""
Passive Alert Synchronization
Syncs alerts from passive indicator file into KLoROS next-wake queue.
"""

from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class PassiveAlertSync:
    """Synchronizes passive indicator alerts into next-wake queue."""
    
    def __init__(self, passive_method, next_wake_method, alert_manager=None):
        """
        Initialize sync system.

        Args:
            passive_method: PassiveIndicatorAlert instance
            next_wake_method: NextWakeIntegrationAlert instance
            alert_manager: DreamAlertManager instance (for main queue sync)
        """
        self.passive = passive_method
        self.next_wake = next_wake_method
        self.alert_manager = alert_manager
        self.last_sync_time = None
        self.synced_alert_ids = set()
    
    def sync_pending_alerts(self) -> int:
        """
        Sync alerts from passive indicator into next-wake queue.
        
        Returns:
            Number of alerts synced
        """
        if not self.passive or not self.next_wake:
            return 0
        
        try:
            # Get pending alerts from passive indicator
            status = self.passive.get_pending_status()
            pending_alerts = status.get('alerts', [])
            
            if not pending_alerts:
                return 0
            
            synced_count = 0
            
            for alert_dict in pending_alerts:
                alert_id = alert_dict.get('request_id')
                
                # Skip if already synced
                if alert_id in self.synced_alert_ids:
                    continue
                
                # Check if next-wake queue has room
                if not self.next_wake.can_deliver_now():
                    logger.warning(f"[passive_sync] Next-wake queue full, skipping {alert_id}")
                    continue
                
                # Reconstruct ImprovementAlert
                from dream_alerts.alert_methods import ImprovementAlert
                from datetime import datetime
                
                alert = ImprovementAlert(
                    request_id=alert_id,
                    description=alert_dict.get('description', ''),
                    component=alert_dict.get('component', 'system'),
                    urgency=alert_dict.get('urgency', 'medium'),
                    confidence=alert_dict.get('confidence', 0.5),
                    detected_at=datetime.fromisoformat(alert_dict.get('detected_at', datetime.now().isoformat())),
                    expected_benefit=alert_dict.get('expected_benefit', ''),
                    risk_level=alert_dict.get('risk_level', 'medium')
                )
                
                # Add to BOTH next-wake queue AND main alert queue
                # This ensures approval commands can find the alert!
                result = self.next_wake.deliver_alert(alert)

                if result.success:
                    # ALSO add to main alert manager queue for approval/rejection
                    if self.alert_manager:
                        self.alert_manager.alert_queue.add_alert(alert)
                        logger.info(f"[passive_sync] Added {alert_id} to main alert queue for approval")

                    synced_count += 1
                    self.synced_alert_ids.add(alert_id)
                    logger.info(f"[passive_sync] Synced alert {alert_id} to next-wake queue")
                else:
                    logger.warning(f"[passive_sync] Failed to sync alert {alert_id}")
            
            return synced_count
            
        except Exception as e:
            logger.error(f"[passive_sync] Error syncing alerts: {e}")
            return 0
    
    def clear_synced_alerts(self, presented_ids: List[str]) -> None:
        """
        Clear alerts that have been presented to user.
        
        Args:
            presented_ids: List of alert IDs that were presented
        """
        for alert_id in presented_ids:
            self.synced_alert_ids.discard(alert_id)
            # Remove from passive indicator
            if self.passive:
                self.passive.remove_alert(alert_id)
                logger.info(f"[passive_sync] Removed presented alert {alert_id} from passive queue")
