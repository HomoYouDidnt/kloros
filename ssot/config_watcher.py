#!/usr/bin/env python3
"""Configuration file watcher for hot-reload of SSOT configs."""
import time
import threading
from pathlib import Path
from typing import Dict, Callable
import logging

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watch configuration files and trigger reload on changes."""

    def __init__(self, watch_paths: Dict[str, Path], reload_callback: Callable):
        """
        Initialize config watcher.

        Args:
            watch_paths: Dict of {name: path} to watch
            reload_callback: Function to call when changes detected
        """
        self.watch_paths = watch_paths
        self.reload_callback = reload_callback
        self.mtimes: Dict[str, float] = {}
        self.running = False
        self.thread = None
        self.check_interval = 5.0  # seconds

        # Initialize mtimes
        for name, path in watch_paths.items():
            if path.exists():
                self.mtimes[name] = path.stat().st_mtime
            else:
                self.mtimes[name] = 0

    def start(self):
        """Start the file watcher in a background thread."""
        if self.running:
            logger.warning("[config_watcher] Already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
        logger.info(f"[config_watcher] Started watching {len(self.watch_paths)} config files")

    def stop(self):
        """Stop the file watcher."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("[config_watcher] Stopped")

    def _watch_loop(self):
        """Main watch loop - checks files periodically."""
        while self.running:
            try:
                changed = self._check_for_changes()
                if changed:
                    logger.info(f"[config_watcher] Detected changes in: {changed}")
                    try:
                        self.reload_callback(changed)
                        logger.info("[config_watcher] ✓ Configuration reloaded successfully")
                    except Exception as e:
                        logger.error(f"[config_watcher] ✗ Reload failed: {e}")
                        # Optionally: send alert about failed reload

            except Exception as e:
                logger.error(f"[config_watcher] Error in watch loop: {e}")

            time.sleep(self.check_interval)

    def _check_for_changes(self) -> list[str]:
        """Check if any watched files have changed."""
        changed = []

        for name, path in self.watch_paths.items():
            if not path.exists():
                # File was deleted or doesn't exist
                if self.mtimes[name] > 0:
                    logger.warning(f"[config_watcher] {name} no longer exists")
                    self.mtimes[name] = 0
                    changed.append(name)
                continue

            current_mtime = path.stat().st_mtime
            if current_mtime > self.mtimes[name]:
                changed.append(name)
                self.mtimes[name] = current_mtime

        return changed


# Integration helper for SSOT
def setup_ssot_watcher(ssot_root: Path, reload_callback: Callable) -> ConfigWatcher:
    """
    Set up watcher for SSOT configuration files.

    Args:
        ssot_root: Path to SSOT directory
        reload_callback: Function to call when configs change

    Returns:
        ConfigWatcher instance (already started)
    """
    watch_paths = {
        "models": ssot_root / "models.toml",
        "services": ssot_root / "services.toml",
        "embeddings_lock": ssot_root / "embeddings.lock.json",
    }

    watcher = ConfigWatcher(watch_paths, reload_callback)
    watcher.start()
    return watcher


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def reload_handler(changed_files):
        print(f"Reload triggered for: {changed_files}")

    ssot_root = Path("/home/kloros/ssot")
    watcher = setup_ssot_watcher(ssot_root, reload_handler)

    print("Watching SSOT configs... Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
