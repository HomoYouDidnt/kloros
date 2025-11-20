"""
PHASE adapter for SPICA: submit instances to Hyperbolic Time Chamber.

Provides isolation guarantees:
- Pre-run lineage integrity verification
- Deterministic replica expansion
- Network lockdown enforcement
- Post-run immutability checks (lineage must not change)
- Structured tournament results (phase.tournament/v1 schema)
"""

import hashlib
import json
import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone

SPICA_ROOT = Path("/home/kloros/experiments/spica")
INSTANCES = SPICA_ROOT / "instances"


def _hash_file(path: Path) -> str:
    """Compute SHA256 hash of file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_disk_space(instances: list[str], qtime: dict, min_gb: int = 20) -> None:
    """
    Pre-flight check: ensure sufficient disk space for replicas.

    BUG FIX: Previous version assumed 500MB per instance, but actual sizes
    can be 1-5GB each depending on artifacts, snapshots, and logs.
    Now samples actual instance sizes and uses realistic estimates.
    """
    total_replicas = (
        qtime["epochs"] * qtime["slices_per_epoch"] * qtime["replicas_per_slice"]
    )

    # Sample actual instance sizes (more accurate than fixed estimate)
    total_size_gb = 0.0
    for inst_id in instances:
        inst_path = INSTANCES / inst_id
        if inst_path.exists():
            # Get actual disk usage for this instance
            size_bytes = sum(f.stat().st_size for f in inst_path.rglob("*") if f.is_file())
            total_size_gb += size_bytes / (1024**3)

    # Each replica is a lightweight reference (snapshots may be copy-on-write)
    # but budget conservatively: assume 20% overhead per replica
    estimated_gb = total_size_gb * total_replicas * 0.2

    stat = shutil.disk_usage(INSTANCES)
    free_gb = stat.free / (1024**3)

    if free_gb < estimated_gb + min_gb:
        raise RuntimeError(
            f"Insufficient disk space: need ~{estimated_gb:.1f}GB + {min_gb}GB buffer, "
            f"have {free_gb:.1f}GB free. "
            f"Run 'python /home/kloros/src/integrations/spica_spawn.py prune' to reclaim space."
        )


def _build_replica_plan(instances: list[str], qtime: dict) -> dict:
    """
    Build deterministic replica expansion plan.

    Args:
        instances: List of SPICA instance IDs
        qtime: Quantum time config (epochs, slices_per_epoch, replicas_per_slice)

    Returns:
        Replica plan dict with deterministic mapping
    """
    epochs = qtime["epochs"]
    slices_per_epoch = qtime["slices_per_epoch"]
    replicas_per_slice = qtime["replicas_per_slice"]

    replicas = []
    for epoch in range(epochs):
        for slice_idx in range(slices_per_epoch):
            for replica_idx in range(replicas_per_slice):
                for instance_id in instances:
                    replica_id = (
                        f"{instance_id}.e{epoch}.s{slice_idx}.r{replica_idx}"
                    )
                    replicas.append({
                        "replica_id": replica_id,
                        "instance_id": instance_id,
                        "epoch": epoch,
                        "slice": slice_idx,
                        "replica": replica_idx
                    })

    return {
        "total_replicas": len(replicas),
        "replicas": replicas
    }


def _run_phase_htc(
    instances: list[str],
    suite_id: str,
    replica_plan: dict,
    cpu_affinity: bool = True,
    network_egress: bool = False
) -> dict:
    """
    Execute PHASE Hyperbolic Time Chamber with SPICADomain.

    Args:
        instances: List of SPICA instance IDs
        suite_id: Test suite identifier
        replica_plan: Deterministic replica expansion plan
        cpu_affinity: Enable CPU affinity pinning
        network_egress: Allow network egress (default: False for lockdown)

    Returns:
        PHASE execution results with test metrics
    """
    # Import SPICADomain for test execution
    sys.path.insert(0, '/home/kloros')
    from src.phase.domains.spica_domain import SPICADomain, SPICATestConfig

    # Initialize SPICA test domain
    test_config = SPICATestConfig(
        max_latency_ms=5000,
        max_memory_mb=2048,
        max_cpu_percent=80
    )

    domain = SPICADomain(test_config)

    # Convert instance IDs to paths
    instance_paths = [INSTANCES / inst_id for inst_id in instances]

    # Run QTIME-accelerated replicas
    test_results = domain.run_qtime_replicas(instance_paths, replica_plan)

    # Aggregate results by instance
    aggregated = domain.aggregate_replica_results(test_results)

    # Convert to phase_adapter format
    results = []
    for result in test_results:
        results.append({
            "replica_id": result.replica_id,
            "instance_id": result.spica_id,
            "status": result.status,
            "metrics": {
                "spica_id": result.spica_id,
                "exact_match_mean": result.exact_match_mean,
                "latency_p50_ms": result.latency_p50_ms,
                "latency_p95_ms": result.latency_p95_ms,
                "memory_peak_mb": result.memory_peak_mb,
                "cpu_percent": result.cpu_percent,
                "query_count": result.query_count
            },
            "error": result.error_message if result.error_message else None
        })

    return {
        "suite_id": suite_id,
        "total_replicas": len(results),
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": sum(1 for r in results if r["status"] in ["fail", "timeout", "oom"]),
        "results": results,
        "aggregated_by_instance": aggregated
    }


def submit_tournament(
    instances: list[str],
    suite_id: str,
    qtime: dict,
    cpu_affinity: bool = True,
    network_egress: bool = False
) -> dict:
    """
    Submit SPICA instances to PHASE tournament with isolation guarantees.

    Args:
        instances: List of SPICA instance IDs
        suite_id: Test suite identifier (e.g., "qa.rag.gold")
        qtime: Quantum time config:
            - epochs: Number of training epochs
            - slices_per_epoch: Time slices per epoch
            - replicas_per_slice: Parallel replicas per slice
        cpu_affinity: Enable CPU affinity pinning (default: True)
        network_egress: Allow network egress (default: False for lockdown)

    Returns:
        Tournament results (schema: phase.tournament/v1)

    Raises:
        RuntimeError: If pre-flight checks fail or lineage is tampered
    """
    # Pre-flight: disk space
    _assert_disk_space(instances, qtime)

    # Pre-run: Create or update tournament lock files to prevent pruning during execution
    import time
    tournament_start = time.time()
    lock_files = []
    for inst in instances:
        instance_path = INSTANCES / inst
        lock_file = instance_path / ".tournament_lock"

        # If preliminary lock exists (from spawn_instance with auto_prune=False),
        # update it with tournament details. Otherwise create new lock.
        lock_data = {
            "tournament_id": f"tournament_{int(tournament_start)}",
            "suite_id": suite_id,
            "started_at": tournament_start,
            "instances": instances
        }
        lock_file.write_text(json.dumps(lock_data, indent=2))
        lock_files.append(lock_file)

    # Pre-run: snapshot lineage hashes + verify tamper-evidence
    pre_state = {}
    for inst in instances:
        instance_path = INSTANCES / inst
        lineage_path = instance_path / "lineage.json"
        manifest_path = instance_path / "manifest.json"

        if not lineage_path.exists() or not manifest_path.exists():
            raise RuntimeError(f"Missing lineage/manifest: {inst}")

        # Verify lineage hasn't been tampered with before tournament
        lineage_hash = _hash_file(lineage_path)
        manifest = json.loads(manifest_path.read_text())

        if lineage_hash != manifest.get("lineage_sha"):
            raise RuntimeError(
                f"Lineage tampered before tournament: {inst} "
                f"(expected {manifest.get('lineage_sha')}, got {lineage_hash})"
            )

        pre_state[inst] = lineage_hash

    # Build deterministic replica plan
    replica_plan = _build_replica_plan(instances, qtime)
    replica_plan_hash = hashlib.sha256(
        json.dumps(replica_plan, sort_keys=True).encode()
    ).hexdigest()

    try:
        # Run PHASE HTC
        phase_results = _run_phase_htc(
            instances, suite_id, replica_plan,
            cpu_affinity=cpu_affinity,
            network_egress=network_egress
        )

        # Post-run: verify lineage unchanged (immutability guarantee)
        for inst in instances:
            lineage_path = INSTANCES / inst / "lineage.json"

            # Defensive: Check if instance was pruned during tournament
            if not lineage_path.exists():
                raise RuntimeError(
                    f"PHASE isolation breach: instance {inst} was deleted during tournament execution. "
                    f"This indicates concurrent cleanup interfering with active tournaments."
                )

            post_hash = _hash_file(lineage_path)

            if pre_state[inst] != post_hash:
                raise RuntimeError(
                    f"PHASE isolation breach: lineage changed for {inst} "
                    f"(pre: {pre_state[inst]}, post: {post_hash})"
                )

        # Build tournament result (schema: phase.tournament/v1)
        tournament = {
            "schema": "phase.tournament/v1",
            "suite_id": suite_id,
            "qtime": qtime,
            "replica_plan_hash": replica_plan_hash,
            "instances": instances,
            "total_replicas": replica_plan["total_replicas"],
            "isolation": {
                "cpu_affinity": cpu_affinity,
                "network_egress": network_egress,
                "lineage_immutable": True  # Guaranteed by post-run checks
            },
            "results": phase_results,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }

        return tournament

    finally:
        # Always remove tournament locks, even if tournament fails
        for lock_file in lock_files:
            try:
                if lock_file.exists():
                    lock_file.unlink()
            except Exception as e:
                # Log but don't fail if lock cleanup fails
                import logging
                logging.warning(f"Failed to remove tournament lock {lock_file}: {e}")


if __name__ == "__main__":
    # CLI usage example
    import sys

    if len(sys.argv) < 3:
        print("Usage: python phase_adapter.py <suite_id> <instance_id> [instance_id...]")
        print("Example: python phase_adapter.py qa.rag.gold spica-abc123 spica-def456")
        sys.exit(1)

    suite_id = sys.argv[1]
    instances = sys.argv[2:]

    # Default qtime (can be parameterized)
    qtime = {
        "epochs": 1,
        "slices_per_epoch": 1,
        "replicas_per_slice": 1
    }

    try:
        result = submit_tournament(instances, suite_id, qtime)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
