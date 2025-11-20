"""
PHASE Graduator - promotes PROBATION zooids to ACTIVE.

Aggregates PHASE fitness with exponential decay, enforces gates,
starts services with heartbeat verification, rolls back on failure.
"""
import json
import logging
import math
import statistics
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from kloros.lifecycle.state_machine import promote_to_active, demote_to_dormant
from kloros.registry.lifecycle_registry import load_lifecycle_policy

logger = logging.getLogger(__name__)

DEFAULT_PHASE_FITNESS_PATH = Path.home() / ".kloros/lineage/phase_fitness.jsonl"


def load_phase_rows(candidate: str, since_ts: Optional[float] = None) -> List[dict]:
    """
    Load PHASE fitness rows for a candidate from streaming JSONL.

    Args:
        candidate: Zooid name to filter rows for
        since_ts: Optional timestamp filter (only rows >= this timestamp)

    Returns:
        List of PHASE fitness row dicts
    """
    path = DEFAULT_PHASE_FITNESS_PATH
    out = []

    try:
        with open(path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSONL row: {line[:100]}")
                    continue

                if row.get("candidate") != candidate:
                    continue

                if since_ts and float(row.get("ts", 0)) < since_ts:
                    continue

                out.append(row)
    except FileNotFoundError:
        logger.debug(f"PHASE fitness file not found: {path}")
        pass

    logger.debug(f"Loaded {len(out)} PHASE rows for {candidate} (since_ts={since_ts})")
    return out


def ewma_with_half_life(
    rows: List[dict],
    now: float,
    half_life_sec: int
) -> Tuple[float, int, Optional[float]]:
    """
    Compute exponentially-weighted moving average with time-based decay.

    Args:
        rows: PHASE fitness rows with "ts" and "composite_phase_fitness"
        now: Current timestamp
        half_life_sec: Half-life for exponential decay

    Returns:
        Tuple of (fitness_mean, evidence_count, ci95_optional)

    Algorithm:
        weight = 0.5 ** ((now - row["ts"]) / half_life_sec)
        fitness_mean = sum(w * x) / sum(w)
    """
    ws, xs = [], []

    for r in rows:
        ts = float(r.get("ts", now))

        if ts > now + 120:
            logger.warning(f"Skipping future row: ts={ts}, now={now}")
            continue

        w = 0.5 ** ((now - ts) / max(1, half_life_sec))
        x = float(r.get("composite_phase_fitness", 0.0))

        ws.append(w)
        xs.append(x)

    if not ws:
        return (0.0, 0, None)

    mean = sum(w * x for w, x in zip(ws, xs)) / sum(ws)

    ci95 = None
    try:
        if len(xs) > 1:
            ci95 = 1.96 * (statistics.pstdev(xs) / math.sqrt(len(xs)))
    except Exception as e:
        logger.debug(f"Failed to compute CI95: {e}")

    return (mean, len(xs), ci95)


def run_graduations(
    reg: dict,
    now: float,
    *,
    start_service: Callable[[str], None],
    wait_for_heartbeat: Callable[[str, float], bool],
    on_event: Optional[Callable[[dict], None]] = None
) -> List[str]:
    """
    Promote PROBATION zooids to ACTIVE if they pass gates.

    Args:
        reg: Registry dict (mutated in-place)
        now: Current timestamp
        start_service: Callback to start service by name
        wait_for_heartbeat: Callback to wait for heartbeat (name, timeout_sec) -> bool
        on_event: Optional callback for state change events

    Returns:
        List of successfully promoted zooid names

    Algorithm:
        1. Find all PROBATION zooids
        2. For each: aggregate PHASE fitness with EWMA
        3. If passes gates (fit >= threshold AND ev >= min):
           - Promote to ACTIVE
           - Start service
           - Wait for heartbeat
           - If no heartbeat: rollback to DORMANT
        4. Emit events with fitness breakdown
    """
    policy = load_lifecycle_policy()

    phase_threshold = policy.get("phase_threshold", 0.70)
    min_phase_evidence = policy.get("min_phase_evidence", 50)
    phase_half_life_sec = policy.get("phase_half_life_sec", 43200)
    prod_ok_threshold = policy.get("prod_ok_threshold", 0.95)
    prod_min_evidence = policy.get("prod_min_evidence", 10)
    probation_retry_cooldown_sec = policy.get("probation_retry_cooldown_sec", 3600)
    probation_max_retries = policy.get("probation_max_retries", 3)
    heartbeat_slo_sec = 30.0

    promoted = []
    probation_names = []

    for niche_name, niche_data in reg["niches"].items():
        probation_names.extend(niche_data.get("probation", []))

    logger.info(f"Found {len(probation_names)} PROBATION zooids to evaluate")

    for name in probation_names:
        z = reg["zooids"].get(name)
        if not z:
            logger.warning(f"Zooid not found in registry: {name}")
            continue

        if z.get("lifecycle_state") != "PROBATION":
            logger.warning(f"Zooid {name} not in PROBATION state: {z.get('lifecycle_state')}")
            continue

        logger.info(f"Evaluating {name} for graduation...")

        rows = load_phase_rows(name, since_ts=None)

        if not rows:
            logger.info(f"  No PHASE rows for {name}, skipping")
            continue

        fitness_mean, evidence, ci95 = ewma_with_half_life(rows, now, phase_half_life_sec)

        z["phase"]["fitness_mean"] = fitness_mean
        z["phase"]["evidence"] = evidence
        z["phase"]["last_ts"] = now
        if ci95 is not None:
            z["phase"]["ci95"] = ci95

        logger.info(f"  {name}: fitness={fitness_mean:.3f}, evidence={evidence}, ci95={ci95}")

        # PHASE gate check
        phase_pass = fitness_mean >= phase_threshold and evidence >= min_phase_evidence

        # Production reliability gate check (using windowed ok_rate)
        prod_block = z.get("prod", {})
        ok_rate_window = float(prod_block.get("ok_rate_window", 0.0))
        prod_evidence = int(prod_block.get("evidence", 0))
        prod_pass = ok_rate_window >= prod_ok_threshold and prod_evidence >= prod_min_evidence

        logger.info(f"  {name}: PHASE gate={'PASS' if phase_pass else 'FAIL'} (fit={fitness_mean:.3f} >= {phase_threshold}, ev={evidence} >= {min_phase_evidence})")
        logger.info(f"  {name}: PROD gate={'PASS' if prod_pass else 'FAIL'} (ok_window={ok_rate_window:.3f} >= {prod_ok_threshold}, ev={prod_evidence} >= {prod_min_evidence})")

        if phase_pass and prod_pass:
            logger.info(f"  {name} passes all gates, promoting to ACTIVE")

            promoted_success = promote_to_active(
                reg,
                name,
                now,
                on_start_service=None,
                on_event=None
            )

            if not promoted_success:
                logger.warning(f"  Failed to promote {name} to ACTIVE")
                continue

            if on_event:
                on_event({
                    "event": "zooid_state_change",
                    "ts": now,
                    "zooid": name,
                    "ecosystem": z.get("ecosystem", "queue_management"),
                    "niche": z["niche"],
                    "from": "PROBATION",
                    "to": "ACTIVE",
                    "reason": "phase_graduation",
                    "phase_fit": fitness_mean,
                    "phase_ev": evidence,
                    "policy_threshold": phase_threshold,
                    "policy_min_ev": min_phase_evidence,
                    "genome_hash": z.get("genome_hash"),
                    "parent_lineage": z.get("parent_lineage", []),
                    "service_action": "systemd_start"
                })

            logger.info(f"  Starting service for {name}...")
            try:
                start_service(name)
            except Exception as e:
                logger.error(f"  Failed to start service for {name}: {e}")
                demote_to_dormant(
                    reg,
                    name,
                    "service_start_failed",
                    now,
                    on_stop_service=None,
                    on_event=on_event
                )
                continue

            logger.info(f"  Waiting for heartbeat from {name} (SLO={heartbeat_slo_sec}s)...")
            heartbeat_ok = False
            try:
                heartbeat_ok = wait_for_heartbeat(name, heartbeat_slo_sec)
            except Exception as e:
                logger.error(f"  Heartbeat check failed for {name}: {e}")

            if heartbeat_ok:
                logger.info(f"  ✓ Heartbeat received from {name}")
                promoted.append(name)
            else:
                logger.warning(f"  ✗ No heartbeat from {name}, rolling back...")

                demote_to_dormant(
                    reg,
                    name,
                    "rollback_no_heartbeat",
                    now,
                    on_stop_service=lambda n: logger.info(f"Rollback stopping service: {n}"),
                    on_event=on_event
                )

                logger.warning(f"  Rolled back {name} to DORMANT")

        elif phase_pass and not prod_pass:
            # PHASE passed but production reliability gate failed
            # Allow retry after cooldown (up to max retries)
            z_policy = z.setdefault("policy", {})
            retries = int(z_policy.get("probation_retries", 0))

            if retries < probation_max_retries:
                z_policy["probation_retries"] = retries + 1
                z_policy["next_probation_earliest_ts"] = now + probation_retry_cooldown_sec
                logger.info(f"  {name} PROD gate failed, scheduling retry {retries + 1}/{probation_max_retries} after cooldown ({probation_retry_cooldown_sec}s)")

                # Demote back to DORMANT for re-queuing
                demote_to_dormant(
                    reg,
                    name,
                    "prod_gate_not_met",
                    now,
                    on_stop_service=None,
                    on_event=on_event
                )
            else:
                logger.warning(f"  {name} exceeded max probation retries ({probation_max_retries}), retiring")
                # Retire zooid that can't meet production reliability standards
                from kloros.lifecycle.state_machine import retire_zooid
                retire_zooid(
                    reg,
                    name,
                    "probation_retry_ceiling",
                    now,
                    on_stop_service=None,
                    on_event=on_event
                )

        else:
            # PHASE gate failed
            logger.info(f"  {name} PHASE gate failed (fit={fitness_mean:.3f} < {phase_threshold} OR ev={evidence} < {min_phase_evidence})")

    logger.info(f"Graduated {len(promoted)}/{len(probation_names)} zooids")
    return promoted
