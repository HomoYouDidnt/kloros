# fitness_ledger.py — append-only ledger for zooid fitness tracking
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

LEDGER_PATH = Path.home() / ".kloros/lineage/fitness_ledger.jsonl"

@dataclass
class FitnessRecord:
    ts: float
    incident_id: str
    zooid: str
    niche: str
    participated: bool
    outcome: str  # "success", "failure", "timeout", "error"
    ttr_ms: Optional[float] = None  # time to respond
    composite_fitness: Optional[float] = None

def record_outcome(
    incident_id: str,
    zooid: str,
    niche: str,
    ok: bool,
    ttr_ms: Optional[float] = None,
    composite_fitness: Optional[float] = None
):
    """
    Append outcome to fitness ledger.

    Args:
        incident_id: Unique incident identifier
        zooid: Name of responding zooid
        niche: Ecological niche (e.g., "latency_monitoring")
        ok: True if successful outcome
        ttr_ms: Time to respond in milliseconds
        composite_fitness: Optional composite fitness score
    """
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = FitnessRecord(
        ts=time.time(),
        incident_id=incident_id,
        zooid=zooid,
        niche=niche,
        participated=True,
        outcome="success" if ok else "failure",
        ttr_ms=ttr_ms,
        composite_fitness=composite_fitness
    )

    with LEDGER_PATH.open("a") as f:
        f.write(json.dumps(asdict(record)) + "\n")

def get_recent_fitness(zooid: str, window_s: float = 3600) -> dict:
    """
    Get recent fitness stats for a zooid.

    Returns:
        {
            "success_rate": float,
            "avg_ttr_ms": float,
            "total_incidents": int,
            "avg_fitness": float
        }
    """
    if not LEDGER_PATH.exists():
        return {"success_rate": 0.0, "avg_ttr_ms": 0.0, "total_incidents": 0, "avg_fitness": 0.0}

    cutoff = time.time() - window_s
    successes = 0
    total = 0
    ttrs = []
    fitnesses = []

    with LEDGER_PATH.open("r") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record["zooid"] == zooid and record["ts"] >= cutoff:
                total += 1
                if record["outcome"] == "success":
                    successes += 1
                if record["ttr_ms"]:
                    ttrs.append(record["ttr_ms"])
                if record["composite_fitness"]:
                    fitnesses.append(record["composite_fitness"])

    return {
        "success_rate": successes / total if total > 0 else 0.0,
        "avg_ttr_ms": sum(ttrs) / len(ttrs) if ttrs else 0.0,
        "total_incidents": total,
        "avg_fitness": sum(fitnesses) / len(fitnesses) if fitnesses else 0.0
    }

def compute_niche_pressure(ecosystem: str, niche: str, window_s: float = 3600) -> float:
    """
    Compute ecological pressure for a niche based on recent failures.

    Returns:
        Pressure score 0.0-1.0 (higher = more failures, need more capacity)
    """
    if not LEDGER_PATH.exists():
        return 0.5  # Default moderate pressure

    cutoff = time.time() - window_s
    failures = 0
    total = 0

    with LEDGER_PATH.open("r") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record["niche"] == niche and record["ts"] >= cutoff:
                total += 1
                if record["outcome"] in ("failure", "timeout", "error"):
                    failures += 1

    if total == 0:
        return 0.5

    failure_rate = failures / total

    # High failure rate + high incident count = high pressure
    incident_pressure = min(1.0, total / 100.0)  # Normalize by expected volume

    return (failure_rate * 0.7) + (incident_pressure * 0.3)
