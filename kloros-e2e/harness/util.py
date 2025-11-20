"""Utility functions for E2E harness."""
import tomllib
from pathlib import Path

_cfg = None


def cfg(key: str):
    """Get configuration value from harness.toml."""
    global _cfg
    if _cfg is None:
        toml_path = Path(__file__).parents[1] / "tests" / "harness.toml"
        _cfg = tomllib.loads(toml_path.read_text())
    return _cfg[key]
