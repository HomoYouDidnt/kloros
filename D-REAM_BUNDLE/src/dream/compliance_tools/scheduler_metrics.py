"""Kernel scheduler metrics collector (procfs/psi)."""
from __future__ import annotations
from pathlib import Path
from .logging_shim import log_event

def read_proc(path: str) -> str | None:
    p = Path(path)
    try:
        return p.read_text()
    except Exception:
        return None

def collect() -> dict:
    data = {
        "schedstat": read_proc("/proc/schedstat"),
        "psi_cpu": read_proc("/proc/pressure/cpu"),
        "psi_io": read_proc("/proc/pressure/io"),
        "psi_memory": read_proc("/proc/pressure/memory"),
    }
    log_event("dream.scheduler_metrics", have_schedstat=bool(data["schedstat"]))
    return data
