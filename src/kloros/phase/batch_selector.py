"""
Batch Selector - Differentiation & Selection for PHASE testing.

Selects DORMANT zooids for promotion to PROBATION based on:
- Niche pressure (active count)
- Novelty score (phenotype diversity)
"""
import time
import json
import pathlib
import random
import logging
from typing import List, Tuple

from kloros.registry.lifecycle_registry import LifecycleRegistry
from kloros.lifecycle.state_machine import start_probation

logger = logging.getLogger(__name__)

PHASE_QUEUE = pathlib.Path.home() / ".kloros/lineage/phase_queue.jsonl"


def _niche_pressure(reg: dict, niche: str) -> float:
    """
    Calculate niche pressure (0.0-1.0).

    Higher pressure = fewer active zooids = more need for new candidates.
    """
    active = reg.get("niches", {}).get(niche, {}).get("active", [])
    return 1.0 / (1 + len(active))


def _novelty_score(z: dict) -> float:
    """
    Calculate novelty score (0.0-1.0).

    Based on phenotype parameter diversity.
    """
    ph = z.get("phenotype", {})
    return len(ph) * 0.01 + random.random() * 0.05


def enqueue_phase_batches(policy: dict) -> List[Tuple[str, List[str]]]:
    """
    Select DORMANT zooids and enqueue PHASE batches.

    For each niche:
    1. Calculate niche pressure
    2. Score all dormant zooids (pressure + novelty)
    3. Select top N candidates
    4. Move to PROBATION
    5. Enqueue PHASE work

    Args:
        policy: Policy configuration dict

    Returns:
        List of (niche, candidates) tuples
    """
    reg_mgr = LifecycleRegistry()
    reg = reg_mgr.load()
    now = time.time()

    batch_size = int(policy.get("phase_batch_size_per_niche", 6))
    profile = policy.get("phase_batch_profile_id", "QMG-100h-full-traffic-v3")
    duration = int(policy.get("phase_batch_duration_sec", 300))

    emitted = []

    for niche, idx in reg.get("niches", {}).items():
        dorm = idx.get("dormant", [])
        if not dorm:
            logger.debug(f"Niche {niche}: no dormant zooids")
            continue

        pressure = _niche_pressure(reg, niche)
        logger.debug(f"Niche {niche}: pressure={pressure:.3f}, dormant={len(dorm)}")

        scored = []
        for name in dorm:
            z = reg["zooids"][name]
            novelty = _novelty_score(z)
            score = 0.7 * pressure + 0.3 * novelty
            scored.append((name, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        picks = [n for n, _ in scored[:batch_size]]

        if not picks:
            continue

        batch_id = time.strftime("%Y-%m-%dT%H:%MZ-STANDARD", time.gmtime(now))
        logger.info(f"Niche {niche}: selected {len(picks)} candidates for batch {batch_id}")

        start_probation(reg, picks, batch_id, now)

        PHASE_QUEUE.parent.mkdir(parents=True, exist_ok=True)
        with PHASE_QUEUE.open("a") as f:
            f.write(json.dumps({
                "ts": now,
                "batch_id": batch_id,
                "niche": niche,
                "workload_profile": profile,
                "duration_sec": duration,
                "candidates": picks
            }) + "\n")

        emitted.append((niche, picks))
        logger.info(f"  Candidates: {', '.join(picks[:3])}{'...' if len(picks) > 3 else ''}")

    if emitted:
        reg_mgr.snapshot_then_atomic_write(reg)
        logger.info(f"Enqueued {len(emitted)} batches for PHASE testing")
    else:
        logger.info("No batches to enqueue")

    return emitted
