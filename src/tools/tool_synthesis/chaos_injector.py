"""
Chaos injection for resilience testing.

Simulates various failure modes to test error handling, fallbacks, and retries.
"""

import random
import time
from typing import Callable, Any, Optional
from functools import wraps


class ChaosInjector:
    """
    Inject chaos into skill executions for testing resilience.

    Supports:
    - Rate limit errors
    - Timeouts
    - Malformed responses
    - Upstream failures
    - Intermittent failures
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.fault_configs = {}

    def configure_fault(
        self,
        skill_name: str,
        fault_type: str,
        probability: float = 1.0,
        duration_ms: Optional[int] = None
    ):
        """
        Configure a fault to inject into a skill.

        Args:
            skill_name: Name of skill to inject faults into
            fault_type: Type of fault (RATE_LIMIT, TIMEOUT, MALFORMED, UPSTREAM, INTERMITTENT)
            probability: Probability of fault occurring (0.0-1.0)
            duration_ms: Duration of timeout/delay in milliseconds
        """
        self.fault_configs[skill_name] = {
            "type": fault_type,
            "probability": probability,
            "duration_ms": duration_ms
        }

    def should_inject_fault(self, skill_name: str) -> bool:
        """Check if fault should be injected for this execution."""
        if not self.enabled:
            return False

        if skill_name not in self.fault_configs:
            return False

        config = self.fault_configs[skill_name]
        return random.random() < config["probability"]

    def inject(self, skill_name: str) -> None:
        """
        Inject a configured fault.

        Raises:
            RateLimitError: If RATE_LIMIT fault configured
            TimeoutError: If TIMEOUT fault configured
            UpstreamError: If UPSTREAM fault configured
            ValueError: If MALFORMED fault configured
        """
        if not self.should_inject_fault(skill_name):
            return

        config = self.fault_configs[skill_name]
        fault_type = config["type"]

        if fault_type == "RATE_LIMIT":
            raise RateLimitError(f"Rate limit exceeded for {skill_name}")

        elif fault_type == "TIMEOUT":
            duration = config.get("duration_ms", 5000)
            time.sleep(duration / 1000.0)
            raise TimeoutError(f"Request timed out after {duration}ms")

        elif fault_type == "UPSTREAM":
            raise UpstreamError(f"Upstream service unavailable for {skill_name}")

        elif fault_type == "MALFORMED":
            raise ValueError(f"Malformed response from {skill_name}: {{invalid_json")

        elif fault_type == "INTERMITTENT":
            # Randomly fail ~50% of the time
            if random.random() < 0.5:
                raise RuntimeError(f"Intermittent failure in {skill_name}")

    def clear_faults(self):
        """Clear all configured faults."""
        self.fault_configs.clear()


class RateLimitError(Exception):
    """Simulated rate limit error."""
    pass


class UpstreamError(Exception):
    """Simulated upstream service error."""
    pass


def chaos_wrapper(injector: ChaosInjector):
    """
    Decorator to inject chaos into a function.

    Usage:
        @chaos_wrapper(injector)
        def my_skill(input):
            return {"result": "ok"}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Inject fault before execution
            skill_name = func.__name__
            injector.inject(skill_name)

            # Execute function
            return func(*args, **kwargs)

        return wrapper
    return decorator


# Global chaos injector
_injector: Optional[ChaosInjector] = None


def get_chaos_injector() -> ChaosInjector:
    """Get or create global chaos injector."""
    global _injector
    if _injector is None:
        _injector = ChaosInjector(enabled=False)  # Disabled by default
    return _injector


def enable_chaos(enabled: bool = True):
    """Enable or disable chaos injection globally."""
    injector = get_chaos_injector()
    injector.enabled = enabled
