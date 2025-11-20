"""
Circuit breaker with auto-masking for tool synthesis.

Automatically masks tools when error rate exceeds threshold,
preventing cascading failures and resource exhaustion.
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque


# Import logging with fallback
try:
    from src.tool_synthesis.logging import log
except ImportError:
    # Fallback for testing
    def log(event: str, **kwargs):
        pass


@dataclass
class ExecutionRecord:
    """Single execution record."""
    timestamp: float
    success: bool


@dataclass
class BreakerState:
    """State of a circuit breaker."""
    tool_name: str
    is_open: bool = False  # True = circuit open (tool masked)
    opened_at: Optional[float] = None
    executions: deque = field(default_factory=lambda: deque(maxlen=100))  # Last 100 executions
    consecutive_failures: int = 0
    total_calls: int = 0
    total_errors: int = 0


class CircuitBreaker:
    """
    Circuit breaker that auto-masks tools on high error rates.

    When a tool's error rate exceeds the threshold within the time window,
    the circuit "opens" and the tool is auto-masked to prevent further calls.

    After a cooldown period, the circuit can be reset manually or automatically.
    """

    def __init__(
        self,
        error_threshold: float = 0.5,  # 50% error rate
        window_seconds: int = 60,  # 1 minute window
        cooldown_seconds: int = 300,  # 5 minute cooldown
        min_calls: int = 5  # Minimum calls before opening circuit
    ):
        self.error_threshold = error_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.min_calls = min_calls

        # tool_name -> BreakerState
        self.breakers: Dict[str, BreakerState] = {}

    def record_execution(self, tool_name: str, success: bool):
        """
        Record a tool execution.

        Args:
            tool_name: Name of tool
            success: Whether execution succeeded
        """
        if tool_name not in self.breakers:
            self.breakers[tool_name] = BreakerState(tool_name=tool_name)

        breaker = self.breakers[tool_name]
        now = time.time()

        # Add execution record
        breaker.executions.append(ExecutionRecord(timestamp=now, success=success))
        breaker.total_calls += 1

        if success:
            breaker.consecutive_failures = 0
        else:
            breaker.consecutive_failures += 1
            breaker.total_errors += 1

        # Check if circuit should open
        if not breaker.is_open and self._should_open_circuit(breaker):
            self._open_circuit(breaker)

    def is_open(self, tool_name: str) -> bool:
        """
        Check if circuit is open (tool is masked).

        Args:
            tool_name: Name of tool

        Returns:
            True if circuit is open
        """
        if tool_name not in self.breakers:
            return False

        breaker = self.breakers[tool_name]

        # Check if cooldown period has passed
        if breaker.is_open and breaker.opened_at:
            if time.time() - breaker.opened_at > self.cooldown_seconds:
                # Auto-recover after cooldown
                self._close_circuit(breaker)
                return False

        return breaker.is_open

    def _should_open_circuit(self, breaker: BreakerState) -> bool:
        """
        Check if circuit should open based on error rate.

        Args:
            breaker: Breaker state

        Returns:
            True if circuit should open
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Get executions within window
        recent_execs = [
            e for e in breaker.executions
            if e.timestamp >= window_start
        ]

        if len(recent_execs) < self.min_calls:
            # Not enough data
            return False

        # Calculate error rate
        errors = sum(1 for e in recent_execs if not e.success)
        error_rate = errors / len(recent_execs)

        return error_rate >= self.error_threshold

    def _open_circuit(self, breaker: BreakerState):
        """
        Open circuit (mask tool).

        Args:
            breaker: Breaker state
        """
        breaker.is_open = True
        breaker.opened_at = time.time()

        # Log circuit opening
        log(
            "circuit_breaker.opened",
            tool=breaker.tool_name,
            total_calls=breaker.total_calls,
            total_errors=breaker.total_errors,
            error_rate=breaker.total_errors / breaker.total_calls if breaker.total_calls > 0 else 0,
            cooldown_seconds=self.cooldown_seconds
        )

    def _close_circuit(self, breaker: BreakerState):
        """
        Close circuit (unmask tool).

        Args:
            breaker: Breaker state
        """
        breaker.is_open = False
        breaker.opened_at = None
        breaker.consecutive_failures = 0

        # Clear old execution records
        breaker.executions.clear()

        # Log circuit closing
        log(
            "circuit_breaker.closed",
            tool=breaker.tool_name,
            reason="cooldown_elapsed"
        )

    def reset(self, tool_name: str):
        """
        Manually reset circuit breaker for a tool.

        Args:
            tool_name: Name of tool to reset
        """
        if tool_name in self.breakers:
            breaker = self.breakers[tool_name]
            if breaker.is_open:
                self._close_circuit(breaker)

                log(
                    "circuit_breaker.manual_reset",
                    tool=tool_name
                )

    def get_status(self, tool_name: str) -> Dict:
        """
        Get circuit breaker status for a tool.

        Args:
            tool_name: Name of tool

        Returns:
            Status dict with is_open, error_rate, calls, etc.
        """
        if tool_name not in self.breakers:
            return {
                "is_open": False,
                "total_calls": 0,
                "total_errors": 0,
                "error_rate": 0.0,
                "consecutive_failures": 0
            }

        breaker = self.breakers[tool_name]
        error_rate = breaker.total_errors / breaker.total_calls if breaker.total_calls > 0 else 0.0

        return {
            "is_open": breaker.is_open,
            "total_calls": breaker.total_calls,
            "total_errors": breaker.total_errors,
            "error_rate": error_rate,
            "consecutive_failures": breaker.consecutive_failures,
            "opened_at": breaker.opened_at,
            "cooldown_remaining": (
                self.cooldown_seconds - (time.time() - breaker.opened_at)
                if breaker.opened_at
                else 0
            )
        }

    def get_all_open_circuits(self) -> List[str]:
        """
        Get list of all tools with open circuits.

        Returns:
            List of tool names
        """
        return [
            name for name, breaker in self.breakers.items()
            if breaker.is_open
        ]


# Global circuit breaker instance
_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get or create global circuit breaker."""
    global _breaker
    if _breaker is None:
        _breaker = CircuitBreaker()
    return _breaker
