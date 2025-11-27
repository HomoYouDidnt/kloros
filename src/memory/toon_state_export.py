"""
TOON State Export Utilities (Tier 3)

Enables system state exports to use TOON format for 50-60% size reduction,
making full state snapshots analyzable within LLM context limits.
"""

from typing import Dict, Any, Optional
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


def export_state_toon(
    state_data: Dict[str, Any],
    output_path: Path,
    use_toon: bool = True,
    include_json: bool = True
) -> Dict[str, int]:
    """
    Export system state with optional TOON compression.

    Args:
        state_data: State dictionary to export
        output_path: Path to write state file
        use_toon: If True, include TOON-compressed version
        include_json: If True, include standard JSON

    Returns:
        {"json_bytes": X, "toon_bytes": Y, "savings_pct": Z}
    """
    metrics = {"json_bytes": 0, "toon_bytes": 0, "savings_pct": 0}

    # Generate JSON version
    json_str = json.dumps(state_data, indent=2)
    metrics["json_bytes"] = len(json_str)

    # Generate TOON version if requested
    toon_str = None
    if use_toon:
        try:
            from src.cognition.mind.memory.toon_utils import to_toon
            toon_str = to_toon(state_data, fallback_json=False)
            metrics["toon_bytes"] = len(toon_str)
            metrics["savings_pct"] = int(100 * (1 - len(toon_str) / len(json_str)))
            logger.info(f"[toon_state] State export: {metrics['json_bytes']} bytes (JSON) → "
                       f"{metrics['toon_bytes']} bytes (TOON), {metrics['savings_pct']}% savings")
        except Exception as e:
            logger.warning(f"[toon_state] TOON export failed: {e}")
            use_toon = False

    # Write export file
    export_data = {}
    if include_json:
        export_data["state_json"] = state_data
    if use_toon and toon_str:
        export_data["state_toon"] = toon_str
        export_data["toon_format"] = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    logger.info(f"[toon_state] Exported state to {output_path}")
    return metrics


def load_state_toon(input_path: Path, prefer_toon: bool = True) -> Dict[str, Any]:
    """
    Load system state, automatically detecting and using TOON if available.

    Args:
        input_path: Path to state file
        prefer_toon: If True, use TOON version when available

    Returns:
        Loaded state dictionary
    """
    with open(input_path, 'r') as f:
        export_data = json.load(f)

    # Try TOON first if preferred and available
    if prefer_toon and export_data.get("toon_format") and "state_toon" in export_data:
        try:
            from src.cognition.mind.memory.toon_utils import from_toon
            state = from_toon(export_data["state_toon"], fallback_json=False)
            logger.info(f"[toon_state] Loaded state from TOON format ({input_path})")
            return state
        except Exception as e:
            logger.warning(f"[toon_state] TOON load failed, using JSON: {e}")

    # Fallback to JSON
    if "state_json" in export_data:
        logger.info(f"[toon_state] Loaded state from JSON format ({input_path})")
        return export_data["state_json"]

    raise ValueError(f"No valid state data found in {input_path}")


def create_compact_snapshot(
    state_data: Dict[str, Any],
    max_depth: int = 3,
    array_limit: int = 10
) -> Dict[str, Any]:
    """
    Create compact state snapshot suitable for LLM analysis.

    Truncates deep nesting and large arrays to fit within context limits.

    Args:
        state_data: Full state dictionary
        max_depth: Maximum nesting depth
        array_limit: Maximum array elements to include

    Returns:
        Compacted state dictionary
    """
    def compact_recursive(obj: Any, depth: int = 0) -> Any:
        if depth >= max_depth:
            return f"<truncated at depth {max_depth}>"

        if isinstance(obj, dict):
            return {k: compact_recursive(v, depth + 1) for k, v in list(obj.items())[:array_limit]}
        elif isinstance(obj, list):
            if len(obj) > array_limit:
                return [compact_recursive(item, depth + 1) for item in obj[:array_limit]] + \
                       [f"<{len(obj) - array_limit} more items>"]
            return [compact_recursive(item, depth + 1) for item in obj]
        return obj

    return compact_recursive(state_data)
