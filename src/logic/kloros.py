"""Decision helpers and operations logging for KLoROS."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

OPS_LOG_PATH = Path.home() / ".kloros" / "ops.log"


def _ensure_log_path() -> None:
    OPS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _json_ready(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(v) for v in value]
    return str(value)


def log_event(event_type: str, **fields: Any) -> None:
    """Append a machine-readable event to ops.log."""
    _ensure_log_path()
    payload: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event": event_type,
    }
    for key, value in fields.items():
        payload[str(key)] = _json_ready(value)
    with OPS_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def should_prioritize(user_id: str, task: Mapping[str, Any] | None) -> bool:
    """Return True when an operator task should preempt lower priority work."""
    if task is None:
        log_event("priority_eval", user=user_id, decision=False, reason="no_task")
        return False

    task_kind = str(task.get("kind", "")).lower()
    interactive = task_kind in {"interactive", "foreground"} or bool(task.get("interactive"))
    priority = str(task.get("priority", "")).lower()
    urgent = priority in {"high", "urgent", "critical"}
    decision = interactive or urgent
    log_event(
        "priority_eval",
        user=user_id,
        task=task.get("name") or task_kind or "unknown",
        interactive=interactive,
        urgent=urgent,
        decision=decision,
    )
    return decision


def _option_risk(option: Mapping[str, Any]) -> float:
    for key in ("risk", "risk_score", "exposure"):
        if key in option:
            try:
                return float(option[key])
            except (TypeError, ValueError):
                continue
    return 1.0


def protective_choice(
    options: Sequence[Mapping[str, Any]],
    user: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Select the safest option for the operator and log the decision."""
    if not options:
        raise ValueError("protective_choice requires at least one option")

    safest = min(options, key=_option_risk)
    log_event(
        "protective_choice",
        user=user or {},
        chosen=safest.get("name") or safest,
        risk=_option_risk(safest),
    )
    return safest


__all__ = ["log_event", "protective_choice", "should_prioritize", "OPS_LOG_PATH"]
