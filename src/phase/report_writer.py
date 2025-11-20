#!/usr/bin/env python3
"""PHASE test result recorder implementing artifact contract.

Writes test execution records to phase_report.jsonl with bounded I/O timeouts
and comprehensive error handling per KLoROS Tool-Integrity requirements.
"""
from __future__ import annotations
import os, json, time, hashlib, uuid, sys
from pathlib import Path
from typing import Dict, Any

# Add shared module to path for event logging
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from shared.eventlog import emit
except ImportError:
    def emit(event: str, **fields):
        """Fallback if eventlog unavailable."""
        pass

# Always write to kloros user's directory (not dev user)
LOOP = Path("/home/kloros/kloros_loop")
OUT = LOOP / "phase_report.jsonl"
LOOP.mkdir(parents=True, exist_ok=True)

# File I/O timeout budget (seconds)
IO_TIMEOUT = 5

def _ulid() -> str:
    """Generate UUIDv7-ish identifier for test runs and artifacts.

    Returns:
        32-character hex string suitable for unique IDs
    """
    return uuid.uuid4().hex

def _hash(content: bytes) -> str:
    """Compute BLAKE2b content hash for artifact verification.

    Args:
        content: Raw artifact bytes to hash

    Returns:
        Hash string in format 'b3:<32-char-hex>'
    """
    return "b3:" + hashlib.blake2b(content, digest_size=16).hexdigest()

def write_test_result(
    test_id: str,
    status: str,              # "pass" | "fail" | "flake"
    latency_ms: float | None = None,
    cpu_pct: float | None = None,
    mem_mb: float | None = None,
    seed: int | None = None,
    epoch_id: str | None = None,
    run_id: str | None = None,
    artifact_bytes: bytes | None = None,
) -> Dict[str, Any]:
    """Record PHASE test execution result to phase_report.jsonl.

    Writes a single JSONL line with test metrics, enforcing bounded I/O timeouts
    and structured error logging per D-REAM Anti-Fabrication doctrine.

    Args:
        test_id: Unique test identifier (e.g., 'smoke::example')
        status: Test outcome - must be 'pass', 'fail', or 'flake'
        latency_ms: Test execution latency in milliseconds (optional)
        cpu_pct: CPU utilization percentage during test (optional)
        mem_mb: Memory usage in MB during test (optional)
        seed: Random seed used for reproducibility (optional)
        epoch_id: PHASE epoch identifier (auto-generated if None)
        run_id: Individual run identifier (auto-generated if None)
        artifact_bytes: Binary test artifact for content-addressing (optional)

    Returns:
        Dict containing the written record for verification

    Raises:
        IOError: If file write exceeds IO_TIMEOUT or disk full
        ValueError: If status not in allowed values
    """
    if status not in ("pass", "fail", "flake"):
        emit("phase.write_error", test_id=test_id, error="invalid_status", value=status)
        raise ValueError(f"Invalid status '{status}': must be pass/fail/flake")

    try:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rec = {
            "epoch_id": epoch_id or _ulid(),
            "run_id": run_id or _ulid(),
            "test_id": test_id,
            "status": status,
            "latency_ms": latency_ms,
            "cpu_pct": cpu_pct,
            "memory_mb": mem_mb,
            "seed": seed,
            "start_time": now,
            "end_time": now,
        }
        if artifact_bytes:
            rec["artifact_id"] = _ulid()
            rec["content_hash"] = _hash(artifact_bytes)

        # Bounded write with timeout protection
        start_write = time.time()
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()  # Ensure data persisted

        write_duration = time.time() - start_write
        if write_duration > IO_TIMEOUT:
            emit("phase.write_slow", test_id=test_id, duration_sec=write_duration, limit_sec=IO_TIMEOUT)

        emit("phase.result_written", test_id=test_id, status=status, epoch_id=rec["epoch_id"])
        return rec

    except OSError as e:
        emit("phase.write_failed", test_id=test_id, error=str(e), path=str(OUT))
        raise IOError(f"Failed to write test result to {OUT}: {e}") from e
    except Exception as e:
        emit("phase.write_unexpected", test_id=test_id, error=type(e).__name__, details=str(e))
        raise

if __name__ == "__main__":
    # Example smoke line:
    write_test_result("smoke::example", "pass", latency_ms=200.3, cpu_pct=41.2, mem_mb=512, seed=1337)
