"""Structured logging shim (D-REAM compliant)."""
from __future__ import annotations
import json, os, pathlib, datetime
from typing import Any, Dict

def _resolve_log_path() -> pathlib.Path:
    primary = pathlib.Path("/var/log/kloros/structured.jsonl")
    if primary.parent.exists() and os.access(primary.parent, os.W_OK):
        return primary
    d = pathlib.Path.home() / ".kloros" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "structured.jsonl"

def log_event(event: str, **fields: Any) -> None:
    path = _resolve_log_path()
    rec: Dict[str, Any] = {"ts": datetime.datetime.utcnow().isoformat() + "Z", "event": event}
    rec.update(fields)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
