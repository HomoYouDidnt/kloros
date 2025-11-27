"""
Runtime Exception Bridge - Connect Python exceptions to KLoROS meta-cognition

This module bridges the gap between runtime errors and self-awareness by feeding
Python exceptions into the D-REAM alert system and curiosity feed.
"""

import sys
import traceback
import threading
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import os


class RuntimeExceptionBridge:
    """
    Feed Python exceptions into KLoROS meta-cognition systems.

    Provides self-awareness of runtime health by escalating exceptions to:
    - D-REAM alert manager (for autonomous repair triggers)
    - Curiosity feed (for self-debugging questions)
    - System logs (for observability)
    """

    def __init__(self, kloros_instance=None):
        """
        Initialize runtime exception bridge.

        Args:
            kloros_instance: KLoROS instance with dream_alert and curiosity systems
        """
        self.kloros = kloros_instance
        self.enabled = int(os.getenv("KLR_ENABLE_EXCEPTION_BRIDGE", "1"))
        self.exception_count = {}
        self._lock = threading.Lock()

        if not self.enabled:
            print("[exception-bridge] Disabled via KLR_ENABLE_EXCEPTION_BRIDGE=0")
            return

        print("[exception-bridge] Runtime exception monitoring initialized")

    def log_exception(
        self,
        exc: Exception,
        context: Optional[Dict[str, Any]] = None,
        severity: str = "error"
    ) -> None:
        """
        Log exception to meta-cognition systems.

        Args:
            exc: The exception that occurred
            context: Additional context about where/why the exception occurred
            severity: error, warning, or critical
        """
        if not self.enabled:
            return

        context = context or {}
        exc_type = type(exc).__name__
        exc_msg = str(exc)

        # Track exception frequency
        with self._lock:
            key = f"{exc_type}:{exc_msg[:50]}"
            self.exception_count[key] = self.exception_count.get(key, 0) + 1
            count = self.exception_count[key]

        # Get stack trace
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        stack_trace = ''.join(tb_lines)

        # Log to console (always)
        print(f"[exception-bridge] {severity.upper()}: {exc_type}: {exc_msg}")
        if count > 1:
            print(f"[exception-bridge] (occurrence #{count})")

        # Feed to D-REAM alert system if available
        if self.kloros and hasattr(self.kloros, 'dream_alert'):
            try:
                self._escalate_to_dream(exc_type, exc_msg, stack_trace, context, severity, count)
            except Exception as e:
                print(f"[exception-bridge] Failed to escalate to D-REAM: {e}")

        # Feed to curiosity system if available and it's a new/recurring issue
        if self.kloros and count in [1, 5, 10, 25]:  # Escalate at thresholds
            try:
                self._generate_curiosity_question(exc_type, exc_msg, stack_trace, context, count)
            except Exception as e:
                print(f"[exception-bridge] Failed to generate curiosity: {e}")

    def _escalate_to_dream(
        self,
        exc_type: str,
        exc_msg: str,
        stack_trace: str,
        context: Dict[str, Any],
        severity: str,
        count: int
    ) -> None:
        """Escalate exception to D-REAM alert system."""
        try:
            from src.dream.alert_manager import get_alert_manager

            alert_mgr = get_alert_manager()
            if not alert_mgr:
                return

            category = "runtime_exception"
            hypothesis = f"RUNTIME_FAILURE_{exc_type.upper()}"

            # Build evidence list
            evidence = [
                f"exception_type:{exc_type}",
                f"message:{exc_msg}",
                f"occurrence_count:{count}",
                f"severity:{severity}"
            ]

            # Add context if available
            if context:
                for key, value in context.items():
                    evidence.append(f"{key}:{value}")

            # Add truncated stack trace
            stack_lines = stack_trace.split('\n')
            evidence.extend(stack_lines[:10])  # First 10 lines of stack trace

            # Determine if this requires immediate action
            autonomy = 3 if severity == "critical" or count >= 5 else 2
            value_estimate = 0.95 if severity == "critical" else 0.8

            alert_mgr.escalate(
                category=category,
                hypothesis=hypothesis,
                evidence=evidence,
                proposed_action=self._suggest_fix(exc_type, exc_msg, context),
                autonomy=autonomy,
                value_estimate=value_estimate
            )

            print(f"[exception-bridge] ✓ Escalated to D-REAM: {hypothesis}")

        except Exception as e:
            # Don't let escalation failure crash the system
            print(f"[exception-bridge] D-REAM escalation error: {e}")

    def _generate_curiosity_question(
        self,
        exc_type: str,
        exc_msg: str,
        stack_trace: str,
        context: Dict[str, Any],
        count: int
    ) -> None:
        """Generate curiosity question for self-debugging."""
        try:
            from src.registry.curiosity_core import get_curiosity_system

            curiosity = get_curiosity_system()
            if not curiosity:
                return

            # Craft question based on exception type and frequency
            if count == 1:
                question = f"Why am I experiencing {exc_type} for the first time? {exc_msg}"
            elif count < 10:
                question = f"Why does {exc_type} keep recurring ({count} times)? How can I fix it?"
            else:
                question = f"URGENT: {exc_type} has occurred {count} times. What is the root cause?"

            hypothesis = f"SELF_DEBUGGING_{exc_type.upper()}"

            # Add evidence
            evidence = [
                f"exception:{exc_type}",
                f"message:{exc_msg[:100]}",
                f"occurrences:{count}"
            ]
            if context:
                evidence.extend(context.keys())

            curiosity.add_question(
                question=question,
                hypothesis=hypothesis,
                evidence=evidence,
                action_class="self_debug",
                autonomy=3,  # High autonomy to self-investigate
                value_estimate=0.95  # Critical to fix own bugs
            )

            print(f"[exception-bridge] ✓ Generated curiosity question: {question[:80]}...")

        except Exception as e:
            print(f"[exception-bridge] Curiosity generation error: {e}")

    def _suggest_fix(
        self,
        exc_type: str,
        exc_msg: str,
        context: Dict[str, Any]
    ) -> str:
        """Suggest a fix based on exception type."""

        # Common patterns
        if exc_type == "PermissionError":
            return "investigate_and_fix_permissions"
        elif exc_type in ["ModuleNotFoundError", "ImportError"]:
            return "verify_dependencies_and_imports"
        elif exc_type == "AttributeError":
            return "check_object_initialization"
        elif exc_type in ["KeyError", "IndexError"]:
            return "validate_data_structure_access"
        elif exc_type == "TypeError":
            return "verify_function_arguments_and_types"
        elif "database" in exc_msg.lower() or "disk" in exc_msg.lower():
            return "check_database_and_storage_health"
        elif "timeout" in exc_msg.lower():
            return "investigate_blocking_operations"
        elif "connection" in exc_msg.lower():
            return "verify_network_connectivity"
        else:
            return "analyze_stack_trace_and_debug"

    def _classify_severity(self, exc: Exception) -> str:
        """Classify exception severity."""
        exc_type = type(exc).__name__

        # Critical exceptions that block operation
        if exc_type in ["SystemExit", "KeyboardInterrupt", "MemoryError"]:
            return "critical"

        # Errors that prevent features from working
        if exc_type in ["PermissionError", "FileNotFoundError", "ModuleNotFoundError"]:
            return "error"

        # Warnings for recoverable issues
        if exc_type in ["Warning", "UserWarning", "DeprecationWarning"]:
            return "warning"

        # Default to error
        return "error"

    def get_stats(self) -> Dict[str, Any]:
        """Get exception statistics."""
        with self._lock:
            total_exceptions = sum(self.exception_count.values())
            return {
                "total_exceptions": total_exceptions,
                "unique_exceptions": len(self.exception_count),
                "top_exceptions": sorted(
                    self.exception_count.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
            }


# Global instance (lazy initialization)
_exception_bridge: Optional[RuntimeExceptionBridge] = None


def get_exception_bridge() -> Optional[RuntimeExceptionBridge]:
    """Get global exception bridge instance."""
    return _exception_bridge


def init_exception_bridge(kloros_instance) -> RuntimeExceptionBridge:
    """Initialize global exception bridge."""
    global _exception_bridge
    _exception_bridge = RuntimeExceptionBridge(kloros_instance)
    return _exception_bridge


# Decorator for automatic exception monitoring
def monitor_exceptions(func: Callable) -> Callable:
    """
    Decorator to automatically log exceptions to meta-cognition.

    Usage:
        @monitor_exceptions
        def my_function():
            # Your code here
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            bridge = get_exception_bridge()
            if bridge:
                bridge.log_exception(
                    exc=e,
                    context={
                        "function": func.__name__,
                        "module": func.__module__
                    }
                )
            raise  # Re-raise to preserve normal exception handling
    return wrapper
