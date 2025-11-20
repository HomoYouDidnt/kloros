"""
Cycle Coordinator - orchestrates daily lifecycle operations.

Manages handoffs: Bioreactor → PHASE → Graduator → Runtime
Enforces global mutex during registry mutations.
Fully idempotent and retriable.
"""
import datetime
import logging
from contextlib import contextmanager
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_ntp_skew_seconds() -> float:
    """
    Get NTP clock skew in seconds.

    Returns:
        Skew in seconds (positive = local ahead, negative = local behind)

    Note: Simplified implementation returns 0.0 for testing.
    Production should query chronyc tracking or similar.
    """
    return 0.0


def within_window(now: float, start_hhmm: str, end_hhmm: str, tz: str = "UTC") -> bool:
    """
    Check if current time is within daily window.

    Args:
        now: Current timestamp
        start_hhmm: Start time "HH:MM" (e.g., "03:00")
        end_hhmm: End time "HH:MM" (e.g., "07:00")
        tz: Timezone (default UTC)

    Returns:
        True if now is within [start, end)
    """
    dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
    current_hhmm = dt.strftime("%H:%M")

    return start_hhmm <= current_hhmm < end_hhmm


def run_bioreactor_phase(
    reg: dict,
    now: float,
    bioreactor_tick: Callable[..., dict],
    ecosystems_niches: List[Tuple[str, str]],
    *,
    on_event: Optional[Callable[[dict], None]] = None
) -> Dict:
    """
    Run bioreactor phase for all niches.

    Args:
        reg: Registry dict (mutated in-place)
        now: Current timestamp
        bioreactor_tick: Callback for bioreactor tick
        ecosystems_niches: List of (ecosystem, niche) tuples
        on_event: Optional event callback

    Returns:
        Stats dict with counts
    """
    logger.info("Starting bioreactor phase")
    total_new_candidates = 0
    all_winners = []
    all_survivors = []

    for ecosystem, niche in ecosystems_niches:
        logger.info(f"Running bioreactor for {ecosystem}/{niche}")

        try:
            result = bioreactor_tick(
                reg,
                ecosystem,
                niche,
                [],
                [],
                now
            )

            total_new_candidates += result.get("new_candidates", 0)
            all_winners.extend(result.get("winners", []))
            all_survivors.extend(result.get("survivors", []))

        except Exception as e:
            logger.error(f"Bioreactor tick failed for {ecosystem}/{niche}: {e}")

    if on_event:
        on_event({
            "event": "cycle_phase",
            "ts": now,
            "stage": "bioreactor",
            "new_candidates": total_new_candidates,
            "winners": len(all_winners),
            "survivors": len(all_survivors)
        })

    logger.info(f"Bioreactor phase complete: {total_new_candidates} candidates, {len(all_winners)} winners")

    return {
        "new_candidates": total_new_candidates,
        "winners": all_winners,
        "survivors": all_survivors
    }


def run_phase_window(
    reg: dict,
    now: float,
    start_probation_batch: Callable[..., List[str]],
    discover_dormant: Callable[[dict], List[str]],
    *,
    on_event: Optional[Callable[[dict], None]] = None
) -> Dict:
    """
    Run PHASE window: transition DORMANT → PROBATION.

    Args:
        reg: Registry dict (mutated in-place)
        now: Current timestamp
        start_probation_batch: Callback to transition to probation
        discover_dormant: Callback to find DORMANT zooids
        on_event: Optional event callback

    Returns:
        Stats dict with counts
    """
    logger.info("Starting PHASE window")

    dormant_names = discover_dormant(reg)
    logger.info(f"Found {len(dormant_names)} DORMANT zooids")

    if not dormant_names:
        logger.info("No DORMANT zooids to transition")
        return {"promoted_to_probation": 0}

    batch_id = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ-LIGHT")

    promoted = start_probation_batch(
        reg,
        dormant_names,
        batch_id,
        now
    )

    if on_event:
        on_event({
            "event": "cycle_phase",
            "ts": now,
            "stage": "phase",
            "promoted_to_probation": len(promoted),
            "batch_id": batch_id
        })

    logger.info(f"PHASE window complete: {len(promoted)} transitioned to PROBATION")

    return {"promoted_to_probation": len(promoted), "batch_id": batch_id}


def run_graduation_phase(
    reg: dict,
    now: float,
    run_graduations: Callable[..., List[str]],
    *,
    on_event: Optional[Callable[[dict], None]] = None
) -> Dict:
    """
    Run graduation phase: promote PROBATION → ACTIVE.

    Args:
        reg: Registry dict (mutated in-place)
        now: Current timestamp
        run_graduations: Callback to run graduations
        on_event: Optional event callback

    Returns:
        Stats dict with counts
    """
    logger.info("Starting graduation phase")

    promoted = run_graduations(reg, now, on_event=on_event)

    if on_event:
        on_event({
            "event": "cycle_phase",
            "ts": now,
            "stage": "graduation",
            "promoted_to_active": len(promoted)
        })

    logger.info(f"Graduation phase complete: {len(promoted)} promoted to ACTIVE")

    return {"promoted_to_active": len(promoted)}


def cycle_once(
    now: float,
    registry_load: Callable[[], dict],
    registry_lock: contextmanager,
    registry_write: Callable[[dict], None],
    bioreactor_tick: Callable[..., dict],
    start_probation_batch: Callable[..., List[str]],
    discover_dormant: Callable[[dict], List[str]],
    run_graduations: Callable[..., List[str]],
    *,
    phase_window: Tuple[str, str] = ("03:00", "07:00"),
    bioreactor_window: Tuple[str, str] = ("00:00", "03:00"),
    tz: str = "UTC",
    ecosystems_niches: Optional[List[Tuple[str, str]]] = None,
    on_event: Optional[Callable[[dict], None]] = None
) -> Dict:
    """
    Run one idempotent cycle pass.

    Args:
        now: Current timestamp
        registry_load: Callback to load registry
        registry_lock: Context manager for registry lock
        registry_write: Callback to write registry atomically
        bioreactor_tick: Callback for bioreactor tick
        start_probation_batch: Callback to start probation
        discover_dormant: Callback to find DORMANT zooids
        run_graduations: Callback to run graduations
        phase_window: (start, end) for PHASE window
        bioreactor_window: (start, end) for bioreactor window
        tz: Timezone
        ecosystems_niches: List of (ecosystem, niche) tuples
        on_event: Optional event callback

    Returns:
        Stats dict describing what was executed
    """
    skew = get_ntp_skew_seconds()
    if abs(skew) > 2.0:
        logger.warning(f"NTP skew detected: {skew:.2f}s")
        if on_event:
            on_event({
                "event": "clock_skew_warning",
                "ts": now,
                "skew_seconds": skew
            })

    if ecosystems_niches is None:
        ecosystems_niches = [("prod_guard", "latency_monitoring")]

    result = {"stage": None, "stats": {}}

    with registry_lock():
        reg = registry_load()
        initial_version = reg.get("version", 0)

        if within_window(now, bioreactor_window[0], bioreactor_window[1], tz):
            logger.info("Executing bioreactor phase")
            stats = run_bioreactor_phase(
                reg,
                now,
                bioreactor_tick,
                ecosystems_niches,
                on_event=on_event
            )
            result["stage"] = "bioreactor"
            result["stats"] = stats
            registry_write(reg)

        elif within_window(now, phase_window[0], phase_window[1], tz):
            logger.info("Executing PHASE window")
            stats = run_phase_window(
                reg,
                now,
                start_probation_batch,
                discover_dormant,
                on_event=on_event
            )
            result["stage"] = "phase"
            result["stats"] = stats
            registry_write(reg)

        elif within_window(now, "07:00", "23:59", tz):
            logger.info("Executing graduation phase")
            stats = run_graduation_phase(
                reg,
                now,
                run_graduations,
                on_event=on_event
            )
            result["stage"] = "graduation"
            result["stats"] = stats
            registry_write(reg)

        else:
            logger.info("No active window; skipping cycle")
            result["stage"] = "idle"

        final_version = reg.get("version", 0)
        result["version_delta"] = final_version - initial_version

    logger.info(f"Cycle complete: stage={result['stage']}, version_delta={result['version_delta']}")
    return result
