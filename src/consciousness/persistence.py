"""
Consciousness State Persistence

Saves and restores consciousness state across KLoROS restarts.
Includes cumulative fatigue tracking that builds up over time.
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .models import Affect


class ConsciousnessStatePersistence:
    """
    Persist consciousness state across restarts.

    Tracks:
    - Current affect (valence, arousal, etc.)
    - Cumulative fatigue (builds up, requires rest)
    - Last update timestamp
    - Session statistics
    """

    def __init__(self, state_file: Optional[Path] = None):
        """
        Initialize persistence manager.

        Args:
            state_file: Path to state file (default: ~/.kloros/consciousness_state.json)
        """
        self.state_file = state_file or Path.home() / ".kloros" / "consciousness_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Cumulative fatigue parameters
        self.fatigue_accumulation_rate = 0.01  # Per minute of active use
        self.fatigue_recovery_rate = 0.02  # Per minute of idle time
        self.fatigue_max = 1.0
        self.idle_threshold_minutes = 10  # Consider idle after 10min

    def save_state(self, affect: Affect, cumulative_fatigue: float) -> None:
        """
        Save current consciousness state.

        Args:
            affect: Current affect state
            cumulative_fatigue: Cumulative fatigue level (0-1)
        """
        try:
            state = {
                "timestamp": datetime.now().isoformat(),
                "affect": {
                    "valence": affect.valence,
                    "arousal": affect.arousal,
                    "dominance": affect.dominance,
                    "uncertainty": affect.uncertainty,
                    "fatigue": affect.fatigue,  # Instantaneous fatigue
                    "curiosity": affect.curiosity
                },
                "cumulative_fatigue": cumulative_fatigue,
                "session_start": datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            print(f"[consciousness] Failed to save state: {e}")

    def load_state(self) -> Optional[Dict[str, Any]]:
        """
        Load saved consciousness state.

        Returns:
            State dictionary or None if no state exists
        """
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file) as f:
                state = json.load(f)

            # Calculate recovery from idle time
            last_timestamp = datetime.fromisoformat(state['timestamp'])
            now = datetime.now()
            idle_minutes = (now - last_timestamp).total_seconds() / 60

            # Apply fatigue recovery if idle
            cumulative_fatigue = state['cumulative_fatigue']
            if idle_minutes > self.idle_threshold_minutes:
                recovery = (idle_minutes - self.idle_threshold_minutes) * self.fatigue_recovery_rate
                cumulative_fatigue = max(0.0, cumulative_fatigue - recovery)

                print(f"[consciousness] Recovered from {state['cumulative_fatigue']:.2f} "
                      f"to {cumulative_fatigue:.2f} fatigue after {idle_minutes:.1f}min idle")

            state['cumulative_fatigue'] = cumulative_fatigue
            state['idle_recovery_applied'] = idle_minutes > self.idle_threshold_minutes

            return state

        except Exception as e:
            print(f"[consciousness] Failed to load state: {e}")
            return None

    def update_cumulative_fatigue(self,
                                   current_cumulative: float,
                                   instantaneous_fatigue: float,
                                   delta_minutes: float,
                                   is_resting: bool = False) -> float:
        """
        Update cumulative fatigue based on current load.

        Args:
            current_cumulative: Current cumulative fatigue (0-1)
            instantaneous_fatigue: Current instantaneous fatigue from resource pressure
            delta_minutes: Time since last update (minutes)
            is_resting: True if in rest/reflection mode (introspection, idle reflection, planning)

        Returns:
            Updated cumulative fatigue

        Note:
            During rest periods, fatigue ONLY recovers, never accumulates.
            This allows KLoROS to think, introspect, and plan improvements without
            incurring fatigue cost.
        """
        # REST MODE: Introspection and reflection do not accumulate fatigue
        if is_resting:
            # Always recover during rest, regardless of instantaneous fatigue
            recovery = self.fatigue_recovery_rate * delta_minutes
            current_cumulative = max(0.0, current_cumulative - recovery)
            return current_cumulative

        # ACTIVE MODE: Fatigue accumulates when under load
        if instantaneous_fatigue > 0.3:  # Threshold for "under load"
            # Accumulation proportional to instantaneous fatigue
            accumulation = instantaneous_fatigue * self.fatigue_accumulation_rate * delta_minutes
            current_cumulative = min(self.fatigue_max, current_cumulative + accumulation)

        # Fatigue recovers during low-load periods
        elif instantaneous_fatigue < 0.1:
            recovery = self.fatigue_recovery_rate * delta_minutes
            current_cumulative = max(0.0, current_cumulative - recovery)

        return current_cumulative


class CumulativeFatigueTracker:
    """
    Track cumulative fatigue across KLoROS's lifetime.

    Unlike instantaneous fatigue (computed from current resource pressure),
    cumulative fatigue builds up over time and requires rest to recover.
    """

    def __init__(self, persistence: ConsciousnessStatePersistence):
        """
        Initialize fatigue tracker.

        Args:
            persistence: Persistence manager
        """
        self.persistence = persistence
        self.cumulative_fatigue = 0.0
        self.last_update_time = time.time()

        # Load previous state
        saved_state = persistence.load_state()
        if saved_state:
            self.cumulative_fatigue = saved_state['cumulative_fatigue']
            print(f"[consciousness] Loaded cumulative fatigue: {self.cumulative_fatigue:.2f}")
        else:
            print("[consciousness] No previous state - starting fresh")

    def update(self, instantaneous_fatigue: float, current_affect: Affect, is_resting: bool = False) -> float:
        """
        Update cumulative fatigue and persist state.

        Args:
            instantaneous_fatigue: Current fatigue from resource pressure
            current_affect: Current affect state
            is_resting: True if in rest/reflection mode (no fatigue accumulation)

        Returns:
            Updated cumulative fatigue
        """
        current_time = time.time()
        delta_seconds = current_time - self.last_update_time
        delta_minutes = delta_seconds / 60.0

        # Update cumulative fatigue
        self.cumulative_fatigue = self.persistence.update_cumulative_fatigue(
            self.cumulative_fatigue,
            instantaneous_fatigue,
            delta_minutes,
            is_resting=is_resting
        )

        # Persist state
        self.persistence.save_state(current_affect, self.cumulative_fatigue)

        self.last_update_time = current_time

        return self.cumulative_fatigue

    def get_combined_fatigue(self, instantaneous_fatigue: float) -> float:
        """
        Get combined fatigue (mix of instantaneous and cumulative).

        Args:
            instantaneous_fatigue: Current resource pressure fatigue

        Returns:
            Combined fatigue (weighted average)
        """
        # Weight: 60% cumulative, 40% instantaneous
        # This gives importance to long-term strain while staying responsive to current load
        return 0.6 * self.cumulative_fatigue + 0.4 * instantaneous_fatigue


def get_consciousness_persistence(state_file: Optional[Path] = None) -> ConsciousnessStatePersistence:
    """Get consciousness persistence manager."""
    return ConsciousnessStatePersistence(state_file)
