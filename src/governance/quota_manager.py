#!/usr/bin/env python3
"""
KLoROS Quota Manager

Tracks API usage for D-REAM evolution cycles to prevent runaway costs.
Aligns with D-REAM doctrine: controlled budgets, no runaway processes.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional


class QuotaManager:
    """Manages daily API quota for D-REAM evolution."""

    def __init__(self, state_file: str = "/home/kloros/.kloros/quota_state.json"):
        """Initialize quota manager.

        Args:
            state_file: Path to quota state JSON file
        """
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Ensure state file exists
        if not self.state_file.exists():
            self._initialize_state()

    def _initialize_state(self):
        """Create initial quota state file."""
        initial_state = {
            "daily_limit": 100,
            "used_today": 0,
            "remaining": 100,
            "last_reset": datetime.now(timezone.utc).isoformat(),
            "notes": "API quota tracking for D-REAM evolution cycles"
        }

        with open(self.state_file, 'w') as f:
            json.dump(initial_state, f, indent=2)

    def _load_state(self) -> Dict[str, Any]:
        """Load current quota state."""
        try:
            with open(self.state_file) as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            self._initialize_state()
            return self._load_state()

    def _save_state(self, state: Dict[str, Any]):
        """Save quota state atomically."""
        temp_file = self.state_file.with_suffix('.tmp')

        try:
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)

            # Atomic rename
            temp_file.replace(self.state_file)
        except IOError as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _should_reset(self, state: Dict[str, Any]) -> bool:
        """Check if daily quota should reset."""
        try:
            last_reset = datetime.fromisoformat(state.get("last_reset", ""))
            now = datetime.now(timezone.utc)

            # Reset if different day
            return last_reset.date() != now.date()
        except (ValueError, AttributeError):
            return True

    def get_status(self) -> Dict[str, Any]:
        """Get current quota status.

        Returns:
            Dict with daily_limit, used_today, remaining, last_reset
        """
        state = self._load_state()

        # Auto-reset if needed
        if self._should_reset(state):
            state = self._reset_quota(state)

        return {
            "daily_limit": state.get("daily_limit", 100),
            "used_today": state.get("used_today", 0),
            "remaining": state.get("remaining", 100),
            "last_reset": state.get("last_reset")
        }

    def _reset_quota(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Reset daily quota."""
        limit = state.get("daily_limit", 100)

        new_state = {
            "daily_limit": limit,
            "used_today": 0,
            "remaining": limit,
            "last_reset": datetime.now(timezone.utc).isoformat(),
            "notes": state.get("notes", "")
        }

        self._save_state(new_state)
        return new_state

    def check_available(self, required: int = 1) -> bool:
        """Check if enough quota is available.

        Args:
            required: Number of API calls needed

        Returns:
            True if quota available, False otherwise
        """
        status = self.get_status()
        return status["remaining"] >= required

    def consume(self, amount: int = 1) -> bool:
        """Consume quota for API calls.

        Args:
            amount: Number of API calls to consume

        Returns:
            True if successfully consumed, False if insufficient quota
        """
        state = self._load_state()

        # Auto-reset if needed
        if self._should_reset(state):
            state = self._reset_quota(state)

        remaining = state.get("remaining", 0)

        if remaining < amount:
            return False

        # Update state
        state["used_today"] = state.get("used_today", 0) + amount
        state["remaining"] = max(0, remaining - amount)

        self._save_state(state)
        return True

    def set_daily_limit(self, new_limit: int):
        """Update daily quota limit.

        Args:
            new_limit: New daily limit (must be >= 0)
        """
        if new_limit < 0:
            raise ValueError("Daily limit must be non-negative")

        state = self._load_state()

        old_limit = state.get("daily_limit", 100)
        state["daily_limit"] = new_limit

        # Adjust remaining proportionally
        if old_limit > 0:
            usage_pct = state.get("used_today", 0) / old_limit
            state["remaining"] = max(0, int(new_limit * (1 - usage_pct)))
        else:
            state["remaining"] = new_limit

        self._save_state(state)


def main():
    """CLI for quota management."""
    import sys

    manager = QuotaManager()

    if len(sys.argv) < 2:
        # Show status
        status = manager.get_status()
        print(f"Daily Limit: {status['daily_limit']}")
        print(f"Used Today: {status['used_today']}")
        print(f"Remaining: {status['remaining']}")
        print(f"Last Reset: {status['last_reset']}")
        sys.exit(0)

    command = sys.argv[1]

    if command == "check":
        required = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        if manager.check_available(required):
            print(f"✓ Quota available: {manager.get_status()['remaining']} remaining")
            sys.exit(0)
        else:
            print(f"✗ Insufficient quota: {manager.get_status()['remaining']} remaining, {required} required")
            sys.exit(1)

    elif command == "consume":
        amount = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        if manager.consume(amount):
            status = manager.get_status()
            print(f"✓ Consumed {amount}, {status['remaining']} remaining")
            sys.exit(0)
        else:
            print(f"✗ Failed to consume {amount}: insufficient quota")
            sys.exit(1)

    elif command == "set-limit":
        if len(sys.argv) < 3:
            print("Usage: quota_manager.py set-limit <limit>")
            sys.exit(1)

        new_limit = int(sys.argv[2])
        manager.set_daily_limit(new_limit)
        print(f"✓ Daily limit set to {new_limit}")
        sys.exit(0)

    else:
        print(f"Unknown command: {command}")
        print("Usage: quota_manager.py [check|consume|set-limit] [args]")
        sys.exit(1)


if __name__ == "__main__":
    main()
