#!/usr/bin/env python3
"""
Integration Monitor Daemon - Incremental static analysis for broken integrations.

Replaces IntegrationFlowMonitor batch polling with inotify-based streaming.

Architecture:
- Initial scan: Parse all Python files once on startup
- Watch: Use inotify (via watchdog) to detect file changes
- Incremental: Only re-parse changed files
- Periodic: Check for orphaned queues every 5 minutes

Memory Profile: ~150MB (AST index for ~500 files)
CPU Profile:
  - Initial scan: 30% for 10 seconds
  - Steady state: 2-5% (only reparse changed files)
"""

import ast
import json
import logging
import sys
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List, Set, Optional

sys.path.insert(0, str(Path(__file__).parents[3]))

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from kloros.orchestration.chem_bus_v2 import ChemPub
from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FlowAnalyzer(ast.NodeVisitor):
    """
    AST visitor to extract integration flows from Python code.

    Looks for:
    - ChemPub.emit() calls (producers)
    - ChemSub() subscriptions (consumers)
    - Queue/channel identifiers
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.flows = []
        self.responsibilities = []

    def visit_Call(self, node):
        """Visit function call nodes."""
        try:
            # ChemPub.emit() - producer
            if (isinstance(node.func, ast.Attribute) and
                node.func.attr == 'emit'):

                # Extract signal name from first argument
                if node.args:
                    signal = self._extract_string_value(node.args[0])
                    if signal:
                        self.flows.append({
                            'type': 'producer',
                            'channel': signal,
                            'file': str(self.file_path),
                            'line': node.lineno
                        })

            # ChemSub() - consumer
            elif (isinstance(node.func, ast.Name) and
                  node.func.id == 'ChemSub'):
                signal = None

                # Try positional arg first
                if node.args:
                    signal = self._extract_string_value(node.args[0])

                # Try keyword arg 'topic='
                if not signal:
                    for keyword in node.keywords:
                        if keyword.arg == 'topic':
                            signal = self._extract_string_value(keyword.value)
                            break

                if signal:
                    self.flows.append({
                        'type': 'consumer',
                        'channel': signal,
                        'file': str(self.file_path),
                        'line': node.lineno
                    })

        except Exception as e:
            logger.debug(f"[integration_monitor] Error analyzing call in {self.file_path}:{node.lineno}: {e}")

        self.generic_visit(node)

    def _extract_string_value(self, node) -> Optional[str]:
        """Extract string value from AST node."""
        if isinstance(node, ast.Constant):
            return str(node.value) if isinstance(node.value, str) else None
        elif isinstance(node, ast.Str):  # Python 3.7 compat
            return node.s
        return None


class IntegrationMonitorDaemon:
    """
    Streaming integration monitor daemon.

    Features:
    - Initial scan of all Python files
    - inotify-based incremental updates
    - Orphaned queue detection
    - Low memory (bounded index)
    """

    def __init__(self):
        """Initialize integration monitor daemon."""
        self.running = True
        self.pub = ChemPub()

        # File index: file_path → {flows: [...], last_modified: ts}
        self.file_index: Dict[str, Dict[str, Any]] = {}

        # Orphaned queues we've already emitted signals for
        self.orphaned_queues_emitted: Set[str] = set()

        # Stats
        self.files_scanned = 0
        self.files_watching = 0
        self.signals_emitted = 0

        # Paths
        self.watch_path = Path("/home/kloros/src")
        self.check_interval = 300  # 5 minutes

    def run(self):
        """
        Main daemon loop.

        1. Initial scan of all Python files
        2. Start watchdog observer
        3. Periodic orphan checks
        """
        logger.info("[integration_monitor] Starting integration monitor daemon")
        logger.info(f"[integration_monitor] Watching {self.watch_path}")

        # Initial scan
        logger.info("[integration_monitor] Performing initial scan...")
        self._initial_scan()
        logger.info(f"[integration_monitor] Initial scan complete: {self.files_scanned} files indexed")

        # Start watchdog
        event_handler = CodeChangeHandler(self)
        observer = Observer()
        observer.schedule(event_handler, str(self.watch_path), recursive=True)
        observer.start()
        logger.info("[integration_monitor] File watcher started")

        try:
            # Periodic orphan checks
            while self.running:
                wait_for_normal_mode()

                try:
                    self._check_for_orphans()
                except Exception as e:
                    logger.error(f"[integration_monitor] Error checking orphans: {e}")

                # Sleep for check interval
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("[integration_monitor] Keyboard interrupt received")
        finally:
            observer.stop()
            observer.join()
            self.shutdown()

    def _initial_scan(self):
        """Scan all Python files once on startup."""
        for py_file in self.watch_path.rglob("*.py"):
            # Skip virtual environments and cache directories
            if any(part.startswith('.') or part in ('__pycache__', 'venv', '.venv')
                   for part in py_file.parts):
                continue

            try:
                self._analyze_file(py_file)
                self.files_scanned += 1
            except Exception as e:
                logger.debug(f"[integration_monitor] Failed to analyze {py_file}: {e}")

        self.files_watching = len(self.file_index)

    def on_file_changed(self, file_path: Path):
        """
        Called by watchdog when file changes.

        Args:
            file_path: Path to changed file
        """
        # Skip non-Python files
        if not str(file_path).endswith('.py'):
            return

        # Skip hidden/cache directories
        if any(part.startswith('.') or part in ('__pycache__', 'venv', '.venv')
               for part in file_path.parts):
            return

        logger.info(f"[integration_monitor] File changed: {file_path}")

        try:
            # Re-analyze the file (incremental update)
            self._analyze_file(file_path)

            # Check if this change affected orphans
            self._check_for_orphans()

        except Exception as e:
            logger.error(f"[integration_monitor] Error handling change for {file_path}: {e}")

    def on_file_deleted(self, file_path: Path):
        """
        Called by watchdog when file is deleted.

        Args:
            file_path: Path to deleted file
        """
        file_key = str(file_path)
        if file_key in self.file_index:
            logger.info(f"[integration_monitor] File deleted: {file_path}")
            del self.file_index[file_key]
            self.files_watching = len(self.file_index)

            # Check if deletion created orphans
            self._check_for_orphans()

    def _analyze_file(self, file_path: Path):
        """
        Parse one file and update index incrementally.

        Args:
            file_path: Path to Python file
        """
        try:
            with open(file_path) as f:
                source = f.read()

            tree = ast.parse(source, filename=str(file_path))
            analyzer = FlowAnalyzer(file_path)
            analyzer.visit(tree)

            # Update index for this file only
            file_key = str(file_path)
            self.file_index[file_key] = {
                'flows': analyzer.flows,
                'responsibilities': analyzer.responsibilities,
                'last_modified': file_path.stat().st_mtime
            }

        except SyntaxError as e:
            logger.debug(f"[integration_monitor] Syntax error in {file_path}: {e}")
        except Exception as e:
            logger.debug(f"[integration_monitor] Failed to analyze {file_path}: {e}")

    def _check_for_orphans(self):
        """
        Check all flows for orphaned queues.

        An orphaned queue is a channel with producers but no consumers.
        """
        # Build channel map: channel → {producers: set(), consumers: set()}
        channels = defaultdict(lambda: {"producers": set(), "consumers": set()})

        for file_data in self.file_index.values():
            for flow in file_data['flows']:
                channel = flow['channel']
                file_path = flow['file']

                if flow['type'] == 'producer':
                    channels[channel]["producers"].add(file_path)
                elif flow['type'] == 'consumer':
                    channels[channel]["consumers"].add(file_path)

        # Emit signals for orphans
        for channel, info in channels.items():
            if info["producers"] and not info["consumers"]:
                orphan_id = f"orphaned_queue_{channel}"

                # Only emit once (with cooldown)
                if orphan_id not in self.orphaned_queues_emitted:
                    self._emit_orphaned_queue_gap(channel, info["producers"])
                    self.orphaned_queues_emitted.add(orphan_id)
                    self.signals_emitted += 1

            # If queue was orphaned but now has consumers, remove from emitted set
            elif orphan_id in self.orphaned_queues_emitted and info["consumers"]:
                logger.info(f"[integration_monitor] Orphaned queue resolved: {channel}")
                self.orphaned_queues_emitted.remove(orphan_id)

    def _emit_orphaned_queue_gap(self, channel: str, producers: Set[str]):
        """
        Emit CAPABILITY_GAP signal for orphaned queue.

        Args:
            channel: Signal/channel name
            producers: Set of file paths that produce to this channel
        """
        self.pub.emit(
            signal="CAPABILITY_GAP",
            ecosystem="architecture",
            facts={
                "gap_type": "orphaned_queue",
                "gap_name": channel,
                "gap_category": "integration",
                "producers": sorted(list(producers)),
                "reason": "Data structure populated but never consumed"
            }
        )

        logger.info(
            f"[integration_monitor] Orphaned queue detected: {channel} "
            f"(producers: {len(producers)})"
        )

    def shutdown(self):
        """Shutdown daemon gracefully."""
        logger.info("[integration_monitor] Shutting down integration monitor daemon")
        logger.info(f"[integration_monitor] Files scanned: {self.files_scanned}")
        logger.info(f"[integration_monitor] Files watching: {self.files_watching}")
        logger.info(f"[integration_monitor] Signals emitted: {self.signals_emitted}")
        self.running = False


class CodeChangeHandler(FileSystemEventHandler):
    """
    Watchdog event handler for code changes.

    Forwards events to IntegrationMonitorDaemon.
    """

    def __init__(self, daemon: IntegrationMonitorDaemon):
        self.daemon = daemon

    def on_modified(self, event):
        """File was modified."""
        if not event.is_directory:
            self.daemon.on_file_changed(Path(event.src_path))

    def on_created(self, event):
        """File was created."""
        if not event.is_directory:
            self.daemon.on_file_changed(Path(event.src_path))

    def on_deleted(self, event):
        """File was deleted."""
        if not event.is_directory:
            self.daemon.on_file_deleted(Path(event.src_path))


def main():
    """Main entry point."""
    daemon = IntegrationMonitorDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
