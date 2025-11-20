"""
User preference management for D-REAM alert system.
"""

import json
from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Any, Optional


class UserAlertPreferences:
    """Manage user preferences for alert routing and delivery."""

    def __init__(self):
        self.config_file = Path("/home/kloros/.kloros/alert_preferences.json")
        self.preferences = self._load_preferences()

    def _load_preferences(self) -> Dict[str, Any]:
        """Load preferences with sensible defaults."""
        defaults = {
            "urgency_thresholds": {
                "critical": 0.9,
                "high": 0.7,
                "medium": 0.5,
                "low": 0.3
            },
            "method_routing": {
                "critical": ["voice_interruption", "next_wake", "passive"],
                "high": ["next_wake", "passive"],
                "medium": ["next_wake", "passive"],
                "low": ["passive"]
            },
            "general_settings": {
                "enabled": True,
                "max_pending": 5,
                "quiet_hours": {"start": "22:00", "end": "08:00"},
                "presence_timeout_minutes": 5
            },
            "voice_settings": {
                "interruption_enabled": True,
                "quiet_hours_strict": True,
                "max_interruptions_per_day": 3,
                "presence_required": True
            },
            "scheduling": {
                "daily_checkin_enabled": True,
                "daily_checkin_time": "09:00",
                "weekly_summary_enabled": False,
                "weekly_summary_day": "sunday",
                "weekly_summary_time": "10:00",
                "batch_size_limit": 5
            },
            "external_notifications": {
                "email_enabled": False,
                "email_address": "",
                "web_dashboard_enabled": True,
                "web_dashboard_port": 5000
            },
            "last_updated": datetime.now().isoformat()
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    user_prefs = json.load(f)
                # Merge with defaults (user prefs override defaults)
                merged = self._deep_merge(defaults, user_prefs)
                return merged
            except Exception as e:
                print(f"[preferences] Error loading preferences: {e}, using defaults")
                return defaults
        else:
            # Create config file with defaults
            self._save_preferences(defaults)
            return defaults

    def _deep_merge(self, defaults: Dict, user_prefs: Dict) -> Dict:
        """Deep merge user preferences with defaults."""
        result = defaults.copy()

        for key, value in user_prefs.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def get_routing_for_urgency(self, urgency: str) -> List[str]:
        """Get preferred alert methods for urgency level."""
        return self.preferences["method_routing"].get(urgency, ["passive"])

    def is_alerts_enabled(self) -> bool:
        """Check if alert system is enabled."""
        return self.preferences["general_settings"].get("enabled", True)

    def is_voice_interruption_enabled(self) -> bool:
        """Check if voice interruption is enabled."""
        return self.preferences["voice_settings"].get("interruption_enabled", True)

    def is_quiet_hours(self, check_time: Optional[datetime] = None) -> bool:
        """Check if current time is in quiet hours."""
        if check_time is None:
            check_time = datetime.now()

        quiet_hours = self.preferences["general_settings"].get("quiet_hours", {})
        start_str = quiet_hours.get("start", "22:00")
        end_str = quiet_hours.get("end", "08:00")

        try:
            start_time = time.fromisoformat(start_str)
            end_time = time.fromisoformat(end_str)
            current_time = check_time.time()

            # Handle overnight quiet hours (e.g., 22:00 to 08:00)
            if start_time > end_time:
                return current_time >= start_time or current_time <= end_time
            else:
                return start_time <= current_time <= end_time

        except Exception:
            # Default quiet hours if parsing fails
            return 22 <= check_time.hour or check_time.hour <= 8

    def get_max_interruptions_per_day(self) -> int:
        """Get maximum allowed voice interruptions per day."""
        return self.preferences["voice_settings"].get("max_interruptions_per_day", 3)

    def get_max_pending_alerts(self) -> int:
        """Get maximum number of pending alerts."""
        return self.preferences["general_settings"].get("max_pending", 5)

    def is_daily_checkin_enabled(self) -> bool:
        """Check if daily check-ins are enabled."""
        return self.preferences["scheduling"].get("daily_checkin_enabled", True)

    def get_daily_checkin_time(self) -> time:
        """Get preferred daily check-in time."""
        time_str = self.preferences["scheduling"].get("daily_checkin_time", "09:00")
        try:
            return time.fromisoformat(time_str)
        except Exception:
            return time(9, 0)  # Default to 9 AM

    def get_batch_size_limit(self) -> int:
        """Get maximum alerts to present in one batch."""
        return self.preferences["scheduling"].get("batch_size_limit", 5)

    def is_email_enabled(self) -> bool:
        """Check if email notifications are enabled."""
        return self.preferences["external_notifications"].get("email_enabled", False)

    def get_email_address(self) -> Optional[str]:
        """Get configured email address."""
        email = self.preferences["external_notifications"].get("email_address", "")
        return email if email else None

    def is_web_dashboard_enabled(self) -> bool:
        """Check if web dashboard is enabled."""
        return self.preferences["external_notifications"].get("web_dashboard_enabled", True)

    def get_web_dashboard_port(self) -> int:
        """Get web dashboard port."""
        return self.preferences["external_notifications"].get("web_dashboard_port", 5000)

    def update_preference(self, key_path: str, value: Any) -> bool:
        """
        Update specific preference and save.

        Args:
            key_path: Dot-separated path to preference (e.g., "voice_settings.interruption_enabled")
            value: New value to set

        Returns:
            bool: True if update successful
        """
        try:
            keys = key_path.split('.')
            current = self.preferences

            # Navigate to the parent of the target key
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            # Set the value
            current[keys[-1]] = value

            # Update timestamp
            self.preferences["last_updated"] = datetime.now().isoformat()

            # Save to file
            self._save_preferences(self.preferences)
            return True

        except Exception as e:
            print(f"[preferences] Error updating preference {key_path}: {e}")
            return False

    def enable_email_notifications(self, email_address: str) -> bool:
        """Enable email notifications with given address."""
        success = True
        success &= self.update_preference("external_notifications.email_enabled", True)
        success &= self.update_preference("external_notifications.email_address", email_address)
        return success

    def disable_voice_interruptions(self) -> bool:
        """Disable voice interruptions (for quiet operation)."""
        return self.update_preference("voice_settings.interruption_enabled", False)

    def set_quiet_hours(self, start_time: str, end_time: str) -> bool:
        """Set quiet hours (format: HH:MM)."""
        try:
            # Validate time format
            time.fromisoformat(start_time)
            time.fromisoformat(end_time)

            success = True
            success &= self.update_preference("general_settings.quiet_hours.start", start_time)
            success &= self.update_preference("general_settings.quiet_hours.end", end_time)
            return success

        except Exception as e:
            print(f"[preferences] Invalid time format: {e}")
            return False

    def set_daily_checkin_time(self, checkin_time: str) -> bool:
        """Set daily check-in time (format: HH:MM)."""
        try:
            # Validate time format
            time.fromisoformat(checkin_time)
            return self.update_preference("scheduling.daily_checkin_time", checkin_time)

        except Exception as e:
            print(f"[preferences] Invalid time format: {e}")
            return False

    def get_preferences_summary(self) -> Dict[str, Any]:
        """Get summary of current preferences for display."""
        return {
            "alerts_enabled": self.is_alerts_enabled(),
            "voice_interruption": self.is_voice_interruption_enabled(),
            "quiet_hours": self.preferences["general_settings"]["quiet_hours"],
            "daily_checkin": {
                "enabled": self.is_daily_checkin_enabled(),
                "time": self.get_daily_checkin_time().strftime("%H:%M")
            },
            "email_notifications": {
                "enabled": self.is_email_enabled(),
                "address": self.get_email_address()
            },
            "limits": {
                "max_pending": self.get_max_pending_alerts(),
                "max_interruptions_per_day": self.get_max_interruptions_per_day(),
                "batch_size": self.get_batch_size_limit()
            }
        }

    def _save_preferences(self, preferences: Dict[str, Any]) -> None:
        """Save preferences to file."""
        try:
            # Ensure directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_file, 'w') as f:
                json.dump(preferences, f, indent=2, default=str)

            print(f"[preferences] Saved preferences to {self.config_file}")

        except Exception as e:
            print(f"[preferences] Error saving preferences: {e}")

    def reset_to_defaults(self) -> bool:
        """Reset all preferences to defaults."""
        try:
            if self.config_file.exists():
                self.config_file.unlink()

            self.preferences = self._load_preferences()
            return True

        except Exception as e:
            print(f"[preferences] Error resetting preferences: {e}")
            return False