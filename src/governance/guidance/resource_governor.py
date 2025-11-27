#!/usr/bin/env python3
"""
Resource Governor - System-wide resource enforcement for ASTRAEA

Prevents runaway resource consumption by enforcing hard limits on:
- Disk space (emergency brake)
- Spawn rate (rate limiting)
- Instance count (hard cap)
- Failure patterns (circuit breaker)

Created: 2025-11-05
Incident: SPICA reproduction crisis (38 instances, 35GB, 96% disk)
"""

import json
import shutil
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

# Metrics integration (optional - graceful degradation if not available)
try:
    from src.orchestration import metrics as prom_metrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.debug("Prometheus metrics not available")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking all requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class SpawnEvent:
    """Record of a spawn attempt."""
    timestamp: float
    success: bool
    reason: Optional[str] = None


@dataclass
class ResourceStatus:
    """Current resource status."""
    disk_free_gb: float
    disk_usage_pct: float
    active_instances: int
    recent_spawns: int
    circuit_state: str
    can_spawn: bool
    blocked_reason: Optional[str] = None


class ResourceGovernor:
    """
    System-wide resource enforcement for SPICA spawning.

    Prevents resource exhaustion through multiple safety layers:
    1. Disk space checks (emergency brake)
    2. Spawn rate limiting (throttling)
    3. Instance count limits (hard cap)
    4. Circuit breaker (failure protection)
    """

    # Class-level warning rate limiter (shared across all instances)
    _last_warning_by_reason: Dict[str, float] = {}
    _warning_throttle_seconds: int = 60

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize resource governor.

        Args:
            config_path: Optional path to config file (defaults to kloros.yaml)
        """
        self.config_path = config_path or Path("/home/kloros/src/config/kloros.yaml")
        self.state_file = Path("/home/kloros/.kloros/resource_governor_state.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Load configuration
        self.config = self._load_config()

        # Initialize or load state
        self.state = self._load_state()

    def _load_config(self) -> Dict[str, Any]:
        """Load resource limits from configuration."""
        defaults = {
            "max_instances": 5,
            "max_spawns_per_hour": 3,
            "min_disk_space_gb": 20,
            "circuit_breaker_threshold": 3,
            "circuit_recovery_seconds": 300,
            "instances_dir": "/home/kloros/experiments/spica/instances"
        }

        try:
            if self.config_path.exists():
                import yaml
                with open(self.config_path) as f:
                    config = yaml.safe_load(f)

                limits = config.get("resource_limits", {}).get("spica", {})
                return {**defaults, **limits}
        except Exception as e:
            logger.warning(f"Failed to load config, using defaults: {e}")

        return defaults

    def _load_state(self) -> Dict[str, Any]:
        """Load or initialize governor state."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

        return {
            "circuit_state": CircuitState.CLOSED.value,
            "circuit_opened_at": None,
            "consecutive_failures": 0,
            "spawn_history": [],
            "last_cleanup": time.time()
        }

    def _save_state(self) -> None:
        """Save governor state atomically."""
        temp_file = self.state_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def _cleanup_old_events(self) -> None:
        """Remove spawn events older than 1 hour."""
        cutoff = time.time() - 3600
        self.state["spawn_history"] = [
            event for event in self.state["spawn_history"]
            if event["timestamp"] > cutoff
        ]
        self.state["last_cleanup"] = time.time()
        self._save_state()

    def check_disk_space(self) -> tuple[bool, Optional[str]]:
        """
        Check if sufficient disk space is available.

        Returns:
            (can_proceed, reason_if_blocked)
        """
        min_gb = self.config["min_disk_space_gb"]

        try:
            usage = shutil.disk_usage("/home/kloros")
            free_gb = usage.free / (1024**3)

            if free_gb < min_gb:
                return False, f"Disk space too low: {free_gb:.1f}GB < {min_gb}GB"

            return True, None

        except Exception as e:
            logger.error(f"Failed to check disk space: {e}")
            return False, f"Disk check failed: {e}"

    def check_spawn_rate(self) -> tuple[bool, Optional[str]]:
        """
        Check if spawn rate is within limits.

        Returns:
            (can_proceed, reason_if_blocked)
        """
        max_per_hour = self.config["max_spawns_per_hour"]

        if time.time() - self.state["last_cleanup"] > 300:
            self._cleanup_old_events()

        cutoff = time.time() - 3600
        recent_spawns = [
            e for e in self.state["spawn_history"]
            if e["timestamp"] > cutoff and e["success"]
        ]

        if len(recent_spawns) >= max_per_hour:
            return False, f"Spawn rate exceeded: {len(recent_spawns)}/{max_per_hour} per hour"

        return True, None

    def check_instance_count(self) -> tuple[bool, Optional[str]]:
        """
        Check if instance count is within limits.

        Returns:
            (can_proceed, reason_if_blocked)
        """
        max_instances = self.config["max_instances"]
        instances_dir = Path(self.config["instances_dir"])

        if not instances_dir.exists():
            return True, None

        instance_count = sum(
            1 for d in instances_dir.iterdir()
            if d.is_dir() and d.name.startswith("spica-")
        )

        if instance_count >= max_instances:
            return False, f"Instance limit reached: {instance_count}/{max_instances}"

        return True, None

    def check_circuit_breaker(self) -> tuple[bool, Optional[str]]:
        """
        Check circuit breaker status.

        Returns:
            (can_proceed, reason_if_blocked)
        """
        state = CircuitState(self.state["circuit_state"])

        if state == CircuitState.CLOSED:
            return True, None

        if state == CircuitState.OPEN:
            opened_at = self.state.get("circuit_opened_at")
            recovery_seconds = self.config["circuit_recovery_seconds"]

            if opened_at and time.time() - opened_at > recovery_seconds:
                self.state["circuit_state"] = CircuitState.HALF_OPEN.value
                self._save_state()
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                return True, None

            return False, "Circuit breaker OPEN (cooling down)"

        if state == CircuitState.HALF_OPEN:
            return True, None

        return False, f"Unknown circuit state: {state}"

    def can_spawn(self) -> tuple[bool, Optional[str]]:
        """
        Check if spawning is allowed.

        Returns:
            (can_proceed, reason_if_blocked)
        """
        checks = [
            ("disk_space", self.check_disk_space()),
            ("spawn_rate", self.check_spawn_rate()),
            ("instance_count", self.check_instance_count()),
            ("circuit_breaker", self.check_circuit_breaker())
        ]

        for check_name, (ok, reason) in checks:
            if not ok:
                # Rate-limit warnings: only log once per throttle period per reason
                now = time.time()
                last_warned = self._last_warning_by_reason.get(check_name, 0)

                if now - last_warned > self._warning_throttle_seconds:
                    logger.warning(f"Spawn blocked by {check_name}: {reason}")
                    self._last_warning_by_reason[check_name] = now
                else:
                    # Suppressed - use debug level for visibility if needed
                    logger.debug(f"Spawn blocked by {check_name}: {reason} (warning throttled)")

                # Update metrics (always, even if warning is throttled)
                if METRICS_AVAILABLE:
                    prom_metrics.spica_spawn_blocks_total.labels(reason=check_name).inc()

                return False, reason

        return True, None

    def record_spawn_attempt(self, success: bool, reason: Optional[str] = None) -> None:
        """
        Record spawn attempt for rate limiting and circuit breaker.

        Args:
            success: Whether spawn succeeded
            reason: Reason for failure (if applicable)
        """
        event = {
            "timestamp": time.time(),
            "success": success,
            "reason": reason
        }

        self.state["spawn_history"].append(event)

        # Update spawn attempt metrics
        if METRICS_AVAILABLE:
            result = "success" if success else "failure"
            prom_metrics.spica_spawn_attempts_total.labels(result=result).inc()

        if success:
            self.state["consecutive_failures"] = 0

            if self.state["circuit_state"] == CircuitState.HALF_OPEN.value:
                old_state = CircuitState.HALF_OPEN.value
                self.state["circuit_state"] = CircuitState.CLOSED.value
                logger.info("Circuit breaker CLOSED (recovery successful)")

                # Update circuit breaker transition metrics
                if METRICS_AVAILABLE:
                    prom_metrics.spica_circuit_breaker_transitions.labels(
                        from_state=old_state,
                        to_state=CircuitState.CLOSED.value
                    ).inc()
        else:
            self.state["consecutive_failures"] += 1

            threshold = self.config["circuit_breaker_threshold"]
            if self.state["consecutive_failures"] >= threshold:
                old_state = self.state["circuit_state"]
                self.state["circuit_state"] = CircuitState.OPEN.value
                self.state["circuit_opened_at"] = time.time()
                logger.error(f"Circuit breaker OPEN (failures: {self.state['consecutive_failures']})")

                # Update circuit breaker transition metrics
                if METRICS_AVAILABLE:
                    prom_metrics.spica_circuit_breaker_transitions.labels(
                        from_state=old_state,
                        to_state=CircuitState.OPEN.value
                    ).inc()

        self._save_state()

    def get_status(self) -> ResourceStatus:
        """Get current resource status."""
        try:
            usage = shutil.disk_usage("/home/kloros")
            disk_free_gb = usage.free / (1024**3)
            disk_usage_pct = (usage.used / usage.total) * 100
        except Exception:
            disk_free_gb = 0.0
            disk_usage_pct = 100.0

        instances_dir = Path(self.config["instances_dir"])
        active_instances = 0
        if instances_dir.exists():
            active_instances = sum(
                1 for d in instances_dir.iterdir()
                if d.is_dir() and d.name.startswith("spica-")
            )

        cutoff = time.time() - 3600
        recent_spawns = sum(
            1 for e in self.state["spawn_history"]
            if e["timestamp"] > cutoff and e["success"]
        )

        can_spawn, blocked_reason = self.can_spawn()

        # Update gauge metrics
        if METRICS_AVAILABLE:
            prom_metrics.spica_instances_current.set(active_instances)
            prom_metrics.spica_disk_free_gb.set(disk_free_gb)

            # Map circuit state to numeric value
            circuit_state_map = {
                CircuitState.CLOSED.value: 0,
                CircuitState.OPEN.value: 1,
                CircuitState.HALF_OPEN.value: 2
            }
            state_value = circuit_state_map.get(self.state["circuit_state"], -1)
            prom_metrics.spica_circuit_breaker_state.set(state_value)

        return ResourceStatus(
            disk_free_gb=disk_free_gb,
            disk_usage_pct=disk_usage_pct,
            active_instances=active_instances,
            recent_spawns=recent_spawns,
            circuit_state=self.state["circuit_state"],
            can_spawn=can_spawn,
            blocked_reason=blocked_reason
        )

    def get_spawn_budget_remaining(self) -> int:
        """Get number of spawns remaining in current hour."""
        max_per_hour = self.config["max_spawns_per_hour"]

        cutoff = time.time() - 3600
        recent_spawns = sum(
            1 for e in self.state["spawn_history"]
            if e["timestamp"] > cutoff and e["success"]
        )

        return max(0, max_per_hour - recent_spawns)

    def reset_circuit(self) -> bool:
        """Manually reset circuit breaker (admin override)."""
        self.state["circuit_state"] = CircuitState.CLOSED.value
        self.state["circuit_opened_at"] = None
        self.state["consecutive_failures"] = 0
        self._save_state()
        logger.info("Circuit breaker manually reset to CLOSED")
        return True


def main():
    """CLI for resource governor inspection."""
    import sys

    governor = ResourceGovernor()

    if len(sys.argv) < 2:
        status = governor.get_status()
        print(f"Disk Free: {status.disk_free_gb:.1f}GB ({status.disk_usage_pct:.1f}% used)")
        print(f"Active Instances: {status.active_instances}/{governor.config['max_instances']}")
        print(f"Recent Spawns: {status.recent_spawns}/{governor.config['max_spawns_per_hour']} per hour")
        print(f"Circuit State: {status.circuit_state}")
        print(f"Can Spawn: {status.can_spawn}")
        if status.blocked_reason:
            print(f"Blocked: {status.blocked_reason}")
        sys.exit(0)

    command = sys.argv[1]

    if command == "check":
        can_spawn, reason = governor.can_spawn()
        if can_spawn:
            print("✓ Spawn allowed")
            sys.exit(0)
        else:
            print(f"✗ Spawn blocked: {reason}")
            sys.exit(1)

    elif command == "reset-circuit":
        governor.reset_circuit()
        print("✓ Circuit breaker reset")
        sys.exit(0)

    else:
        print(f"Unknown command: {command}")
        print("Usage: resource_governor.py [check|reset-circuit]")
        sys.exit(1)


if __name__ == "__main__":
    main()
