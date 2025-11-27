"""Configuration management for KLoROS."""
import os
import yaml
from pathlib import Path
from typing import Dict, Any


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load KLoROS configuration from YAML.

    Args:
        config_path: Path to config file (default: src/config/kloros.yaml)

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        # Default to src/config/kloros.yaml
        config_path = Path(__file__).parent / "kloros.yaml"

    config_path = Path(config_path).expanduser()

    if not config_path.exists():
        # Return sensible defaults if config doesn't exist
        return {
            "modes": {
                "standard": {
                    "ace": True,
                    "agentflow": True,
                    "budgets": {"latency_ms": 5000, "tool_calls": 4, "tokens": 3500}
                }
            },
            "agentflow": {
                "reward_weights": {"cost": 0.02, "safety": 1.0, "verifier_agree": 0.3}
            },
            "ace": {
                "k_retrieve": 12,
                "max_bullets_per_domain": 24,
                "min_evidence_score": 0.6
            },
            "chroma": {
                "persist_dir": "~/.kloros/chroma_data",
                "embedder": "BAAI/bge-small-en-v1.5"
            }
        }

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Expand paths
    if "chroma" in config and "persist_dir" in config["chroma"]:
        config["chroma"]["persist_dir"] = os.path.expanduser(config["chroma"]["persist_dir"])

    return config


def get_mode_config(mode: str = "standard") -> Dict[str, Any]:
    """Get configuration for a specific cognitive mode.

    Args:
        mode: Cognitive mode (light/standard/thunderdome)

    Returns:
        Mode configuration
    """
    config = load_config()
    return config.get("modes", {}).get(mode, config.get("modes", {}).get("standard", {}))
