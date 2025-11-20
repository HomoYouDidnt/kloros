"""Safety sandbox for chaos experiments."""

import os
import tempfile
import shutil
from typing import Optional


class Sandbox:
    """Isolates chaos experiments from production environment."""

    def __init__(self, enabled: bool = True, metrics=None, logger=None):
        """Initialize sandbox.

        Args:
            enabled: Whether sandbox is active
            metrics: Optional metrics system
            logger: Optional logger
        """
        self.enabled = enabled
        self.metrics = metrics
        self.logger = logger
        self.tmp: Optional[str] = None
        self._saved_env = {}

    def __enter__(self):
        """Enter sandbox context."""
        if not self.enabled:
            if self.logger:
                self.logger.info("[sandbox] Sandbox disabled - running in production mode!")
            return self

        if self.logger:
            self.logger.info("[sandbox] Entering sandbox mode")

        # Set sandbox flags
        self._save_env("KLR_DREAM_SANDBOX")
        os.environ["KLR_DREAM_SANDBOX"] = "1"

        # Create temporary data directory
        self.tmp = tempfile.mkdtemp(prefix="klr_chaos_")
        self._save_env("KLR_DATA_DIR")
        os.environ["KLR_DATA_DIR"] = self.tmp

        # Redirect outcome logs to sandbox
        self._save_env("KLR_HEAL_OUTCOMES")
        os.environ["KLR_HEAL_OUTCOMES"] = os.path.join(self.tmp, "heal_outcomes.jsonl")

        # Disable external integrations
        self._save_env("KLR_DISABLE_MQTT")
        os.environ["KLR_DISABLE_MQTT"] = "1"

        self._save_env("KLR_DISABLE_HTTP")
        os.environ["KLR_DISABLE_HTTP"] = "1"

        # Reduce noise in logs
        self._save_env("KLR_QUIET_MODE")
        os.environ["KLR_QUIET_MODE"] = "1"

        if self.logger:
            self.logger.info(f"[sandbox] Temp directory: {self.tmp}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit sandbox context and cleanup."""
        if not self.enabled:
            return

        if self.logger:
            self.logger.info("[sandbox] Exiting sandbox mode")

        # Cleanup temp directory
        if self.tmp and os.path.exists(self.tmp):
            try:
                shutil.rmtree(self.tmp, ignore_errors=True)
                if self.logger:
                    self.logger.info(f"[sandbox] Cleaned up {self.tmp}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"[sandbox] Cleanup failed: {e}")

        # Restore environment
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        self._saved_env.clear()

    def _save_env(self, key: str):
        """Save current environment variable value.

        Args:
            key: Environment variable name
        """
        self._saved_env[key] = os.environ.get(key)

    def get_temp_dir(self) -> Optional[str]:
        """Get sandbox temporary directory.

        Returns:
            Path to temp directory or None if sandbox disabled
        """
        return self.tmp

    def is_active(self) -> bool:
        """Check if sandbox is currently active.

        Returns:
            True if sandbox is active
        """
        return self.enabled and self.tmp is not None
