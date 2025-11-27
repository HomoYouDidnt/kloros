"""
Observer main loop - streams events, applies rules, emits intents.

The Observer runs continuously in the background, monitoring:
- systemd journal logs (journald)
- filesystem changes (inotify)
- prometheus metrics (scraping)

It processes events through the rule engine and emits intents to
~/.kloros/intents/ for orchestrator consumption.
"""

import os
import sys
import time
import signal
import logging
import threading
from pathlib import Path
from typing import List

from .sources import Event, JournaldSource, InotifySource, MetricsSource, SystemdAuditSource
from .rules import RuleEngine
from .emit import IntentEmitter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.core.common.memory_monitor import create_monitor

logger = logging.getLogger(__name__)


class Observer:
    """
    Main observer process - coordinates event streaming, rule processing, and intent emission.
    """

    def __init__(
        self,
        event_spool_dir: Path = Path.home() / ".kloros" / "events",
        journald_units: List[str] = None,
        watch_paths: List[Path] = None,
        metrics_endpoint: str = "http://localhost:9090/metrics",
        metrics_interval_s: int = 30,
    ):
        """
        Args:
            event_spool_dir: Directory to spool raw events (for debugging/audit)
            journald_units: systemd units to watch (default: ["dream.service", "kloros.service"])
            watch_paths: Filesystem paths to watch (default: promotions, signals)
            metrics_endpoint: Prometheus metrics endpoint
            metrics_interval_s: Metrics scraping interval
        """
        self.event_spool_dir = Path(event_spool_dir)
        self.event_spool_dir.mkdir(parents=True, exist_ok=True)

        # Default units and paths
        if journald_units is None:
            # Monitor all KLoROS services
            journald_units = [
                "dream.service",
                "kloros.service",
                "kloros-capability-integrator.service",
                "kloros-curiosity-core-consumer.service",
                "kloros-curiosity-processor.service",
                "kloros-dream-consumer.service",
                "kloros-introspection.service",
                "kloros-observer.service",
                "kloros-orchestrator-monitor.service",
                "kloros-policy-engine.service",
                "kloros-winner-deployer.service",
                "klr-investigation-consumer.service",
                "klr-ledger-writer.service",
                "klr-semantic-dedup.service",
            ]

        if watch_paths is None:
            watch_paths = [
                Path.home() / "out" / "promotions",
                Path.home() / ".kloros" / "signals",
            ]

        # Initialize components
        self.journald_source = JournaldSource(units=journald_units)
        self.kernel_source = JournaldSource(watch_kernel=True)  # Kernel log monitoring
        self.inotify_source = InotifySource(paths=watch_paths)
        self.metrics_source = MetricsSource(
            endpoint=metrics_endpoint,
            interval_s=metrics_interval_s
        )
        self.systemd_audit_source = SystemdAuditSource(interval_s=86400)  # Audit once per day

        self.rule_engine = RuleEngine(rate_limit_window_s=300)
        self.intent_emitter = IntentEmitter()

        # Shutdown flag
        self._shutdown = threading.Event()

        # Memory monitoring
        self.memory_monitor = create_monitor(
            service_name="kloros_observer",
            warning_mb=256,
            critical_mb=512
        )

        # Statistics
        self.stats = {
            "events_processed": 0,
            "intents_generated": 0,
            "events_rate_limited": 0,
            "start_time": 0,
        }

    def run(self):
        """
        Run the observer main loop.

        Spawns threads for each event source and processes events as they arrive.
        """
        logger.info("Observer starting...")
        self.stats["start_time"] = time.time()

        # Start config hot-reload (enables zero-downtime D-REAM deployments)
        try:
            from src.core.config.hot_reload import start_hot_reload
            start_hot_reload()
            logger.info("Config hot-reload enabled")
        except Exception as e:
            logger.warning(f"Could not start config hot-reload (non-fatal): {e}")

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Spawn source threads
        threads = []

        # Thread 1: journald events
        journald_thread = threading.Thread(
            target=self._stream_source,
            args=(self.journald_source, "journald"),
            daemon=True
        )
        journald_thread.start()
        threads.append(journald_thread)

        # Thread 2: kernel events
        kernel_thread = threading.Thread(
            target=self._stream_source,
            args=(self.kernel_source, "kernel"),
            daemon=True
        )
        kernel_thread.start()
        threads.append(kernel_thread)

        # Thread 3: inotify events
        inotify_thread = threading.Thread(
            target=self._stream_source,
            args=(self.inotify_source, "inotify"),
            daemon=True
        )
        inotify_thread.start()
        threads.append(inotify_thread)

        # Thread 4: metrics events
        metrics_thread = threading.Thread(
            target=self._stream_source,
            args=(self.metrics_source, "metrics"),
            daemon=True
        )
        metrics_thread.start()
        threads.append(metrics_thread)

        # Thread 5: systemd audit
        systemd_audit_thread = threading.Thread(
            target=self._stream_source,
            args=(self.systemd_audit_source, "systemd_audit"),
            daemon=True
        )
        systemd_audit_thread.start()
        threads.append(systemd_audit_thread)


        # Thread 7: periodic housekeeping
        housekeeping_thread = threading.Thread(
            target=self._housekeeping_loop,
            daemon=True
        )
        housekeeping_thread.start()
        threads.append(housekeeping_thread)

        logger.info(f"Observer running with {len(threads)} source threads")

        # Main thread: wait for shutdown
        try:
            while not self._shutdown.is_set():
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")

        finally:
            logger.info("Observer shutting down...")
            self._shutdown.set()

            # Wait for threads to finish (with timeout)
            for thread in threads:
                thread.join(timeout=5)

            self._print_stats()

    def _stream_source(self, source, source_name: str):
        """
        Stream events from a source and process them.

        Args:
            source: Event source instance (JournaldSource, InotifySource, or MetricsSource)
            source_name: Name for logging
        """
        logger.info(f"Source thread started: {source_name}")

        try:
            for event in source.stream():
                if self._shutdown.is_set():
                    break

                # Process event
                self._process_event(event)

        except Exception as e:
            logger.error(f"Source {source_name} failed: {e}", exc_info=True)

        logger.info(f"Source thread stopped: {source_name}")

    def _process_event(self, event: Event):
        """
        Process a single event through the rule engine.

        Args:
            event: Event to process
        """
        self.stats["events_processed"] += 1

        # Optionally spool raw event (for debugging/audit)
        if os.getenv("KLR_OBSERVER_SPOOL_EVENTS") == "1":
            self._spool_event(event)

        # Apply rules
        try:
            intent = self.rule_engine.process(event)

            if intent:
                # Emit intent
                success = self.intent_emitter.emit(intent)
                if success:
                    self.stats["intents_generated"] += 1
                    logger.info(
                        f"Intent generated: {intent.intent_type} "
                        f"(priority={intent.priority})"
                    )

        except Exception as e:
            logger.error(f"Error processing event {event.type}: {e}", exc_info=True)

    def _spool_event(self, event: Event):
        """
        Write raw event to spool directory for debugging/audit.

        Args:
            event: Event to spool
        """
        try:
            import json
            ts = int(time.time() * 1000)
            filename = f"{ts}_{event.source}_{event.type}.json"
            filepath = self.event_spool_dir / filename

            with open(filepath, "w") as f:
                json.dump(event.to_dict(), f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to spool event: {e}")

    def _housekeeping_loop(self):
        """
        Periodic housekeeping tasks.

        - Prune old intents (>24 hours)
        - Prune old spooled events (>7 days)
        - Log statistics
        """
        logger.info("Housekeeping thread started")

        while not self._shutdown.is_set():
            try:
                # Sleep 10 minutes
                self._shutdown.wait(timeout=600)

                if self._shutdown.is_set():
                    break

                # Prune old intents
                self.intent_emitter.prune_old_intents(max_age_hours=24)

                # Prune old spooled events (if spooling enabled)
                if os.getenv("KLR_OBSERVER_SPOOL_EVENTS") == "1":
                    self._prune_old_events(max_age_hours=168)  # 7 days

                # Check memory usage
                mem_status = self.memory_monitor.check_and_log()
                if mem_status['status'] == 'critical':
                    logger.error(f"CRITICAL memory: {mem_status['rss_mb']}MB. Triggering shutdown.")
                    self._shutdown.set()

                # Log stats
                self._log_stats()

            except Exception as e:
                logger.error(f"Housekeeping error: {e}", exc_info=True)

        logger.info("Housekeeping thread stopped")

    def _prune_old_events(self, max_age_hours: int):
        """
        Remove spooled events older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours before pruning
        """
        cutoff = time.time() - (max_age_hours * 3600)
        pruned = 0

        for event_file in self.event_spool_dir.glob("*.json"):
            try:
                # Extract timestamp from filename
                ts_str = event_file.stem.split("_")[0]
                ts = int(ts_str) / 1000

                if ts < cutoff:
                    event_file.unlink()
                    pruned += 1

            except (ValueError, IndexError):
                pass

        if pruned > 0:
            logger.info(f"Pruned {pruned} old spooled events")

    def _log_stats(self):
        """Log observer statistics."""
        uptime = time.time() - self.stats["start_time"]
        uptime_hours = uptime / 3600

        logger.info(
            f"Observer stats: "
            f"uptime={uptime_hours:.1f}h, "
            f"events={self.stats['events_processed']}, "
            f"intents={self.stats['intents_generated']}"
        )

    def _print_stats(self):
        """Print final statistics on shutdown."""
        uptime = time.time() - self.stats["start_time"]
        print("\n" + "=" * 60)
        print("Observer Statistics")
        print("=" * 60)
        print(f"Uptime:            {uptime:.1f}s ({uptime/3600:.2f}h)")
        print(f"Events processed:  {self.stats['events_processed']}")
        print(f"Intents generated: {self.stats['intents_generated']}")
        print("=" * 60)

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._shutdown.set()


def main():
    """CLI entry point for observer."""
    import argparse

    parser = argparse.ArgumentParser(description="KLoROS Observer - Event streaming and intent generation")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    parser.add_argument(
        "--spool-events",
        action="store_true",
        help="Enable event spooling to ~/.kloros/events/ (for debugging)"
    )
    parser.add_argument(
        "--metrics-endpoint",
        default="http://localhost:9090/metrics",
        help="Prometheus metrics endpoint"
    )
    parser.add_argument(
        "--metrics-interval",
        type=int,
        default=30,
        help="Metrics scraping interval in seconds"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Set environment for event spooling
    if args.spool_events:
        os.environ["KLR_OBSERVER_SPOOL_EVENTS"] = "1"

    # Create and run observer
    observer = Observer(
        metrics_endpoint=args.metrics_endpoint,
        metrics_interval_s=args.metrics_interval
    )

    observer.run()


if __name__ == "__main__":
    main()
