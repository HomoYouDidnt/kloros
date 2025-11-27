"""Scenario loading and parsing."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Scenario:
    """E2E test scenario definition."""

    name: str
    steps: list[dict]
    speech_contains: list[str]
    metrics: dict
    artifacts: list[dict]
    events: list[dict]  # Phase 3: MQTT event expectations


def load_scenario(path: Path) -> Scenario:
    """
    Load scenario from YAML file.

    Args:
        path: Path to scenario YAML file

    Returns:
        Scenario object
    """
    raw = yaml.safe_load(path.read_text())

    return Scenario(
        name=raw["name"],
        steps=raw["steps"],
        speech_contains=raw.get("expect", {}).get("speech_contains", []),
        metrics=raw.get("expect", {}).get("metrics", {}),
        artifacts=raw.get("expect", {}).get("artifacts", []),
        events=raw.get("expect", {}).get("events", []),
    )
