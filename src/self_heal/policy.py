"""Guardrails and safety policies for healing actions."""

import os
import time
from typing import Dict, Any


class Guardrails:
    """Safety policies for healing actions."""

    # Healing modes
    SAFE = "SAFE"      # Require explicit confirmation (future feature)
    AUTO = "AUTO"      # Automatically apply fixes
    DRY_RUN = "DRY-RUN"  # Log what would happen but don't execute

    def __init__(self, mode: str = None):
        """Initialize guardrails.

        Args:
            mode: Healing mode (SAFE, AUTO, DRY-RUN). Defaults to env var or SAFE.
        """
        self.mode = mode or os.getenv("KLR_HEAL_MODE", self.SAFE)
        self.rate_limit = int(os.getenv("KLR_HEAL_RATE_LIMIT", "6"))  # per minute
        self._tokens: Dict[str, list] = {}  # source -> list of timestamps

    def should_heal(self, event) -> bool:
        """Check if healing should proceed for this event.

        Args:
            event: HealEvent to check

        Returns:
            True if healing should proceed
        """
        # DRY-RUN mode always returns False (just log)
        if self.mode == self.DRY_RUN:
            return False

        # SAFE mode: for now, always allow (future: require confirmation)
        # AUTO mode: check rate limits
        return self._check_rate_limit(event.source)

    def _check_rate_limit(self, source: str) -> bool:
        """Token bucket rate limiting per source.

        Args:
            source: Event source to check

        Returns:
            True if rate limit allows healing
        """
        now = time.time()
        window = 60.0  # 1 minute window

        # Clean old tokens
        if source not in self._tokens:
            self._tokens[source] = []

        self._tokens[source] = [
            ts for ts in self._tokens[source]
            if now - ts < window
        ]

        # Check if under limit
        if len(self._tokens[source]) >= self.rate_limit:
            print(f"[guardrails] Rate limit exceeded for {source}")
            return False

        # Add token
        self._tokens[source].append(now)
        return True

    def is_action_allowed(self, action_name: str, params: Dict[str, Any]) -> bool:
        """Check if a specific action with parameters is allowed.

        Args:
            action_name: Name of the action
            params: Action parameters

        Returns:
            True if action is allowed
        """
        # Whitelist of safe actions
        safe_actions = {
            # Application-level actions
            "set_flag",
            "set_timeout",
            "lower_threshold",
            "enforce_mute_wrapper",
            "enable_ack",
            # System-level actions
            "clear_swap",
            "kill_duplicate_process",
            "kill_stuck_processes",
            "restart_service"
        }

        if action_name not in safe_actions:
            print(f"[guardrails] Action '{action_name}' not in whitelist")
            return False

        # Parameter validation
        if action_name == "set_timeout" and params.get("new_timeout_s", 0) > 300:
            print(f"[guardrails] Timeout too large: {params['new_timeout_s']}s")
            return False

        # System action validation
        if action_name == "restart_service":
            # Only allow restarting specific safe services
            allowed_services = {"kloros.service", "kloros-observer.service"}
            service = params.get("service", "")
            if service not in allowed_services:
                print(f"[guardrails] Service restart not allowed: {service}")
                return False

        if action_name == "kill_stuck_processes":
            # Ensure pattern is provided to avoid killing all processes
            if "pattern" not in params or not params["pattern"]:
                print(f"[guardrails] kill_stuck_processes requires pattern")
                return False

        return True
