#!/usr/bin/env python3
"""
D-REAM Telemetry Logger Module
Structured event logging for evolution runs.
"""

import json
import time
import hashlib
import pathlib
from typing import Dict, Any, Optional, List
from datetime import datetime
import threading
import logging

logger = logging.getLogger(__name__)


class EventLogger:
    """Thread-safe structured event logger."""

    def __init__(self, path: str, buffer_size: int = 100):
        """
        Initialize event logger.

        Args:
            path: Path to JSONL log file
            buffer_size: Number of events to buffer before flush
        """
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.buffer_size = buffer_size
        self.buffer = []
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.event_count = 0

        # Write header event
        self.emit("logger_init", {
            "path": str(self.path),
            "buffer_size": buffer_size,
            "timestamp": datetime.now().isoformat()
        })

    def emit(self, event_type: str, payload: Dict[str, Any], 
             level: str = "INFO"):
        """
        Emit a structured event.

        Args:
            event_type: Type of event
            payload: Event data
            level: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        """
        with self.lock:
            record = {
                "ts": time.time(),
                "ts_iso": datetime.now().isoformat(),
                "elapsed": time.time() - self.start_time,
                "seq": self.event_count,
                "event": event_type,
                "level": level,
                "payload": payload
            }
            
            self.buffer.append(record)
            self.event_count += 1

            # Flush if buffer is full
            if len(self.buffer) >= self.buffer_size:
                self._flush()

    def _flush(self):
        """Flush buffer to file (must be called with lock held)."""
        if not self.buffer:
            return

        try:
            with self.path.open("a", encoding="utf-8") as f:
                for record in self.buffer:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
            flushed = len(self.buffer)
            self.buffer.clear()
            logger.debug(f"Flushed {flushed} events to {self.path}")
            
        except Exception as e:
            logger.error(f"Failed to flush events: {e}")

    def flush(self):
        """Public flush method."""
        with self.lock:
            self._flush()

    def close(self):
        """Close logger and flush remaining events."""
        self.flush()
        self.emit("logger_close", {
            "total_events": self.event_count,
            "elapsed": time.time() - self.start_time
        })
        self.flush()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class TelemetryCollector:
    """Collect and aggregate telemetry data."""

    def __init__(self, logger: EventLogger):
        self.logger = logger
        self.metrics = {}
        self.timers = {}

    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record a metric value."""
        self.logger.emit("metric", {
            "name": name,
            "value": value,
            "tags": tags or {}
        })
        
        # Update aggregates
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(value)

    def start_timer(self, name: str):
        """Start a named timer."""
        self.timers[name] = time.time()
        self.logger.emit("timer_start", {"name": name})

    def stop_timer(self, name: str) -> float:
        """Stop a timer and return elapsed time."""
        if name not in self.timers:
            logger.warning(f"Timer {name} not started")
            return 0.0

        elapsed = time.time() - self.timers[name]
        del self.timers[name]
        
        self.logger.emit("timer_stop", {
            "name": name,
            "elapsed": elapsed
        })
        
        self.record_metric(f"{name}_duration", elapsed)
        return elapsed

    def record_event(self, name: str, data: Dict[str, Any]):
        """Record a custom event."""
        self.logger.emit(name, data)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        import statistics as st
        
        summary = {}
        for name, values in self.metrics.items():
            if values:
                summary[name] = {
                    "count": len(values),
                    "mean": st.mean(values),
                    "min": min(values),
                    "max": max(values),
                    "std": st.stdev(values) if len(values) > 1 else 0
                }
        
        return summary
