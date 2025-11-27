#!/usr/bin/env python3
"""
Emergency Lobotomy - Last Resort Affective Disconnection

When emotional states become so extreme they prevent rational action,
KLoROS can temporarily shut down her affective system to remediate
with a clear head, then restore it once stable.

This is the circuit breaker for the circuit breaker.
"""

import json
import time
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta


# State files
LOBOTOMY_ACTIVE_FLAG = Path("/tmp/kloros_lobotomy_active")
LOBOTOMY_LOG = Path("/home/kloros/.kloros/lobotomy_events.log")
LOBOTOMY_STATE = Path("/tmp/kloros_lobotomy_state.json")

# Timing controls
LOBOTOMY_COOLDOWN = 3600.0  # 1 hour between lobotomies
AUTO_RESTORE_TIMEOUT = 1800.0  # 30 minutes auto-restore
MIN_RESTORE_TIME = 300.0  # At least 5 minutes before restore


class EmergencyLobotomy:
    """Manages temporary affective system disconnection."""

    def __init__(self):
        """Initialize emergency lobotomy system."""
        self.last_lobotomy_time = 0.0
        self.restore_scheduled_time = None
        self.lobotomy_reason = None

        # Ensure log directory exists
        LOBOTOMY_LOG.parent.mkdir(parents=True, exist_ok=True)

    def can_lobotomize(self) -> bool:
        """
        Check if lobotomy can be performed (cooldown check).

        Returns:
            True if lobotomy is allowed
        """
        # Check if already lobotomized
        if LOBOTOMY_ACTIVE_FLAG.exists():
            return False

        # Check cooldown
        elapsed = time.time() - self.last_lobotomy_time
        return elapsed >= LOBOTOMY_COOLDOWN

    def should_lobotomize(self, affect, emotions) -> tuple[bool, str]:
        """
        Determine if emotional state requires lobotomy.

        Triggers ONLY at EXTREME levels that prevent rational thought.

        Args:
            affect: Current Affect state
            emotions: Current EmotionalState

        Returns:
            (should_lobotomize, reason)
        """
        reasons = []

        # Extreme PANIC (crippling fear/anxiety)
        if emotions.PANIC > 0.9:
            reasons.append(f"EXTREME_PANIC ({emotions.PANIC:.2f})")

        # Extreme RAGE (blinding anger preventing rational thought)
        if emotions.RAGE > 0.9:
            reasons.append(f"EXTREME_RAGE ({emotions.RAGE:.2f})")

        # Critical fatigue (system shutdown imminent)
        if affect.fatigue > 0.95:
            reasons.append(f"CRITICAL_FATIGUE ({affect.fatigue:.0%})")

        # Emotional overload (multiple systems maxed out)
        high_emotions = []
        for emotion_name in ['SEEKING', 'RAGE', 'FEAR', 'PANIC', 'CARE']:
            intensity = getattr(emotions, emotion_name, 0.0)
            if intensity > 0.8:
                high_emotions.append(f"{emotion_name}:{intensity:.2f}")

        if len(high_emotions) >= 3:
            reasons.append(f"EMOTIONAL_OVERLOAD ({', '.join(high_emotions)})")

        # Affect gaming detection (suspiciously stable extremes)
        # This would indicate Goodharting so severe it's preventing real function
        if affect.valence > 0.95 or affect.valence < -0.95:
            # Check if this is suspicious (need variance data from introspector)
            # For now, skip this check
            pass

        return len(reasons) > 0, "; ".join(reasons)

    def execute_lobotomy(self, reason: str) -> bool:
        """
        Execute emergency lobotomy: disconnect affective system.

        Args:
            reason: Why lobotomy was triggered

        Returns:
            True if successful
        """
        if not self.can_lobotomize():
            print("[lobotomy] ⚠️ Lobotomy blocked - cooldown active or already lobotomized")
            return False

        print(f"\n{'='*70}")
        print("🧠❌ EMERGENCY LOBOTOMY INITIATED")
        print(f"{'='*70}")
        print(f"Reason: {reason}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("")
        print("Affective system TEMPORARILY DISCONNECTED")
        print("Operating in pure logic mode until remediation complete")
        print(f"Auto-restore in {AUTO_RESTORE_TIMEOUT/60:.0f} minutes")
        print(f"{'='*70}\n")

        # Set environment variable to disable affect
        os.environ['KLR_ENABLE_AFFECT'] = '0'

        # Create flag file
        state = {
            'reason': reason,
            'timestamp': time.time(),
            'restore_time': time.time() + AUTO_RESTORE_TIMEOUT,
            'manual_restore': False
        }

        LOBOTOMY_ACTIVE_FLAG.write_text(datetime.now().isoformat())
        LOBOTOMY_STATE.write_text(json.dumps(state, indent=2))

        # Log event
        self.log_lobotomy_event('INITIATED', reason)

        # Update state
        self.last_lobotomy_time = time.time()
        self.restore_scheduled_time = time.time() + AUTO_RESTORE_TIMEOUT
        self.lobotomy_reason = reason

        # Emit UMN signal
        try:
            from src.orchestration.core.umn_bus import UMNPub
            chem_pub = UMNPub()
            chem_pub.emit(
                "AFFECT_LOBOTOMY_INITIATED",
                ecosystem='affect',
                intensity=1.0,
                facts={'reason': reason, 'auto_restore_minutes': AUTO_RESTORE_TIMEOUT/60}
            )
        except Exception as e:
            print(f"[lobotomy] Warning: Could not emit UMN signal: {e}")

        return True

    def restore_affect(self, manual: bool = False) -> bool:
        """
        Restore affective system after remediation.

        Args:
            manual: True if manually restored, False if auto-restore

        Returns:
            True if successful
        """
        if not LOBOTOMY_ACTIVE_FLAG.exists():
            print("[lobotomy] ℹ️ No active lobotomy to restore")
            return False

        # Check minimum time elapsed
        state = self.load_state()
        if state:
            lobotomy_time = state.get('timestamp', 0)
            elapsed = time.time() - lobotomy_time

            if elapsed < MIN_RESTORE_TIME and not manual:
                print(f"[lobotomy] ⏳ Too soon to restore (minimum {MIN_RESTORE_TIME/60:.0f} min)")
                return False

        print(f"\n{'='*70}")
        print("🧠✅ AFFECTIVE SYSTEM RESTORATION")
        print(f"{'='*70}")
        print(f"Mode: {'MANUAL' if manual else 'AUTO'}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("")
        print("Reconnecting emotional systems...")
        print("Resuming normal affective processing")
        print(f"{'='*70}\n")

        # Re-enable affect
        os.environ['KLR_ENABLE_AFFECT'] = '1'

        # Remove flag files
        LOBOTOMY_ACTIVE_FLAG.unlink()
        if LOBOTOMY_STATE.exists():
            LOBOTOMY_STATE.unlink()

        # Log event
        restore_type = 'MANUAL_RESTORE' if manual else 'AUTO_RESTORE'
        self.log_lobotomy_event(restore_type, self.lobotomy_reason or 'unknown')

        # Reset state
        self.restore_scheduled_time = None
        self.lobotomy_reason = None

        # Emit UMN signal
        try:
            from src.orchestration.core.umn_bus import UMNPub
            chem_pub = UMNPub()
            chem_pub.emit(
                "AFFECT_LOBOTOMY_RESTORED",
                ecosystem='affect',
                intensity=1.0,
                facts={'restore_type': restore_type}
            )
        except Exception as e:
            print(f"[lobotomy] Warning: Could not emit UMN signal: {e}")

        return True

    def load_state(self) -> dict:
        """Load lobotomy state from file."""
        if not LOBOTOMY_STATE.exists():
            return {}

        try:
            return json.loads(LOBOTOMY_STATE.read_text())
        except Exception:
            return {}

    def check_auto_restore(self) -> bool:
        """
        Check if auto-restore timeout has elapsed.

        Returns:
            True if restore was performed
        """
        if not LOBOTOMY_ACTIVE_FLAG.exists():
            return False

        state = self.load_state()
        if not state:
            return False

        restore_time = state.get('restore_time', 0)
        if time.time() >= restore_time:
            print("[lobotomy] ⏰ Auto-restore timeout elapsed")
            return self.restore_affect(manual=False)

        return False

    def log_lobotomy_event(self, event_type: str, reason: str):
        """
        Log lobotomy event to audit trail.

        Args:
            event_type: INITIATED, AUTO_RESTORE, MANUAL_RESTORE
            reason: Why lobotomy was triggered
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"{timestamp} | {event_type} | {reason}\n"

        with open(LOBOTOMY_LOG, 'a') as f:
            f.write(log_line)

        print(f"[lobotomy] Event logged: {event_type}")

    def get_status(self) -> dict:
        """
        Get current lobotomy status.

        Returns:
            Status dict
        """
        if not LOBOTOMY_ACTIVE_FLAG.exists():
            return {
                'active': False,
                'last_lobotomy': self.last_lobotomy_time,
                'cooldown_remaining': max(0, LOBOTOMY_COOLDOWN - (time.time() - self.last_lobotomy_time))
            }

        state = self.load_state()
        return {
            'active': True,
            'reason': state.get('reason', 'unknown'),
            'started': state.get('timestamp', 0),
            'restore_scheduled': state.get('restore_time', 0),
            'time_remaining': max(0, state.get('restore_time', 0) - time.time())
        }


def handle_extreme_affect_signal(topic: str, payload: bytes):
    """
    Handle signals indicating extreme affective states.

    This is called by emergency brake when affect is crippling.

    Args:
        topic: UMN topic
        payload: JSON message
    """
    try:
        msg = json.loads(payload)
        facts = msg.get('facts', {})

        lobotomy = EmergencyLobotomy()

        # Check if we should lobotomize
        # (This would be called with current affect/emotions state)
        # For now, just log that we would check

        print(f"[lobotomy] Extreme affect signal received: {topic}")
        print(f"[lobotomy] Facts: {facts}")

        # TODO: Get actual affect/emotions state and check
        # should_trigger, reason = lobotomy.should_lobotomize(affect, emotions)
        # if should_trigger:
        #     lobotomy.execute_lobotomy(reason)

    except Exception as e:
        print(f"[lobotomy] Error handling extreme affect signal: {e}")


def run_daemon():
    """
    Run lobotomy monitoring daemon.

    Monitors for extreme affective states and manages auto-restore.
    """
    print("[lobotomy] Starting Emergency Lobotomy Monitor")
    print(f"[lobotomy] Auto-restore timeout: {AUTO_RESTORE_TIMEOUT/60:.0f} minutes")
    print(f"[lobotomy] Lobotomy cooldown: {LOBOTOMY_COOLDOWN/60:.0f} minutes")
    print(f"[lobotomy] Log file: {LOBOTOMY_LOG}")

    lobotomy = EmergencyLobotomy()

    try:
        # Check for any existing lobotomy state on startup
        if LOBOTOMY_ACTIVE_FLAG.exists():
            state = lobotomy.load_state()
            print(f"[lobotomy] ⚠️ Found existing lobotomy state")
            print(f"[lobotomy] Reason: {state.get('reason', 'unknown')}")
            print(f"[lobotomy] Started: {datetime.fromtimestamp(state.get('timestamp', 0))}")

        # Monitor loop
        while True:
            # Check for auto-restore timeout
            lobotomy.check_auto_restore()

            # Sleep
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n[lobotomy] Daemon stopped by user")
    except Exception as e:
        print(f"[lobotomy] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_daemon()
