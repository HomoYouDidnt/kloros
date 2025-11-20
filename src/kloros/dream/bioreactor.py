"""
Lifecycle-aware Bioreactor - conservative evolutionary updates.

Runs tournaments among ACTIVE defenders, generates DORMANT candidates,
maintains stable polymorphism with no mass replacements.
"""
import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)


def bioreactor_tick(
    reg: dict,
    ecosystem: str,
    niche: str,
    prod_rows: List[dict],
    phase_rows: List[dict],
    now: float,
    *,
    differentiate: Callable[[str, str, int], List[dict]],
    select_winners: Callable[[List[dict], List[dict], List[dict], float, int], List[dict]],
    enqueue_phase_candidate: Callable[[dict], None]
) -> Dict:
    """
    Run one bioreactor tick for a niche.

    Args:
        reg: Registry dict (mutated in-place)
        ecosystem: Ecosystem name
        niche: Niche name
        prod_rows: Production OBSERVATION rows
        phase_rows: PHASE fitness rows
        now: Current timestamp
        differentiate: Callback to generate candidates (niche, ecosystem, m) -> list[candidate dicts]
        select_winners: Callback to select tournament winners (defenders, prod, phase, now, k) -> list[winners]
        enqueue_phase_candidate: Callback to enqueue candidate to PHASE

    Returns:
        Dict with keys: new_candidates, winners, survivors

    Algorithm:
        1. Generate m DORMANT candidates via differentiate()
        2. Add candidates to registry (DORMANT state, genome_hash binding)
        3. Get ACTIVE defenders from niche index
        4. Run tournament via select_winners() to get k winners
        5. Conservative update: keep losers unless should_retire()
        6. Enqueue candidates to PHASE (de-duped by genome_hash)
        7. Update niche index with survivors
    """
    niche_key = niche

    if niche_key not in reg["niches"]:
        reg["niches"][niche_key] = {
            "active": [],
            "probation": [],
            "dormant": [],
            "retired": []
        }

    logger.info(f"Bioreactor tick: ecosystem={ecosystem}, niche={niche}")

    new_candidates = differentiate(niche, ecosystem, 3)
    logger.info(f"Generated {len(new_candidates)} candidates")

    for cand in new_candidates:
        name = cand["name"]
        genome_hash = cand.get("genome_hash")

        if genome_hash and genome_hash in reg["genomes"]:
            existing = reg["genomes"][genome_hash]
            logger.info(f"Skipping duplicate candidate: {name} (genome_hash={genome_hash[:16]}... already bound to {existing})")
            continue

        cand["lifecycle_state"] = "DORMANT"
        cand["entered_ts"] = now
        cand["niche"] = niche
        cand["ecosystem"] = ecosystem

        reg["zooids"][name] = cand

        if genome_hash:
            reg["genomes"][genome_hash] = name

        if name not in reg["niches"][niche_key]["dormant"]:
            reg["niches"][niche_key]["dormant"].append(name)

        logger.info(f"Added DORMANT candidate: {name}")

        phase_entry = {
            "ts": now,
            "candidate": name,
            "genome_hash": genome_hash,
            "workload_profile_id": "QMG-100h-full-traffic-v3",
            "schema_version": "v1"
        }

        try:
            enqueue_phase_candidate(phase_entry)
            logger.info(f"Enqueued {name} to PHASE")
        except Exception as e:
            logger.error(f"Failed to enqueue {name} to PHASE: {e}")

    active_names = reg["niches"][niche_key]["active"]
    active_defenders = [reg["zooids"][n] for n in active_names if n in reg["zooids"]]

    logger.info(f"Running tournament with {len(active_defenders)} ACTIVE defenders")

    if not active_defenders:
        logger.warning("No ACTIVE defenders to run tournament")
        return {
            "new_candidates": len(new_candidates),
            "winners": [],
            "survivors": []
        }

    winners = select_winners(active_defenders, prod_rows, phase_rows, now, 2)
    winner_names = [w["name"] for w in winners]

    logger.info(f"Tournament winners: {winner_names}")

    survivors = set(active_names)

    logger.info(f"Conservative policy: all ACTIVE zooids remain (stable polymorphism)")

    survivor_names = sorted(survivors)
    reg["niches"][niche_key]["active"] = survivor_names

    logger.info(f"Bioreactor tick complete: {len(new_candidates)} candidates, {len(winner_names)} winners, {len(survivor_names)} survivors")

    return {
        "new_candidates": len(new_candidates),
        "winners": winner_names,
        "survivors": survivor_names
    }
