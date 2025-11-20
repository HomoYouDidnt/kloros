"""
PHASE Consumer Daemon - Execute workload testing for PROBATION zooids.

Tails phase_queue.jsonl and runs synthetic workloads in sandbox.
"""
import json
import time
import pathlib
import subprocess
import os
import logging
import sys

# Add path for maintenance mode
if "/home/kloros/src" not in sys.path:
    sys.path.insert(0, "/home/kloros/src")

from kloros.orchestration.maintenance_mode import wait_for_normal_mode

logger = logging.getLogger(__name__)

PHASE_QUEUE = pathlib.Path.home() / ".kloros/lineage/phase_queue.jsonl"
PHASE_FIT = pathlib.Path.home() / ".kloros/lineage/phase_fitness.jsonl"


def _run_candidate(
    profile: str,
    duration: int,
    candidate: str,
    sandbox_python: str,
    timeout: int
) -> dict:
    """
    Run PHASE workload for a candidate zooid.

    Args:
        profile: Workload profile ID
        duration: Test duration in seconds
        candidate: Zooid name
        sandbox_python: Python interpreter path
        timeout: Subprocess timeout

    Returns:
        Metrics dict with p95_ms, error_rate, throughput_qps, composite
    """
    cmd = [
        sandbox_python,
        "/home/kloros/src/phase/drivers/queue_latency.py",
        "--module", f"/home/kloros/src/zooids/{candidate}.py",
        "--duration", str(duration),
        "--profile", profile
    ]

    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = "/home/kloros/src"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
            env=env
        )
        metrics = json.loads(result.stdout)
        logger.info(f"Candidate {candidate}: composite={metrics.get('composite', 0.0):.3f}")
        return metrics

    except subprocess.TimeoutExpired:
        logger.error(f"Candidate {candidate}: timeout after {timeout}s")
        return {
            "p95_ms": 10_000,
            "error_rate": 1.0,
            "throughput_qps": 0.0,
            "composite": 0.0,
            "error": "timeout"
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Candidate {candidate}: exit code {e.returncode}")
        logger.error(f"  stdout: {e.stdout[:200]}")
        logger.error(f"  stderr: {e.stderr[:200]}")
        return {
            "p95_ms": 10_000,
            "error_rate": 1.0,
            "throughput_qps": 0.0,
            "composite": 0.0,
            "error": f"exit_{e.returncode}"
        }

    except json.JSONDecodeError as e:
        logger.error(f"Candidate {candidate}: invalid JSON output")
        logger.error(f"  stdout: {result.stdout[:200]}")
        return {
            "p95_ms": 10_000,
            "error_rate": 1.0,
            "throughput_qps": 0.0,
            "composite": 0.0,
            "error": "json_decode"
        }

    except Exception as e:
        logger.error(f"Candidate {candidate}: unexpected error: {e}")
        return {
            "p95_ms": 10_000,
            "error_rate": 1.0,
            "throughput_qps": 0.0,
            "composite": 0.0,
            "error": str(e)
        }


def _tail(f):
    """
    Tail a file, yielding new lines as they appear.

    Processes existing lines first, then waits for new ones.

    Args:
        f: Open file handle

    Yields:
        Lines from file (existing and new)
    """
    # Process existing lines first (don't skip to EOF)
    while True:
        line = f.readline()
        if not line:
            time.sleep(0.2)
            continue
        yield line


def run_consumer(policy: dict):
    """
    Run the PHASE consumer daemon.

    Tails phase_queue.jsonl and executes workloads for each batch.

    Args:
        policy: Policy configuration dict
    """
    PHASE_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    PHASE_FIT.parent.mkdir(parents=True, exist_ok=True)

    sandbox_python = policy.get("sandbox_python", "/usr/bin/python3")
    timeout = int(policy.get("sandbox_timeout_sec", 60))

    logger.info("PHASE consumer daemon started")
    logger.info(f"  Queue: {PHASE_QUEUE}")
    logger.info(f"  Fitness: {PHASE_FIT}")
    logger.info(f"  Python: {sandbox_python}")
    logger.info(f"  Timeout: {timeout}s")

    if not PHASE_QUEUE.exists():
        PHASE_QUEUE.touch()
        logger.info(f"Created queue file: {PHASE_QUEUE}")

    with PHASE_QUEUE.open("r") as q:
        for line in _tail(q):
            # Check maintenance mode before processing
            wait_for_normal_mode()

            try:
                job = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in queue: {line[:100]}")
                continue

            batch_id = job.get("batch_id", "unknown")
            niche = job.get("niche", "unknown")
            candidates = job.get("candidates", [])

            logger.info(f"Processing batch {batch_id} ({niche}): {len(candidates)} candidates")

            ts = time.time()
            for cand in candidates:
                logger.info(f"  Testing {cand}...")

                metrics = _run_candidate(
                    job.get("workload_profile", "default"),
                    int(job.get("duration_sec", 300)),
                    cand,
                    sandbox_python,
                    timeout
                )

                row = {
                    "ts": ts,
                    "batch_id": batch_id,
                    "niche": niche,
                    "candidate": cand,
                    "composite_phase_fitness": metrics.get("composite", 0.0),
                    "workload_profile_id": job.get("workload_profile", "default"),
                    "p95_ms": metrics.get("p95_ms", 0.0),
                    "error_rate": metrics.get("error_rate", 0.0),
                    "throughput_qps": metrics.get("throughput_qps", 0.0),
                }

                with PHASE_FIT.open("a") as f:
                    f.write(json.dumps(row) + "\n")

            logger.info(f"Batch {batch_id} complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    from kloros.registry.lifecycle_registry import load_lifecycle_policy
    run_consumer(load_lifecycle_policy())
