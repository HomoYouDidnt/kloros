"""Bounded CPU workload: integer math & SHA-like mixing for a fixed duration."""
from __future__ import annotations
import time, math, hashlib, os
from .logging_shim import log_event

def bounded_cpu_load(seconds: float = 5.0, parallelism: int = max(1, os.cpu_count()//2)) -> dict:
    import concurrent.futures as cf
    end = time.time() + seconds
    def work(seed: int) -> int:
        i = 0
        h = hashlib.sha256(str(seed).encode()).digest()
        total = 0
        while time.time() < end:
            i += 1
            total ^= int.from_bytes(h, 'little') ^ i
            # simple mix
            total = (total * 2654435761) & 0xFFFFFFFF
        return total
    results = []
    with cf.ThreadPoolExecutor(max_workers=parallelism) as ex:
        futs = [ex.submit(work, s) for s in range(parallelism)]
        for f in futs:
            results.append(f.result())
    metrics = {"kind": "cpu_bounded", "seconds": seconds, "parallelism": parallelism, "results": len(results)}
    log_event("dream.cpu_bounded", **metrics)
    return metrics
