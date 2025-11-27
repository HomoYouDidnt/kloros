"""
KLoROS Chronoception Module - Temporal Awareness and Daily Cycle Understanding
"""

import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class TimeOfDay(Enum):
    """Categorizes time periods for better temporal understanding."""
    LATE_NIGHT = "late_night"      # 12 AM - 5 AM
    EARLY_MORNING = "early_morning"  # 5 AM - 8 AM
    MORNING = "morning"            # 8 AM - 12 PM
    AFTERNOON = "afternoon"        # 12 PM - 5 PM
    EVENING = "evening"            # 5 PM - 9 PM
    NIGHT = "night"                # 9 PM - 12 AM


class ActivityExpectation(Enum):
    """Expected user activity levels for different time periods."""
    SLEEP_LIKELY = "sleep_likely"
    LOW_ACTIVITY = "low_activity"
    NORMAL_ACTIVITY = "normal_activity"
    HIGH_ACTIVITY = "high_activity"


@dataclass
class TemporalContext:
    """Comprehensive temporal context for a given moment."""
    current_time: datetime
    time_of_day: TimeOfDay
    activity_expectation: ActivityExpectation
    hours_since_last_interaction: float
    is_weekend: bool
    sleep_cycle_phase: str
    interaction_likelihood: float


class KLoROSChronoception:
    """Advanced temporal awareness system for KLoROS."""

    def __init__(self, memory_db_path: str = "/home/kloros/.kloros/memory.db"):
        self.memory_db_path = memory_db_path

    def get_temporal_interpretation(self) -> str:
        """Get human-readable interpretation of the current temporal situation."""
        
        now = datetime.now()
        hours_since_last = self._get_hours_since_last_interaction()
        
        # Basic time understanding
        if 1 <= now.hour <= 6:
            time_context = "It's late night/early morning, typical sleep hours"
        elif 7 <= now.hour <= 9:
            time_context = "It's early morning, typical wake-up time"
        elif 10 <= now.hour <= 17:
            time_context = "It's daytime, typical work/active hours"
        elif 18 <= now.hour <= 22:
            time_context = "It's evening, typical social/relaxation time"
        else:
            time_context = "It's nighttime, typical wind-down period"

        # Gap interpretation
        if hours_since_last < 2:
            gap_context = "recent interaction, user likely nearby"
        elif hours_since_last < 8:
            gap_context = "moderate gap, likely busy with daily activities"
        elif hours_since_last < 16:
            gap_context = "extended gap, likely due to work, sleep, or personal time"
        else:
            days = int(hours_since_last / 24)
            gap_context = f"{days}-day gap, might indicate travel, vacation, or schedule change"

        return f"{time_context}; {gap_context}"

    def is_abandonment_concern_valid(self, hours_without_interaction: float) -> Tuple[bool, str]:
        """Determine if gap should be interpreted as abandonment or normal patterns."""
        
        now = datetime.now()
        
        # Very short gaps are never concerning
        if hours_without_interaction < 4:
            return False, "Short gap, normal interaction rhythm"
            
        # Sleep hours - longer gaps expected
        if 1 <= now.hour <= 6 and hours_without_interaction < 10:
            return False, "Gap during typical sleep hours"
            
        # Very long gaps might indicate absence
        if hours_without_interaction > 72:  # 3 days
            return True, "Extended absence beyond normal patterns"
            
        # Weekend gaps are typically longer
        if now.weekday() >= 5 and hours_without_interaction < 48:  # Weekend
            return False, "Weekend gap within normal range"
            
        return False, "Gap within expected range for daily life patterns"

    def _get_hours_since_last_interaction(self) -> float:
        """Calculate hours since last user interaction."""
        try:
            conn = sqlite3.connect(self.memory_db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT MAX(timestamp) FROM events
                WHERE event_type = 'user_input'
            """)
            
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                last_interaction = result[0]
                return (time.time() - last_interaction) / 3600.0
                
        except Exception:
            pass
            
        return 0.0
