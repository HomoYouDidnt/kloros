#!/usr/bin/env python3
"""
Capability Hot-Reload - Watches capabilities.yaml and reloads tools dynamically.

Purpose:
    Enable zero-downtime tool loading when CapabilityIntegrator adds new modules.
    Completes the discovery-to-execution loop with real-time tool availability.

Architecture:
    1. Watches /home/kloros/src/registry/capabilities.yaml with inotify
    2. When file changes, triggers tool reload on registered tool registries
    3. New tools become available immediately without service restart

Integration:
    - Start in orchestrator initialization
    - Register IntrospectionToolRegistry instances for reload
    - CapabilityIntegrator writes capabilities.yaml → triggers reload

Flow:
    Investigation → CapabilityIntegrator → capabilities.yaml modified
    → inotify event → reload_capability_tools() → new tools available
"""

import logging
import threading
import time
from pathlib import Path
from typing import Set, Optional, Callable

try:
    import inotify_simple
    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False
    logging.warning("[capability_hot_reload] inotify_simple not available, hot-reload disabled")

logger = logging.getLogger(__name__)

CAPABILITIES_YAML = Path("/home/kloros/src/registry/capabilities.yaml")


class CapabilityHotReloader:
    """
    Watches capabilities.yaml and triggers tool reload when it changes.

    Thread-safe with support for multiple tool registry callbacks.
    """

    def __init__(
        self,
        capabilities_file: Path = CAPABILITIES_YAML,
        debounce_ms: int = 1000
    ):
        """
        Initialize capability hot-reloader.

        Args:
            capabilities_file: Path to capabilities.yaml
            debounce_ms: Debounce period to avoid rapid reloads (default 1000ms)
        """
        self.capabilities_file = capabilities_file
        self.debounce_ms = debounce_ms

        self._lock = threading.RLock()
        self._reload_callbacks: Set[Callable[[], int]] = set()
        self._last_reload_time = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None

        if not INOTIFY_AVAILABLE:
            logger.warning("[capability_hot_reload] inotify not available, hot-reload disabled")

    def register_callback(self, callback: Callable[[], int]):
        """
        Register a callback to be notified when capabilities.yaml changes.

        Callback signature: callback() -> int (number of tools loaded)

        Typically this would be IntrospectionToolRegistry.reload_capability_tools()

        Args:
            callback: Function to call when capabilities.yaml changes
        """
        with self._lock:
            self._reload_callbacks.add(callback)
            logger.info(f"[capability_hot_reload] Registered callback: {callback.__name__}")

    def unregister_callback(self, callback: Callable):
        """Unregister a reload callback."""
        with self._lock:
            self._reload_callbacks.discard(callback)

    def start(self):
        """Start watching capabilities.yaml for changes."""
        if not INOTIFY_AVAILABLE:
            logger.warning("[capability_hot_reload] Cannot start: inotify_simple not available")
            return

        if self._running:
            logger.warning("[capability_hot_reload] Already running")
            return

        if not self.capabilities_file.exists():
            logger.error(f"[capability_hot_reload] Capabilities file not found: {self.capabilities_file}")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop,
            name="capability-hot-reload",
            daemon=True
        )
        self._thread.start()

        logger.info(f"[capability_hot_reload] Started watching {self.capabilities_file}")

    def stop(self):
        """Stop watching for changes."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[capability_hot_reload] Stopped")

    def _watch_loop(self):
        """Main inotify watch loop (runs in background thread)."""
        try:
            inotify = inotify_simple.INotify()
            watch_flags = (
                inotify_simple.flags.MODIFY |
                inotify_simple.flags.CLOSE_WRITE |
                inotify_simple.flags.MOVED_TO
            )

            # Watch the directory, not the file directly (more reliable)
            wd = inotify.add_watch(str(self.capabilities_file.parent), watch_flags)
            logger.info(
                f"[capability_hot_reload] Watching {self.capabilities_file.parent} "
                f"for changes to {self.capabilities_file.name}"
            )

            while self._running:
                events = inotify.read(timeout=1000)

                for event in events:
                    if event.name == self.capabilities_file.name:
                        logger.info(f"[capability_hot_reload] Detected change in {self.capabilities_file.name}")

                        # Debounce to avoid rapid successive reloads
                        # (CapabilityIntegrator may write file in multiple operations)
                        now = time.time()
                        if (now - self._last_reload_time) * 1000 < self.debounce_ms:
                            logger.debug("[capability_hot_reload] Debouncing reload")
                            continue

                        self._trigger_reload()
                        self._last_reload_time = now

        except Exception as e:
            logger.error(f"[capability_hot_reload] Watch loop error: {e}", exc_info=True)
        finally:
            logger.info("[capability_hot_reload] Watch loop exited")

    def _trigger_reload(self):
        """Trigger reload on all registered callbacks."""
        with self._lock:
            if not self._reload_callbacks:
                logger.warning("[capability_hot_reload] No callbacks registered, reload skipped")
                return

            total_loaded = 0
            for callback in self._reload_callbacks:
                try:
                    loaded = callback()
                    total_loaded += loaded
                    logger.info(f"[capability_hot_reload] Callback {callback.__name__} loaded {loaded} new tools")
                except Exception as e:
                    logger.error(
                        f"[capability_hot_reload] Callback {callback.__name__} failed: {e}",
                        exc_info=True
                    )

            if total_loaded > 0:
                logger.info(f"[capability_hot_reload] ✅ Hot-reload complete: {total_loaded} new tools loaded")
            else:
                logger.debug("[capability_hot_reload] Hot-reload complete: no new tools")

    def force_reload(self):
        """Force immediate reload (useful for testing or manual triggers)."""
        logger.info("[capability_hot_reload] Force reload triggered")
        self._trigger_reload()


# Singleton instance
_reloader_instance: Optional[CapabilityHotReloader] = None


def get_capability_hot_reloader() -> CapabilityHotReloader:
    """Get singleton capability hot-reloader instance."""
    global _reloader_instance
    if _reloader_instance is None:
        _reloader_instance = CapabilityHotReloader()
    return _reloader_instance


def start_capability_hot_reload():
    """Start capability hot-reload (call from service initialization)."""
    reloader = get_capability_hot_reloader()
    reloader.start()
    return reloader


if __name__ == "__main__":
    # Self-test
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    print("=== Capability Hot-Reload Self-Test ===\n")

    def test_callback():
        print("[CALLBACK] capabilities.yaml changed - reloading tools")
        return 0  # Simulate no new tools in test

    reloader = CapabilityHotReloader()
    reloader.register_callback(test_callback)
    reloader.start()

    print(f"\nWatching: {reloader.capabilities_file}")
    print("\n✅ Hot-reload started. Modify capabilities.yaml to see changes...")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        reloader.stop()
