"""Passive power/thermal monitor: reads sensors/nvidia-smi if available, bounded duration."""
from __future__ import annotations
import subprocess, time, shutil
from .logging_shim import log_event

def collect(duration_s: int = 10, interval_s: float = 1.0) -> dict:
    samples = []
    end = time.time() + duration_s
    while time.time() < end:
        entry = {}
        if shutil.which("sensors"):
            try:
                entry["sensors"] = subprocess.check_output(["sensors"], text=True, timeout=2)
            except Exception:
                entry["sensors"] = None
        if shutil.which("nvidia-smi"):
            try:
                entry["gpu_power"] = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=power.draw,temperature.gpu", "--format=csv,noheader,nounits"],
                    text=True, timeout=2)
            except Exception:
                entry["gpu_power"] = None
        samples.append(entry)
        time.sleep(interval_s)
    metrics = {"kind": "power_monitor", "duration_s": duration_s, "interval_s": interval_s, "samples": len(samples)}
    log_event("dream.power_monitor", **metrics)
    return metrics
