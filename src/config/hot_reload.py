#!/usr/bin/env python3
"""
Config Hot-Reload - Watches .kloros_env and reloads config dynamically

Purpose:
    Enable zero-downtime config updates from D-REAM winner deployments
    by watching .kloros_env and updating running processes when it changes

Architecture:
    - Uses inotify to watch .kloros_env for modifications
    - Parses env file and updates os.environ atomically
    - Broadcasts reload events to registered callbacks
    - Thread-safe with lock protection

Integration:
    - Import and start in main service initialization
    - Register reload callbacks for components that need notification
    - Winner deployer can trigger immediate reload after deployment

Example:
    from src.config.hot_reload import ConfigReloader

    reloader = ConfigReloader()
    reloader.register_callback(my_component.on_config_reload)
    reloader.start()
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Set, Callable, Optional, Any
from datetime import datetime

try:
    import inotify_simple
    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False
    logging.warning("inotify_simple not available, hot-reload disabled")

logger = logging.getLogger(__name__)


class ConfigReloader:
    """
    Watches .kloros_env and reloads config when it changes.

    Thread-safe with callback support for components that need reload notifications.
    """

    def __init__(
        self,
        env_file: Path = Path("/home/kloros/.kloros_env"),
        debounce_ms: int = 500
    ):
        """
        Initialize config reloader.

        Args:
            env_file: Path to .kloros_env file
            debounce_ms: Debounce period to avoid rapid reloads
        """
        self.env_file = env_file
        self.debounce_ms = debounce_ms

        self._lock = threading.RLock()
        self._callbacks: Set[Callable[[Dict[str, str], Dict[str, str]], None]] = set()
        self._current_config: Dict[str, str] = {}
        self._last_reload_time = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None

        if not INOTIFY_AVAILABLE:
            logger.warning("[hot_reload] inotify_simple not available, hot-reload disabled")

    def register_callback(self, callback: Callable[[Dict[str, str], Dict[str, str]], None]):
        """
        Register a callback to be notified on config reload.

        Callback signature: callback(old_config: Dict, new_config: Dict) -> None

        Args:
            callback: Function to call when config reloads
        """
        with self._lock:
            self._callbacks.add(callback)
            logger.info(f"[hot_reload] Registered callback: {callback.__name__}")

    def unregister_callback(self, callback: Callable):
        """Unregister a reload callback."""
        with self._lock:
            self._callbacks.discard(callback)

    def start(self):
        """Start watching .kloros_env for changes."""
        if not INOTIFY_AVAILABLE:
            logger.warning("[hot_reload] Cannot start: inotify_simple not available")
            return

        if self._running:
            logger.warning("[hot_reload] Already running")
            return

        if not self.env_file.exists():
            logger.warning(f"[hot_reload] Config file not found: {self.env_file}")
            self.env_file.touch()

        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop,
            name="config-hot-reload",
            daemon=True
        )
        self._thread.start()

        logger.info(f"[hot_reload] Started watching {self.env_file}")

        # Initial load
        self._reload_config()

    def stop(self):
        """Stop watching for changes."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[hot_reload] Stopped")

    def _watch_loop(self):
        """Main inotify watch loop (runs in background thread)."""
        try:
            inotify = inotify_simple.INotify()
            watch_flags = (
                inotify_simple.flags.MODIFY |
                inotify_simple.flags.CLOSE_WRITE |
                inotify_simple.flags.MOVED_TO
            )

            wd = inotify.add_watch(str(self.env_file.parent), watch_flags)
            logger.info(f"[hot_reload] Watching {self.env_file.parent} for changes to {self.env_file.name}")

            while self._running:
                events = inotify.read(timeout=1000)

                for event in events:
                    if event.name == self.env_file.name:
                        logger.info(f"[hot_reload] Detected change in {self.env_file.name}")

                        # Debounce to avoid rapid successive reloads
                        now = time.time()
                        if (now - self._last_reload_time) * 1000 < self.debounce_ms:
                            logger.debug("[hot_reload] Debouncing reload")
                            continue

                        self._reload_config()
                        self._last_reload_time = now

        except Exception as e:
            logger.error(f"[hot_reload] Watch loop error: {e}", exc_info=True)
        finally:
            logger.info("[hot_reload] Watch loop exited")

    def _reload_config(self):
        """Reload config from .kloros_env and update os.environ."""
        try:
            if not self.env_file.exists():
                logger.warning(f"[hot_reload] Config file not found: {self.env_file}")
                return

            with self._lock:
                old_config = self._current_config.copy()
                new_config = self._parse_env_file()

                if new_config == old_config:
                    logger.debug("[hot_reload] No config changes detected")
                    return

                # Update os.environ with new values
                changes = {}
                for key, new_value in new_config.items():
                    old_value = old_config.get(key)
                    if old_value != new_value:
                        os.environ[key] = new_value
                        changes[key] = {"old": old_value, "new": new_value}

                # Track removed keys
                for key in old_config:
                    if key not in new_config:
                        if key in os.environ:
                            del os.environ[key]
                        changes[key] = {"old": old_config[key], "new": None}

                self._current_config = new_config

                if changes:
                    logger.info(f"[hot_reload] Reloaded config with {len(changes)} changes")
                    for key, change in changes.items():
                        logger.info(f"[hot_reload]   {key}: {change['old']} → {change['new']}")

                    # Notify callbacks
                    self._notify_callbacks(old_config, new_config)
                else:
                    logger.debug("[hot_reload] Config reloaded, no changes")

        except Exception as e:
            logger.error(f"[hot_reload] Failed to reload config: {e}", exc_info=True)

    def _parse_env_file(self) -> Dict[str, str]:
        """
        Parse .kloros_env file into a dict.

        Returns:
            Dict of key=value pairs
        """
        config = {}

        try:
            with open(self.env_file, 'r') as f:
                for line in f:
                    line = line.strip()

                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue

                    # Parse key=value
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]

                        config[key] = value

        except Exception as e:
            logger.error(f"[hot_reload] Failed to parse env file: {e}")

        return config

    def _notify_callbacks(self, old_config: Dict[str, str], new_config: Dict[str, str]):
        """Notify all registered callbacks of config change."""
        with self._lock:
            for callback in self._callbacks:
                try:
                    callback(old_config, new_config)
                except Exception as e:
                    logger.error(f"[hot_reload] Callback {callback.__name__} failed: {e}", exc_info=True)

    def force_reload(self):
        """Force immediate config reload (useful for testing or manual triggers)."""
        logger.info("[hot_reload] Force reload triggered")
        self._reload_config()

    def get_current_config(self) -> Dict[str, str]:
        """Get current loaded config."""
        with self._lock:
            return self._current_config.copy()


# Singleton instance
_reloader_instance: Optional[ConfigReloader] = None


def get_config_reloader() -> ConfigReloader:
    """Get singleton config reloader instance."""
    global _reloader_instance
    if _reloader_instance is None:
        _reloader_instance = ConfigReloader()
    return _reloader_instance


def start_hot_reload():
    """Start config hot-reload (call from service initialization)."""
    reloader = get_config_reloader()
    reloader.start()
    return reloader


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    print("=== Config Hot-Reload Self-Test ===\n")

    def test_callback(old_config, new_config):
        print(f"\n[CALLBACK] Config changed!")
        changes = set(new_config.keys()) | set(old_config.keys())
        for key in changes:
            old = old_config.get(key)
            new = new_config.get(key)
            if old != new:
                print(f"  {key}: {old} → {new}")

    reloader = ConfigReloader()
    reloader.register_callback(test_callback)
    reloader.start()

    print(f"\nWatching: {reloader.env_file}")
    print("Current config loaded:")
    for key, value in sorted(reloader.get_current_config().items()):
        print(f"  {key}={value}")

    print("\n✅ Hot-reload started. Modify .kloros_env to see changes...")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        reloader.stop()
