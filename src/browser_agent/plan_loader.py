"""Plan loader utility."""
import yaml
import json
import os
from typing import Dict, Any

def load_plan(path: str) -> Dict[str, Any]:
    """Load plan from YAML or JSON file.

    Args:
        path: Path to plan file

    Returns:
        Plan dictionary
    """
    path = os.path.expanduser(path)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Plan file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        if path.endswith(".yaml") or path.endswith(".yml"):
            return yaml.safe_load(f)
        elif path.endswith(".json"):
            return json.load(f)
        else:
            raise ValueError(f"Unsupported file type: {path}")

def save_plan(plan: Dict[str, Any], path: str):
    """Save plan to YAML or JSON file.

    Args:
        plan: Plan dictionary
        path: Output file path
    """
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        if path.endswith(".yaml") or path.endswith(".yml"):
            yaml.safe_dump(plan, f, default_flow_style=False)
        elif path.endswith(".json"):
            json.dump(plan, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported file type: {path}")
