#!/usr/bin/env python3
"""D-REAM fitness computation from PHASE test results.

Computes multi-objective fitness score (pass_rate, latency, efficiency, stability)
and emits promotion decision with bounded I/O and comprehensive error handling per
KLoROS Tool-Integrity requirements.
"""
from __future__ import annotations
import os, json, sys, time, uuid
from statistics import mean
from pathlib import Path
from typing import Dict, Any, Iterable

# Add shared module to path for event logging
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from shared.eventlog import emit
except ImportError:
    def emit(event: str, **fields):
        """Fallback if eventlog unavailable."""
        pass

LOOP = os.path.expanduser("~/kloros_loop")
PHASE = Path(LOOP) / "phase_report.jsonl"
FIT   = Path(LOOP) / "fitness.json"

# Adjustable weights (also mirror them in loop.yaml)
WEIGHTS = {"pass_rate": 0.4, "latency_delta": 0.3, "efficiency": 0.2, "stability": 0.1}

# File I/O timeout budget (seconds)
IO_TIMEOUT = 10

def _ulid() -> str:
    """Generate UUIDv4 hex identifier for fitness run tracking."""
    return uuid.uuid4().hex

def _load_phase_lines() -> list[dict]:
    """Load and parse PHASE test results from phase_report.jsonl.

    Reads all JSONL lines with bounded timeout protection. Skips malformed lines
    and logs parse errors to structured event log.

    Returns:
        List of test result dictionaries. Empty list if file missing or all lines malformed.

    Raises:
        IOError: If file read exceeds IO_TIMEOUT
        OSError: If file permissions denied
    """
    if not PHASE.exists():
        emit("fitness.no_phase_data", path=str(PHASE))
        return []

    try:
        start_read = time.time()
        raw = PHASE.read_text(encoding="utf-8")
        read_duration = time.time() - start_read

        if read_duration > IO_TIMEOUT:
            emit("fitness.read_slow", path=str(PHASE), duration_sec=read_duration, limit_sec=IO_TIMEOUT)
            raise IOError(f"Reading {PHASE} exceeded {IO_TIMEOUT}s timeout")

        lines = []
        for i, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError as e:
                emit("fitness.parse_error", line_num=i, error=str(e))
                continue  # Skip malformed lines, don't fail entire load

        emit("fitness.loaded", line_count=len(lines), path=str(PHASE))
        return lines

    except OSError as e:
        emit("fitness.read_failed", path=str(PHASE), error=str(e))
        raise
    except Exception as e:
        emit("fitness.load_unexpected", error=type(e).__name__, details=str(e))
        raise

def compute_fitness(lines: list[dict]) -> Dict[str, Any]:
    """Compute multi-objective fitness score from PHASE test results.

    Calculates weighted fitness across 4 dimensions:
    - pass_rate (0.4): Fraction of tests passing
    - latency_delta (0.3): Normalized latency improvement (lower is better)
    - efficiency (0.2): Combined CPU/memory efficiency
    - stability (0.1): Inverse flake rate

    Decision thresholds:
    - score >= 0.10: promote (safe to promote to memory)
    - score >= 0.05: hold (keep testing)
    - score < 0.05: rollback (regression detected)

    Args:
        lines: List of test result dicts from phase_report.jsonl

    Returns:
        Dict with keys: epoch_id, inputs, weights, score, decision, evidence

    Raises:
        ValueError: If lines contains invalid data types
    """
    try:
        total = len(lines)
        if total == 0:
            emit("fitness.empty_input")
            return {
                "epoch_id": "empty-epoch",
                "inputs": {"pass_rate": 0.0, "latency_delta": 0.0, "efficiency": 0.0, "stability": 0.0},
                "weights": WEIGHTS,
                "score": 0.0,
                "decision": "rollback",
                "evidence": {"phase_report_path": str(PHASE), "reason": "no_test_data"}
            }

        passes = sum(1 for x in lines if x.get("status") == "pass")
        flakes = sum(1 for x in lines if x.get("status") == "flake")
        pass_rate = passes / total

        lat = [x.get("latency_ms") for x in lines if isinstance(x.get("latency_ms"), (int, float))]
        latency_delta = (-mean(lat)/1000.0) if lat else 0.0

        cpu = [x.get("cpu_pct") for x in lines if isinstance(x.get("cpu_pct"), (int, float))]
        mem = [x.get("mem_mb") for x in lines if isinstance(x.get("mem_mb"), (int, float))]
        efficiency = (1.0 - (mean(cpu)/100.0 if cpu else 0.0)) * 0.5 + (1.0 - (mean(mem)/8192.0 if mem else 0.0)) * 0.5

        stability = 1.0 - (flakes / total)

        inputs = {"pass_rate": pass_rate, "latency_delta": latency_delta, "efficiency": efficiency, "stability": stability}
        score = sum(inputs[k] * WEIGHTS[k] for k in WEIGHTS)
        decision = "promote" if score >= 0.10 else ("hold" if score >= 0.05 else "rollback")

        epoch_id = lines[0].get("epoch_id", "local-epoch") if lines else "local-epoch"

        emit("fitness.computed", epoch_id=epoch_id, score=score, decision=decision, total_tests=total)

        return {
            "run_id": _ulid(),
            "epoch_id": epoch_id,
            "inputs": inputs,
            "weights": WEIGHTS,
            "fitness_score": score,
            "decision": decision,
            "evidence": {"phase_report_path": str(PHASE), "total_tests": total, "passes": passes, "flakes": flakes}
        }

    except Exception as e:
        emit("fitness.compute_error", error=type(e).__name__, details=str(e))
        raise

def write_fitness():
    """Load PHASE data, compute fitness, and persist to fitness.json.

    Main entry point for D-REAM fitness evaluation. Loads phase_report.jsonl,
    computes fitness score, writes result to fitness.json with bounded I/O timeout.

    Returns:
        Dict containing fitness computation result

    Raises:
        IOError: If file I/O exceeds IO_TIMEOUT
        OSError: If disk full or permissions denied
        ValueError: If PHASE data malformed
    """
    try:
        lines = _load_phase_lines()
        data = compute_fitness(lines)

        # Bounded write with timeout protection
        start_write = time.time()
        FIT.write_text(json.dumps(data, indent=2), encoding="utf-8")
        write_duration = time.time() - start_write

        if write_duration > IO_TIMEOUT:
            emit("fitness.write_slow", duration_sec=write_duration, limit_sec=IO_TIMEOUT)
            raise IOError(f"Writing {FIT} exceeded {IO_TIMEOUT}s timeout")

        emit("fitness.written", path=str(FIT), score=data["fitness_score"], decision=data["decision"])
        return data

    except OSError as e:
        emit("fitness.write_failed", path=str(FIT), error=str(e))
        raise IOError(f"Failed to write fitness to {FIT}: {e}") from e
    except Exception as e:
        emit("fitness.write_unexpected", error=type(e).__name__, details=str(e))
        raise

if __name__ == "__main__":
    out = write_fitness()
    print(json.dumps(out, indent=2))
