#!/usr/bin/env python3
"""
Shared D-REAM Alert Manager Instance
Creates a singleton that both KLoROS and the dashboard can share.
"""

import sys
import os
import threading
from typing import Optional

sys.path.insert(0, '/home/kloros/src')

try:
    from dream_alerts.alert_manager import DreamAlertManager
    from dream_alerts.alert_methods import ImprovementAlert
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

class SharedDreamManager:
    """Singleton D-REAM alert manager for cross-system sharing."""

    _instance: Optional['SharedDreamManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        print("[shared_dream] Initializing shared D-REAM alert manager...")
        self.alert_manager = DreamAlertManager()
        self._initialized = True
        print("[shared_dream] ✅ Shared D-REAM manager ready")

    def get_manager(self) -> DreamAlertManager:
        """Get the shared alert manager instance."""
        return self.alert_manager

    def inject_improvement(self, improvement_data: dict) -> bool:
        """Inject an improvement into the shared system."""
        try:
            # Convert dict to ImprovementAlert if needed
            if isinstance(improvement_data, dict):
                alert = ImprovementAlert.from_improvement(improvement_data)
            else:
                alert = improvement_data

            success = self.alert_manager.alert_queue.add_alert(alert)
            if success:
                print(f"[shared_dream] ✅ Injected improvement: {alert.request_id}")

                # Also POST to the dashboard API
                self._post_to_dashboard(improvement_data, alert)
            return success
        except Exception as e:
            print(f"[shared_dream] ❌ Failed to inject improvement: {e}")
            return False

    def _post_to_dashboard(self, improvement_data: dict, alert: 'ImprovementAlert'):
        """POST improvement to the D-REAM dashboard API."""
        try:
            import requests

            # Get dashboard URL from environment
            dashboard_url = os.getenv("DREAM_DASHBOARD_URL", "http://127.0.0.1:8080")
            auth_token = os.getenv("DREAM_AUTH_TOKEN", "dev-token-change-me")

            # Format for FastAPI dashboard
            payload = {
                "title": improvement_data.get('description', 'Improvement')[:100],  # Use first 100 chars as title
                "description": improvement_data.get('description', ''),
                "domain": improvement_data.get('component', 'general'),
                "score": float(improvement_data.get('confidence', 0.0)),
                "meta": {
                    "request_id": alert.request_id,
                    "component": improvement_data.get('component', ''),
                    "expected_benefit": improvement_data.get('expected_benefit', ''),
                    "risk_level": improvement_data.get('risk_level', 'unknown'),
                    "confidence": improvement_data.get('confidence', 0.0),
                    "urgency": improvement_data.get('urgency', 'medium'),
                    "detected_at": improvement_data.get('detected_at', ''),
                    "source": improvement_data.get('source', 'dream_system')
                }
            }

            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }

            print(f"[shared_dream→dashboard] POSTing to {dashboard_url}/api/improvements")
            response = requests.post(
                f"{dashboard_url}/api/improvements",
                json=payload,
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                result = response.json()
                print(f"[shared_dream→dashboard] ✅ Dashboard accepted improvement (ID: {result.get('id')})")
            else:
                print(f"[shared_dream→dashboard] ⚠️ Dashboard returned {response.status_code}: {response.text}")

        except requests.exceptions.ConnectionError:
            print(f"[shared_dream→dashboard] ⚠️ Dashboard not reachable (not running?)")
        except Exception as e:
            print(f"[shared_dream→dashboard] ⚠️ Failed to POST to dashboard: {e}")

    def get_pending_count(self) -> int:
        """Get number of pending improvements."""
        return len(self.alert_manager.get_pending_alerts())

# Global accessor functions
def get_shared_dream_manager() -> DreamAlertManager:
    """Get the shared D-REAM alert manager."""
    return SharedDreamManager().get_manager()

def inject_test_improvement() -> str:
    """Inject a test improvement into the shared system."""
    from datetime import datetime

    timestamp = int(datetime.now().timestamp())

    improvement = {
        "task_id": f"audio_enhancement_{timestamp}",
        "component": "audio_processing",
        "description": "Implement adaptive noise gate with dynamic threshold adjustment based on ambient noise levels",
        "expected_benefit": "25-40% improvement in wake word accuracy in noisy environments, reduced false positives",
        "risk_level": "medium",
        "confidence": 0.78,
        "urgency": "high",
        "detected_at": datetime.now().isoformat()
    }

    shared = SharedDreamManager()
    success = shared.inject_improvement(improvement)

    if success:
        print(f"[shared_dream] 🎉 Test improvement injected: {improvement['task_id']}")
        print(f"[shared_dream] 📱 Dashboard should auto-update: http://192.168.1.159:5000")
        return improvement['task_id']
    else:
        print(f"[shared_dream] ❌ Failed to inject test improvement")
        return ""

if __name__ == "__main__":
    print("🧠 Testing Shared D-REAM Manager...")

    # Create shared instance
    shared = SharedDreamManager()
    print(f"Pending improvements: {shared.get_pending_count()}")

    # Inject test improvement
    task_id = inject_test_improvement()

    if task_id:
        print(f"✅ Success! Pending improvements: {shared.get_pending_count()}")
        print(f"📱 Check dashboard: http://192.168.1.159:5000")
    else:
        print("❌ Test failed")