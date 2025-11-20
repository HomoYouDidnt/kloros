"""Event and metrics observation for chaos experiments."""

from typing import Dict, Any, Optional, List
from datetime import datetime


class TraceObserver:
    """Observes heal events and system metrics during chaos experiments."""

    def __init__(self, metrics=None, logger=None):
        """Initialize observer.

        Args:
            metrics: Optional metrics system
            logger: Optional logger
        """
        self.metrics = metrics
        self.logger = logger
        self._events: List[tuple] = []
        self._start_time = datetime.now()

    def on_event(self, event):
        """Handle a heal event.

        Args:
            event: HealEvent from the bus
        """
        self._events.append((
            event.source,
            event.kind,
            event.severity,
            event.context.copy() if hasattr(event.context, 'copy') else dict(event.context),
            datetime.now()
        ))

        if self.logger:
            self.logger.info(
                f"[chaos] Event: {event.source}.{event.kind} "
                f"severity={event.severity}"
            )

    def seen_event(
        self,
        source: Optional[str] = None,
        kind: Optional[str] = None,
        severity: Optional[str] = None
    ) -> bool:
        """Check if a matching event was observed.

        Args:
            source: Event source to match (optional)
            kind: Event kind to match (optional)
            severity: Event severity to match (optional)

        Returns:
            True if matching event was seen
        """
        return any(
            (source is None or e[0] == source) and
            (kind is None or e[1] == kind) and
            (severity is None or e[2] == severity)
            for e in self._events
        )

    def get_events(
        self,
        source: Optional[str] = None,
        kind: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all matching events.

        Args:
            source: Filter by source (optional)
            kind: Filter by kind (optional)

        Returns:
            List of event dicts
        """
        events = []
        for e in self._events:
            if (source is None or e[0] == source) and (kind is None or e[1] == kind):
                events.append({
                    "source": e[0],
                    "kind": e[1],
                    "severity": e[2],
                    "context": e[3],
                    "timestamp": e[4].isoformat()
                })
        return events

    def snapshot(self) -> Dict[str, Any]:
        """Capture current system metrics snapshot.

        Returns:
            Dict of metric values
        """
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "events_count": len(self._events),
            "duration_s": (datetime.now() - self._start_time).total_seconds()
        }

        if self.metrics:
            # Sample key metrics if metrics system is available
            snapshot.update({
                "synth_timeout_rate": self._read_rate("rag.synthesis.timeout_rate"),
                "false_vad_rate": self._read_rate("asr.false_trigger_rate"),
                "heal_success_rate": self._read_rate("self_heal.success_rate"),
                "validator_rejection_rate": self._read_rate("validator.rejection_rate")
            })

        return snapshot

    def _read_rate(self, name: str, window_s: int = 300) -> float:
        """Read a rate metric if available.

        Args:
            name: Metric name
            window_s: Time window in seconds

        Returns:
            Rate value or 0.0 if unavailable
        """
        if not self.metrics:
            return 0.0

        try:
            if hasattr(self.metrics, 'read_rate'):
                return self.metrics.read_rate(name, window_s)
            elif hasattr(self.metrics, 'get'):
                return self.metrics.get(name, 0.0)
        except Exception:
            pass

        return 0.0

    def reset(self):
        """Reset observer state for new experiment."""
        self._events.clear()
        self._start_time = datetime.now()

    def get_summary(self) -> Dict[str, Any]:
        """Get experiment summary.

        Returns:
            Summary dict with event counts and timing
        """
        duration = (datetime.now() - self._start_time).total_seconds()

        # Count events by source
        by_source = {}
        for e in self._events:
            source = e[0]
            by_source[source] = by_source.get(source, 0) + 1

        # Count by severity
        by_severity = {}
        for e in self._events:
            severity = e[2]
            by_severity[severity] = by_severity.get(severity, 0) + 1

        return {
            "total_events": len(self._events),
            "duration_s": duration,
            "events_by_source": by_source,
            "events_by_severity": by_severity,
            "events_per_second": len(self._events) / duration if duration > 0 else 0
        }
