"""
Lifecycle state machine for zooid transitions.

Pure functions with injectable side-effect hooks.
Callers must hold registry lock and call atomic write after mutations.
"""
import logging
from typing import Callable, Iterable, List, Optional

logger = logging.getLogger(__name__)

State = str  # "DORMANT" | "PROBATION" | "ACTIVE" | "RETIRED"


def _move_index(reg: dict, niche: str, name: str, from_state: str, to_state: str) -> None:
    """Move zooid between niche state indexes."""
    if niche not in reg["niches"]:
        reg["niches"][niche] = {
            "active": [],
            "probation": [],
            "dormant": [],
            "retired": []
        }

    if name in reg["niches"][niche][from_state]:
        reg["niches"][niche][from_state].remove(name)

    if name not in reg["niches"][niche][to_state]:
        reg["niches"][niche][to_state].append(name)


def _emit_event(on_event: Optional[Callable[[dict], None]], event: dict) -> None:
    """Emit state change event via callback."""
    if on_event:
        on_event(event)
    logger.info(f"State change: {event['zooid']} {event['from']}→{event['to']} ({event['reason']})")


def start_probation(
    reg: dict,
    names: Iterable[str],
    batch_id: str,
    now: float,
    *,
    on_event: Optional[Callable[[dict], None]] = None
) -> List[str]:
    """
    Transition DORMANT zooids to PROBATION for PHASE evaluation.

    Args:
        reg: Registry dict (mutated in-place)
        names: Zooid names to transition
        batch_id: PHASE batch identifier (e.g., "2025-11-07T03:10Z-LIGHT")
        now: Current timestamp
        on_event: Optional callback for state change events

    Returns:
        List of zooid names successfully transitioned

    Idempotent: Already-PROBATION zooids are skipped silently
    """
    promoted = []

    for name in names:
        z = reg["zooids"].get(name)
        if not z:
            logger.warning(f"Zooid not found: {name}")
            continue

        if z["lifecycle_state"] == "PROBATION":
            logger.debug(f"Zooid already in PROBATION, skipping: {name}")
            continue

        if z["lifecycle_state"] != "DORMANT":
            logger.warning(f"Cannot start probation for {name}: current state is {z['lifecycle_state']}, expected DORMANT")
            continue

        prev_ts = z.get("last_transition_ts", z.get("entered_ts", now))
        prev_state = z["lifecycle_state"]

        z["lifecycle_state"] = "PROBATION"

        if "phase" not in z:
            z["phase"] = {"batches": [], "evidence": 0, "fitness_mean": 0.0}

        if batch_id not in z["phase"]["batches"]:
            z["phase"]["batches"].append(batch_id)

        z["last_transition_ts"] = now

        _move_index(reg, z["niche"], name, "dormant", "probation")

        _emit_event(on_event, {
            "event": "zooid_state_change",
            "ts": now,
            "zooid": name,
            "ecosystem": z.get("ecosystem", "queue_management"),
            "niche": z["niche"],
            "from": prev_state,
            "to": "PROBATION",
            "reason": f"phase_batch:{batch_id}",
            "lifecycle_prev_ts": now - prev_ts,
            "genome_hash": z.get("genome_hash"),
            "parent_lineage": z.get("parent_lineage", []),
            "service_action": "noop"
        })

        promoted.append(name)

    logger.info(f"Started probation for {len(promoted)}/{len(list(names))} zooids in batch {batch_id}")
    return promoted


def promote_to_active(
    reg: dict,
    name: str,
    now: float,
    *,
    on_start_service: Optional[Callable[[str], None]] = None,
    on_event: Optional[Callable[[dict], None]] = None
) -> bool:
    """
    Promote PROBATION zooid to ACTIVE after passing PHASE gates.

    Args:
        reg: Registry dict (mutated in-place)
        name: Zooid name to promote
        now: Current timestamp
        on_start_service: Optional callback to start service
        on_event: Optional callback for state change events

    Returns:
        True if promoted, False if already ACTIVE or invalid state

    Side effects: Calls on_start_service(name) if provided
    """
    z = reg["zooids"].get(name)
    if not z:
        logger.error(f"Zooid not found: {name}")
        return False

    if z["lifecycle_state"] == "ACTIVE":
        logger.debug(f"Zooid already ACTIVE: {name}")
        return False

    if z["lifecycle_state"] != "PROBATION":
        logger.error(f"Cannot promote {name}: current state is {z['lifecycle_state']}, expected PROBATION")
        return False

    prev_ts = z.get("last_transition_ts", z.get("entered_ts", now))
    prev_state = z["lifecycle_state"]

    z["lifecycle_state"] = "ACTIVE"
    z["promoted_ts"] = now
    z["last_transition_ts"] = now

    _move_index(reg, z["niche"], name, "probation", "active")

    if on_start_service:
        on_start_service(name)
        service_action = "systemd_start"
    else:
        service_action = "noop"

    _emit_event(on_event, {
        "event": "zooid_state_change",
        "ts": now,
        "zooid": name,
        "ecosystem": z.get("ecosystem", "queue_management"),
        "niche": z["niche"],
        "from": prev_state,
        "to": "ACTIVE",
        "reason": "graduation",
        "lifecycle_prev_ts": now - prev_ts,
        "genome_hash": z.get("genome_hash"),
        "parent_lineage": z.get("parent_lineage", []),
        "service_action": service_action
    })

    logger.info(f"Promoted {name} to ACTIVE")
    return True


def demote_to_dormant(
    reg: dict,
    name: str,
    reason: str,
    now: float,
    *,
    on_stop_service: Optional[Callable[[str], None]] = None,
    on_event: Optional[Callable[[dict], None]] = None
) -> bool:
    """
    Demote ACTIVE zooid to DORMANT (quarantine).

    Args:
        reg: Registry dict (mutated in-place)
        name: Zooid name to demote
        reason: Demotion reason (e.g., "prod_guard_trip")
        now: Current timestamp
        on_stop_service: Optional callback to stop service
        on_event: Optional callback for state change events

    Returns:
        True if demoted, False if already DORMANT or invalid state

    Side effects: Calls on_stop_service(name) if provided
    Policy: Increments demotions counter
    """
    z = reg["zooids"].get(name)
    if not z:
        logger.error(f"Zooid not found: {name}")
        return False

    if z["lifecycle_state"] == "DORMANT":
        logger.debug(f"Zooid already DORMANT: {name}")
        return False

    if z["lifecycle_state"] != "ACTIVE":
        logger.error(f"Cannot demote {name}: current state is {z['lifecycle_state']}, expected ACTIVE")
        return False

    prev_ts = z.get("last_transition_ts", z.get("entered_ts", now))
    prev_state = z["lifecycle_state"]

    z["lifecycle_state"] = "DORMANT"
    z["demotions"] = z.get("demotions", 0) + 1
    z["reason"] = reason
    z["last_transition_ts"] = now

    _move_index(reg, z["niche"], name, "active", "dormant")

    if on_stop_service:
        on_stop_service(name)
        service_action = "systemd_stop"
    else:
        service_action = "noop"

    _emit_event(on_event, {
        "event": "zooid_state_change",
        "ts": now,
        "zooid": name,
        "ecosystem": z.get("ecosystem", "queue_management"),
        "niche": z["niche"],
        "from": prev_state,
        "to": "DORMANT",
        "reason": reason,
        "lifecycle_prev_ts": now - prev_ts,
        "genome_hash": z.get("genome_hash"),
        "parent_lineage": z.get("parent_lineage", []),
        "service_action": service_action,
        "demotions": z["demotions"]
    })

    logger.warning(f"Demoted {name} to DORMANT: {reason} (demotions={z['demotions']})")
    return True


def retire(
    reg: dict,
    name: str,
    reason: str,
    now: float,
    *,
    on_stop_service: Optional[Callable[[str], None]] = None,
    on_event: Optional[Callable[[dict], None]] = None
) -> bool:
    """
    Retire zooid permanently (from any state).

    Args:
        reg: Registry dict (mutated in-place)
        name: Zooid name to retire
        reason: Retirement reason (e.g., "demotion_ceiling", "catastrophic")
        now: Current timestamp
        on_stop_service: Optional callback to stop service
        on_event: Optional callback for state change events

    Returns:
        True if retired, False if already RETIRED

    Side effects: Calls on_stop_service(name) if was ACTIVE
    Policy: Sets retired_reason
    """
    z = reg["zooids"].get(name)
    if not z:
        logger.error(f"Zooid not found: {name}")
        return False

    if z["lifecycle_state"] == "RETIRED":
        logger.debug(f"Zooid already RETIRED: {name}")
        return False

    prev_ts = z.get("last_transition_ts", z.get("entered_ts", now))
    prev_state = z["lifecycle_state"]

    from_index = prev_state.lower()
    needs_stop = (prev_state == "ACTIVE")

    z["lifecycle_state"] = "RETIRED"
    z["retired_reason"] = reason
    z["last_transition_ts"] = now

    _move_index(reg, z["niche"], name, from_index, "retired")

    if needs_stop and on_stop_service:
        on_stop_service(name)
        service_action = "systemd_stop"
    else:
        service_action = "noop"

    _emit_event(on_event, {
        "event": "zooid_state_change",
        "ts": now,
        "zooid": name,
        "ecosystem": z.get("ecosystem", "queue_management"),
        "niche": z["niche"],
        "from": prev_state,
        "to": "RETIRED",
        "reason": reason,
        "lifecycle_prev_ts": now - prev_ts,
        "genome_hash": z.get("genome_hash"),
        "parent_lineage": z.get("parent_lineage", []),
        "service_action": service_action
    })

    logger.warning(f"Retired {name}: {reason} (was {prev_state})")
    return True
