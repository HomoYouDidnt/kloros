"""
Event sources for the Observer.

Provides streaming event collection from:
- journald (systemd logs)
- filesystem watchers (inotify)
- metrics scraping (Prometheus)
"""

import os
import time
import json
import logging
from pathlib import Path
from typing import Iterator, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Normalized event from any source."""
    source: str  # "journald", "inotify", "metrics"
    type: str    # "promotion_new", "phase_complete", "gpu_oom", etc.
    ts: float    # timestamp
    data: Dict[str, Any]  # source-specific payload

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def hash_key(self) -> str:
        """Deduplication key for rate-limiting."""
        # Hash on (source, type, relevant data fields)
        key_data = f"{self.source}:{self.type}"
        if "path" in self.data:
            key_data += f":{self.data['path']}"
        if "unit" in self.data:
            key_data += f":{self.data['unit']}"
        return key_data


class JournaldSource:
    """Stream events from systemd journal."""

    def __init__(self, units: list[str] = None, watch_kernel: bool = False):
        """
        Args:
            units: List of systemd units to watch (e.g., ["dream.service", "kloros.service"])
            watch_kernel: If True, watch kernel logs (_TRANSPORT=kernel) instead of units
        """
        self.units = units or []
        self.watch_kernel = watch_kernel
        self._proc = None

    def stream(self) -> Iterator[Event]:
        """
        Yield events from journal in real-time.

        Uses: journalctl -u SERVICE -f --output=json (for units)
              journalctl _TRANSPORT=kernel -f --output=json (for kernel)
        """
        import subprocess

        if self.watch_kernel:
            cmd = ["journalctl", "_TRANSPORT=kernel", "-f", "--output=json", "--since=now"]
        else:
            unit_args = []
            for unit in self.units:
                unit_args.extend(["-u", unit])
            cmd = ["journalctl"] + unit_args + ["-f", "--output=json", "--since=now"]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            if self.watch_kernel:
                logger.info("JournaldSource streaming: kernel logs")
            else:
                logger.info(f"JournaldSource streaming: {self.units}")

            for line in iter(self._proc.stdout.readline, ""):
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)

                    # Extract PRIORITY field for filtering
                    priority = int(entry.get('PRIORITY', 6))

                    # Extract relevant fields
                    message = entry.get("MESSAGE", "")
                    # MESSAGE can be a list if it contains multiple lines
                    if isinstance(message, list):
                        message = "\n".join(str(m) for m in message)
                    elif not isinstance(message, str):
                        message = str(message)

                    # For kernel logs, use SYSLOG_IDENTIFIER or _COMM instead of _SYSTEMD_UNIT
                    if self.watch_kernel:
                        unit = entry.get("SYSLOG_IDENTIFIER", entry.get("_COMM", "kernel"))
                    else:
                        unit = entry.get("_SYSTEMD_UNIT", "")

                    ts = float(entry.get("__REALTIME_TIMESTAMP", time.time() * 1e6)) / 1e6

                    # Classify event type from message
                    event_type = self._classify_message(message, unit, is_kernel=self.watch_kernel, priority=priority)

                    if event_type:
                        yield Event(
                            source="journald",
                            type=event_type,
                            ts=ts,
                            data={"unit": unit, "message": message}
                        )

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from journalctl: {line[:100]}")
                except Exception as e:
                    logger.error(f"Error processing journal entry: {e}")

        finally:
            if self._proc:
                self._proc.terminate()

    def _classify_message(self, message: str, unit: str, is_kernel: bool = False, priority: int = 6) -> str | None:
        """
        Classify journal message into event type.

        Args:
            message: Log message text
            unit: Systemd unit or identifier
            is_kernel: Whether this is a kernel log
            priority: Journald PRIORITY field (0-7, lower=more severe)
                0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug
        """
        msg_lower = message.lower()

        # Kernel-specific error patterns (hardware/driver failures)
        if is_kernel:
            # Critical kernel errors (firmware crashes, hardware failures, panics)
            kernel_critical = [
                "[err]",           # Kernel error prefix
                "oops",            # Kernel oops
                "panic",           # Kernel panic
                "bug:",            # Kernel bug
                "firmware crash",  # Firmware crash
                "hardware error",  # Hardware error
                "mce:",            # Machine check exception
                "segfault",        # Segmentation fault
                "general protection fault",
                "fw crash",        # Firmware crash (short form)
                "ser catches error",  # System error recovery (Wi-Fi specific)
            ]

            for pattern in kernel_critical:
                if pattern in msg_lower:
                    return "error_kernel_critical"

            # Operational kernel errors (driver issues, hardware warnings)
            kernel_errors = [
                "error",
                "failed",
                "failure",
                "timeout",
                "i/o error",
                "badaddr",         # Bad memory address
                "halt",
                "warning",
            ]

            for pattern in kernel_errors:
                if pattern in msg_lower:
                    return "error_kernel_operational"

            # Skip non-error kernel messages (too noisy)
            return None

        # D-REAM events
        if "dream" in unit.lower():
            if "promotion" in msg_lower:
                return "dream_promotion"
            if "survivor" in msg_lower or "generation" in msg_lower:
                return "dream_generation"
            if "failed" in msg_lower or "error" in msg_lower:
                return "dream_error"

        # PHASE events
        if "phase" in unit.lower():
            if "complete" in msg_lower or "finished" in msg_lower:
                return "phase_complete"
            if "timeout" in msg_lower:
                return "phase_timeout"
            if "failed" in msg_lower:
                return "phase_error"

        # GPU/resource events
        if "oom" in msg_lower or "out of memory" in msg_lower:
            return "gpu_oom"

        # Lock contention
        if "lock" in msg_lower and "contention" in msg_lower:
            return "lock_contention"

        # Generic operational errors (CRITICAL: must be investigated immediately)
        # Only apply keyword matching to warning or higher severity (priority <= 4)
        # INFO-level logs (priority >= 5) never trigger error classification
        error_keywords = [
            "error:",
            "exception",
            "traceback",
            "failed:",
            "failure:",
            "critical:",
            "fatal:",
            "valueerror",
            "typeerror",
            "keyerror",
            "attributeerror",
            "indexerror"
        ]

        if priority <= 4:
            for keyword in error_keywords:
                if keyword in msg_lower:
                    # Determine severity
                    if any(x in msg_lower for x in ["critical", "fatal", "oom", "crash"]):
                        return "error_critical"
                    return "error_operational"

        return None


class InotifySource:
    """Watch filesystem paths for changes."""

    def __init__(self, paths: list[Path]):
        """
        Args:
            paths: List of paths to watch (files or directories)
        """
        self.paths = [Path(p) for p in paths]

    def stream(self) -> Iterator[Event]:
        """
        Yield events for file/directory changes.

        Uses: inotify via watchdog library
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
        except ImportError:
            logger.error("watchdog not installed: pip install watchdog")
            return

        class EventHandler(FileSystemEventHandler):
            def __init__(self, event_queue):
                self.event_queue = event_queue

            def on_created(self, event: FileSystemEvent):
                if not event.is_directory:
                    self.event_queue.append(("created", event.src_path))

            def on_modified(self, event: FileSystemEvent):
                if not event.is_directory:
                    self.event_queue.append(("modified", event.src_path))

        import queue
        event_queue = []

        observer = Observer()
        handler = EventHandler(event_queue)

        for path in self.paths:
            if path.exists():
                observer.schedule(handler, str(path), recursive=False)
                logger.info(f"InotifySource watching: {path}")

        observer.start()

        try:
            while True:
                if event_queue:
                    action, path_str = event_queue.pop(0)

                    # Classify file event
                    event_type = self._classify_file(Path(path_str), action)

                    if event_type:
                        yield Event(
                            source="inotify",
                            type=event_type,
                            ts=time.time(),
                            data={"path": path_str, "action": action}
                        )

                time.sleep(0.1)  # Poll queue

        finally:
            observer.stop()
            observer.join()

    def _classify_file(self, path: Path, action: str) -> str | None:
        """Classify file change into event type."""
        name = path.name
        parent = path.parent.name

        # Promotion files
        if parent == "promotions" and name.endswith(".json"):
            return "promotion_new"

        # PHASE signals
        if parent == "signals" and "phase_complete" in name:
            return "phase_signal"

        # D-REAM heartbeat
        if name == "ready" and "dream" in str(path):
            return "dream_heartbeat"

        return None


class SystemdAuditSource:
    """Audit systemd services and timers for disabled items."""

    def __init__(self, interval_s: int = 86400):
        """
        Args:
            interval_s: Audit interval in seconds (default: 24 hours)
        """
        self.interval_s = interval_s
        self._audited_units = set()

    def stream(self) -> Iterator[Event]:
        """
        Yield events for disabled systemd units.

        Runs audit on startup and then every interval_s seconds.
        Rate-limits emission to 1 event per second to avoid flooding intent router.
        """
        while True:
            try:
                disabled_units = self._get_disabled_units()

                for unit_name, unit_type in disabled_units:
                    # Skip if already audited
                    if unit_name in self._audited_units:
                        continue

                    self._audited_units.add(unit_name)

                    yield Event(
                        source="systemd_audit",
                        type="systemd_disabled",
                        ts=time.time(),
                        data={
                            "unit": unit_name,
                            "unit_type": unit_type,
                            "state": "disabled"
                        }
                    )

                    # Rate-limit: 1 event per second to avoid overwhelming intent router
                    # Prevents cascading failures from bulk emission
                    time.sleep(1.0)

            except Exception as e:
                logger.warning(f"Systemd audit error: {e}")

            time.sleep(self.interval_s)

    def _get_disabled_units(self) -> list[tuple[str, str]]:
        """Get list of disabled systemd services and timers."""
        import subprocess

        disabled_units = []

        try:
            # List all services
            result = subprocess.run(
                ["systemctl", "list-unit-files", "--type=service", "--state=disabled", "--no-pager", "--no-legend"],
                capture_output=True,
                text=True,
                timeout=10
            )

            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    unit_name = parts[0]
                    # Filter out system/boot services that should stay disabled
                    if not self._is_system_service(unit_name):
                        disabled_units.append((unit_name, "service"))

            # List all timers
            result = subprocess.run(
                ["systemctl", "list-unit-files", "--type=timer", "--state=disabled", "--no-pager", "--no-legend"],
                capture_output=True,
                text=True,
                timeout=10
            )

            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    unit_name = parts[0]
                    if not self._is_system_service(unit_name):
                        disabled_units.append((unit_name, "timer"))

        except Exception as e:
            logger.error(f"Failed to list systemd units: {e}")

        return disabled_units

    def _is_system_service(self, unit_name: str) -> bool:
        """Check if unit is a core system service that should stay disabled."""
        system_patterns = [
            "systemd-",
            "getty@",
            "serial-getty@",
            "console-",
            "emergency",
            "rescue",
            "multi-user",
            "graphical",
            "reboot",
            "poweroff",
            "halt",
            "kexec",
            "ctrl-alt-del",
            "syslog",
            "dbus-",
            "udev",
            "plymouth",
            "display-manager",
            "autovt@",
            "container-",
            "user@",
            "debug-",
        ]

        unit_lower = unit_name.lower()
        for pattern in system_patterns:
            if pattern in unit_lower:
                return True

        return False


class DeadLetterMonitor:
    """Monitor dead letter queue for failed intent routing."""

    def __init__(self, dlq_path: Path = Path.home() / ".kloros" / "failed_signals.jsonl",
                 check_interval_s: int = 60):
        """
        Args:
            dlq_path: Path to dead letter queue file
            check_interval_s: How often to check DLQ for new entries
        """
        self.dlq_path = Path(dlq_path)
        self.check_interval_s = check_interval_s
        self._last_check_size = 0
        self._startup_complete = False

    def stream(self) -> Iterator[Event]:
        """
        Yield events when dead letter queue grows.

        Detects intent routing failures and generates investigation events.
        On first iteration, processes any existing dead letters from startup.
        """
        while True:
            try:
                if not self.dlq_path.exists():
                    time.sleep(self.check_interval_s)
                    continue

                current_size = self.dlq_path.stat().st_size

                if not self._startup_complete:
                    if current_size > 0:
                        count = len([line for line in open(self.dlq_path, 'r').readlines() if line.strip()])
                        yield Event(
                            source="dead_letter_monitor",
                            type="error_critical",
                            ts=time.time(),
                            data={"message": f"Found {count} historical dead letters on startup"}
                        )

                    self._last_check_size = current_size
                    self._startup_complete = True
                    time.sleep(self.check_interval_s)
                    continue

                if current_size > self._last_check_size:
                    with open(self.dlq_path, 'r') as f:
                        f.seek(self._last_check_size)
                        new_entries = f.read()

                    new_count = len([line for line in new_entries.split('\n') if line.strip()])

                    if new_count > 0:
                        last_entry = {}
                        for line in reversed(new_entries.split('\n')):
                            if line.strip():
                                try:
                                    last_entry = json.loads(line)
                                    break
                                except:
                                    pass

                        error_msg = last_entry.get('error', 'Unknown error')

                        yield Event(
                            source="dead_letter_monitor",
                            type="error_critical",
                            ts=time.time(),
                            data={
                                "message": f"Intent routing failures detected: {new_count} new dead letters. Last error: {error_msg}",
                                "unit": "kloros-intent-router.service",
                                "dead_letter_count": new_count,
                                "last_error": error_msg
                            }
                        )

                    self._last_check_size = current_size

            except Exception as e:
                logger.warning(f"Dead letter monitor error: {e}")

            time.sleep(self.check_interval_s)


class MetricsSource:
    """Scrape Prometheus metrics periodically."""

    def __init__(self, endpoint: str = "http://localhost:9090/metrics", interval_s: int = 30):
        """
        Args:
            endpoint: Prometheus scrape endpoint
            interval_s: Scrape interval in seconds
        """
        self.endpoint = endpoint
        self.interval_s = interval_s

    def stream(self) -> Iterator[Event]:
        """
        Yield events from metrics scraping.

        Scrapes every interval_s seconds and emits events for threshold breaches.
        """
        # Skip if metrics scraping disabled
        if self.interval_s <= 0:
            logger.info("Metrics scraping disabled (interval_s <= 0), MetricsSource idle")
            while True:
                time.sleep(3600)  # Sleep indefinitely

        while True:
            try:
                metrics = self._scrape()

                # Check thresholds
                events = self._check_thresholds(metrics)

                for event in events:
                    yield event

            except Exception as e:
                logger.warning(f"Metrics scrape error: {e}")

            time.sleep(self.interval_s)

    def _scrape(self) -> Dict[str, float]:
        """Scrape metrics endpoint and parse values."""
        try:
            import requests
            resp = requests.get(self.endpoint, timeout=5)
            resp.raise_for_status()

            metrics = {}
            for line in resp.text.splitlines():
                if line.startswith("#") or not line.strip():
                    continue

                # Parse: metric_name{labels} value
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].split("{")[0]
                    try:
                        value = float(parts[1])
                        metrics[name] = value
                    except ValueError:
                        pass

            return metrics

        except Exception as e:
            logger.warning(f"Metrics scrape error: {e}")
            return {}

    def _check_thresholds(self, metrics: Dict[str, float]) -> list[Event]:
        """Check metrics against thresholds and generate events."""
        events = []

        # Lock contention threshold
        lock_contention = metrics.get("kloros_orchestrator_lock_contention_total", 0)
        if lock_contention > 10:  # >10 contentions
            events.append(Event(
                source="metrics",
                type="lock_contention_high",
                ts=time.time(),
                data={"metric": "lock_contention", "value": lock_contention}
            ))

        # PHASE duration threshold
        phase_duration = metrics.get("kloros_phase_duration_seconds", 0)
        if phase_duration > 7200:  # >2 hours
            events.append(Event(
                source="metrics",
                type="phase_duration_high",
                ts=time.time(),
                data={"metric": "phase_duration", "value": phase_duration}
            ))

        return events
