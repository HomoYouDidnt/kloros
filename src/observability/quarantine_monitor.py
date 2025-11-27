"""
Quarantine Monitor - demotes ACTIVE zooids on failure bursts.

Monitors production OBSERVATION events and demotes misbehaving ACTIVE zooids
when failures exceed threshold within rolling window. Enforces exponential
backoff cooldown and demotion ceiling.
"""
import logging
from typing import Callable, Iterable, List, Optional

from src.lifecycle.state_machine import demote_to_dormant, retire
from src.registry.lifecycle_registry import load_lifecycle_policy

logger = logging.getLogger(__name__)

Row = dict


def check_quarantine(
    reg: dict,
    rows: Iterable[Row],
    now: float,
    *,
    n_failures: int,
    window_sec: int,
    on_stop_service: Optional[Callable[[str], None]] = None,
    on_event: Optional[Callable[[dict], None]] = None,
) -> List[str]:
    """
    Evaluate ACTIVE zooids for demotion based on failure rate.

    Args:
        reg: Registry dict (mutated in-place)
        rows: OBSERVATION rows with "zooid", "ts", "ok" fields
        now: Current timestamp
        n_failures: Threshold for demotion (e.g., 3)
        window_sec: Rolling window size (e.g., 900)
        on_stop_service: Optional callback to stop service
        on_event: Optional callback for state change events

    Returns:
        List of zooid names demoted to DORMANT or RETIRED

    Algorithm:
        1. Group rows by zooid, count failures in window
        2. For each ACTIVE zooid with failures >= threshold:
           - Check cooldown (skip if still cooling down)
           - Demote to DORMANT with exponential backoff
           - If demotions >= ceiling: retire permanently
    """
    policy = load_lifecycle_policy()
    demotion_ceiling = policy.get("demotion_ceiling", 2)
    cooldown_base_sec = policy.get("cooldown_base_sec", 900)

    window_start = now - window_sec
    failures_by_zooid = {}

    for row in rows:
        zooid_name = row.get("zooid")
        ts = float(row.get("ts", 0))
        ok = row.get("ok", True)

        if ts > now + 120:
            logger.warning(f"Skipping future row: ts={ts}, now={now}")
            continue

        if ts < window_start:
            continue

        if not zooid_name:
            continue

        if zooid_name not in failures_by_zooid:
            failures_by_zooid[zooid_name] = 0

        if ok is False:
            failures_by_zooid[zooid_name] += 1

    logger.info(f"Quarantine check: {len(failures_by_zooid)} zooids evaluated, window=[{window_start:.0f}, {now:.0f}]")

    demoted = []

    for zooid_name, failure_count in failures_by_zooid.items():
        if failure_count < n_failures:
            continue

        z = reg["zooids"].get(zooid_name)
        if not z:
            logger.warning(f"Zooid not in registry: {zooid_name}")
            continue

        if z.get("lifecycle_state") != "ACTIVE":
            logger.debug(f"Skipping {zooid_name}: not ACTIVE (state={z.get('lifecycle_state')})")
            continue

        if "policy" not in z:
            z["policy"] = {}

        cooldown_until = z["policy"].get("cooldown_until_ts", 0)
        if now < cooldown_until:
            logger.info(f"Skipping {zooid_name}: in cooldown until {cooldown_until:.0f}")
            continue

        logger.warning(f"Quarantine trip: {zooid_name} has {failure_count} failures in {window_sec}s window")

        current_demotions = z.get("demotions", 0)
        cooldown_sec = cooldown_base_sec * (2 ** current_demotions)
        cooldown_until_ts = now + cooldown_sec

        z["policy"]["prod_guard_failures"] = failure_count
        z["policy"]["cooldown_until_ts"] = cooldown_until_ts

        demoted_success = demote_to_dormant(
            reg,
            zooid_name,
            "prod_guard_trip",
            now,
            on_stop_service=on_stop_service,
            on_event=None
        )

        if not demoted_success:
            logger.error(f"Failed to demote {zooid_name}")
            continue

        if on_event:
            on_event({
                "event": "zooid_state_change",
                "ts": now,
                "zooid": zooid_name,
                "ecosystem": z.get("ecosystem", "queue_management"),
                "niche": z["niche"],
                "from": "ACTIVE",
                "to": "DORMANT",
                "reason": "prod_guard_trip",
                "failures_in_window": failure_count,
                "window_sec": window_sec,
                "demotions": z["demotions"],
                "cooldown_until_ts": cooldown_until_ts,
                "genome_hash": z.get("genome_hash"),
                "parent_lineage": z.get("parent_lineage", []),
                "service_action": "systemd_stop"
            })

        logger.warning(f"Demoted {zooid_name} to DORMANT (demotions={z['demotions']}, cooldown={cooldown_sec}s)")
        demoted.append(zooid_name)

        if z["demotions"] >= demotion_ceiling:
            logger.error(f"Demotion ceiling reached for {zooid_name} ({z['demotions']} >= {demotion_ceiling}), retiring...")

            retired_success = retire(
                reg,
                zooid_name,
                "demotion_ceiling",
                now,
                on_stop_service=None,
                on_event=on_event
            )

            if retired_success:
                logger.error(f"Retired {zooid_name} permanently")

    logger.info(f"Quarantine check complete: {len(demoted)} zooids demoted")
    return demoted


def run_quarantine_monitor_once(
    reg: dict,
    now: float,
    read_recent_rows: Callable[[float], List[Row]],
    on_stop_service: Callable[[str], None],
    on_event: Callable[[dict], None],
) -> List[str]:
    """
    Run one cycle of quarantine monitoring.

    Args:
        reg: Registry dict (mutated in-place)
        now: Current timestamp
        read_recent_rows: Callback to read OBSERVATION rows since timestamp
        on_stop_service: Callback to stop service
        on_event: Callback for state change events

    Returns:
        List of demoted zooid names
    """
    policy = load_lifecycle_policy()
    n_failures = policy.get("n_failures_for_quarantine", 3)
    window_sec = policy.get("quarantine_window_sec", 900)

    since_ts = now - window_sec
    rows = read_recent_rows(since_ts)

    logger.info(f"Quarantine monitor: evaluating {len(rows)} rows since {since_ts:.0f}")

    demoted = check_quarantine(
        reg,
        rows,
        now,
        n_failures=n_failures,
        window_sec=window_sec,
        on_stop_service=on_stop_service,
        on_event=on_event
    )

    return demoted
