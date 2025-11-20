"""Heal event schema and factory."""

from dataclasses import dataclass, field
from typing import Dict, Any
from datetime import datetime
import uuid


@dataclass
class HealEvent:
    """Structured healing event."""

    id: str
    ts: str
    source: str  # e.g., "validator", "rag", "audio"
    kind: str    # e.g., "low_context_overlap", "synthesis_timeout", "beep_echo"
    severity: str  # "warn", "error", "critical"
    context: Dict[str, Any] = field(default_factory=dict)

    def matches(self, pattern: Dict[str, Any]) -> bool:
        """Check if this event matches a playbook pattern.

        Args:
            pattern: Dict with optional fields to match (source, kind, severity)

        Returns:
            True if all specified pattern fields match this event
        """
        for key, val in pattern.items():
            if key == "context":
                # Context matching: check if all pattern context keys exist and match
                for ctx_key, ctx_val in val.items():
                    if self.context.get(ctx_key) != ctx_val:
                        return False
            else:
                # Direct field matching
                if getattr(self, key, None) != val:
                    return False
        return True


def mk_event(source: str, kind: str, severity: str = "warn", **ctx) -> HealEvent:
    """Factory for creating heal events.

    Args:
        source: Event source component
        kind: Event type/kind
        severity: Event severity level
        **ctx: Additional context as keyword arguments

    Returns:
        HealEvent instance
    """
    return HealEvent(
        id=str(uuid.uuid4())[:8],
        ts=datetime.now().isoformat(),
        source=source,
        kind=kind,
        severity=severity,
        context=ctx
    )
