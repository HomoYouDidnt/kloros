#!/usr/bin/env python3
"""KLoROS memory promotion system implementing loop.yaml promotion rule.

Evaluates fitness.json and creates memory promotion markers when fitness score
exceeds previous best, with bounded I/O and comprehensive error handling per
KLoROS Tool-Integrity requirements.
"""
from __future__ import annotations
import os, json, time, sys
from pathlib import Path
from typing import Optional, Dict, Any

# Add shared module to path for event logging
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from shared.eventlog import emit
except ImportError:
    def emit(event: str, **fields):
        """Fallback if eventlog unavailable."""
        pass

LOOP = os.path.expanduser("~/kloros_loop")
FIT  = Path(LOOP) / "fitness.json"
MEM  = Path(LOOP) / "memory"
MEM.mkdir(parents=True, exist_ok=True)

# File I/O timeout budget (seconds)
IO_TIMEOUT = 5

def _load_fitness() -> Optional[Dict[str, Any]]:
    """Load fitness computation result from fitness.json.

    Returns:
        Dict containing fitness data, or None if file missing

    Raises:
        IOError: If file read exceeds IO_TIMEOUT
        json.JSONDecodeError: If file contains invalid JSON
    """
    if not FIT.exists():
        emit("memory.no_fitness", path=str(FIT))
        return None

    try:
        start_read = time.time()
        data = json.loads(FIT.read_text(encoding="utf-8"))
        read_duration = time.time() - start_read

        if read_duration > IO_TIMEOUT:
            emit("memory.read_slow", path=str(FIT), duration_sec=read_duration, limit_sec=IO_TIMEOUT)
            raise IOError(f"Reading {FIT} exceeded {IO_TIMEOUT}s timeout")

        return data

    except json.JSONDecodeError as e:
        emit("memory.fitness_parse_error", path=str(FIT), error=str(e))
        raise
    except OSError as e:
        emit("memory.fitness_read_failed", path=str(FIT), error=str(e))
        raise
    except Exception as e:
        emit("memory.fitness_load_unexpected", error=type(e).__name__, details=str(e))
        raise

def _load_prev_best() -> float:
    """Load previous best fitness score from fitness_prev_best.txt.

    Returns:
        Previous best score as float, or 0.0 if file missing/corrupted

    Raises:
        IOError: If file read exceeds IO_TIMEOUT
    """
    prev = Path(LOOP) / "fitness_prev_best.txt"
    if not prev.exists():
        return 0.0

    try:
        start_read = time.time()
        raw = prev.read_text(encoding="utf-8").strip()
        read_duration = time.time() - start_read

        if read_duration > IO_TIMEOUT:
            emit("memory.prev_best_slow", duration_sec=read_duration, limit_sec=IO_TIMEOUT)
            raise IOError(f"Reading prev_best exceeded {IO_TIMEOUT}s timeout")

        return float(raw)

    except (ValueError, OSError) as e:
        emit("memory.prev_best_parse_error", error=str(e))
        return 0.0  # Graceful fallback for corrupted file
    except Exception as e:
        emit("memory.prev_best_unexpected", error=type(e).__name__, details=str(e))
        return 0.0

def _save_prev_best(v: float) -> None:
    """Persist new best fitness score to fitness_prev_best.txt.

    Args:
        v: Fitness score to save (6 decimal precision)

    Raises:
        IOError: If file write exceeds IO_TIMEOUT or disk full
    """
    try:
        start_write = time.time()
        (Path(LOOP) / "fitness_prev_best.txt").write_text(f"{v:.6f}", encoding="utf-8")
        write_duration = time.time() - start_write

        if write_duration > IO_TIMEOUT:
            emit("memory.save_best_slow", duration_sec=write_duration, limit_sec=IO_TIMEOUT)
            raise IOError(f"Writing prev_best exceeded {IO_TIMEOUT}s timeout")

    except OSError as e:
        emit("memory.save_best_failed", error=str(e))
        raise IOError(f"Failed to save prev_best: {e}") from e
    except Exception as e:
        emit("memory.save_best_unexpected", error=type(e).__name__, details=str(e))
        raise

def maybe_promote() -> Dict[str, Any]:
    """Evaluate promotion gate per loop.yaml rule: decision=='promote' AND score >= prev_best.

    Creates memory promotion marker file if gate conditions met. Implements the
    KLoROS memory promotion rule with full audit trail and bounded I/O.

    Promotion logic:
    1. Load fitness.json decision and score
    2. Compare to fitness_prev_best.txt
    3. If decision=='promote' AND score >= prev_best:
       - Create timestamped marker in memory/promoted_<epoch>_<timestamp>.txt
       - Update fitness_prev_best.txt
       - Return success with audit trail

    Returns:
        Dict with keys:
        - promoted (bool): True if promotion occurred
        - marker (str): Path to promotion marker file (if promoted)
        - score (float): Current fitness score
        - prev_best (float): Previous best score
        - reason (str): Explanation if not promoted

    Raises:
        IOError: If file I/O exceeds IO_TIMEOUT
        OSError: If disk full or permissions denied
    """
    try:
        fit = _load_fitness()
        if not fit:
            return {"promoted": False, "reason": "no_fitness"}

        decision = fit.get("decision")
        score = float(fit.get("score", 0.0))
        prev_best = _load_prev_best()

        # Apply loop.yaml promotion rule
        if decision == "promote" and score >= prev_best:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            epoch_id = fit.get("epoch_id", "epoch")
            mark = MEM / f"promoted_{epoch_id}_{stamp}.txt"

            # Create promotion marker with bounded write
            start_write = time.time()
            mark.write_text(
                json.dumps({"epoch_id": epoch_id, "score": score, "prev_best": prev_best, "timestamp": stamp}, indent=2),
                encoding="utf-8"
            )
            write_duration = time.time() - start_write

            if write_duration > IO_TIMEOUT:
                emit("memory.marker_slow", duration_sec=write_duration, limit_sec=IO_TIMEOUT)
                raise IOError(f"Writing promotion marker exceeded {IO_TIMEOUT}s timeout")

            _save_prev_best(score)

            emit("memory.promoted", epoch_id=epoch_id, score=score, prev_best=prev_best, marker=str(mark))
            return {"promoted": True, "marker": str(mark), "score": score, "prev_best": prev_best}

        # Gate not met
        reason = f"decision={decision}, score={score:.6f} < prev_best={prev_best:.6f}"
        emit("memory.gate_not_met", decision=decision, score=score, prev_best=prev_best)
        return {"promoted": False, "reason": "gate_not_met", "decision": decision, "score": score, "prev_best": prev_best}

    except Exception as e:
        emit("memory.promote_error", error=type(e).__name__, details=str(e))
        raise

if __name__ == "__main__":
    print(json.dumps(maybe_promote(), indent=2))
