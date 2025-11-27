#!/usr/bin/env python3
"""
GPU Canary Escalation Manager

Manages automatic escalation from predictive to canary mode
based on repeated symptom patterns.
"""
import json
import time
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

FLAGS_DIR = Path("/home/kloros/.kloros/flags")
ESCALATION_FILE = FLAGS_DIR / "escalate_canary.json"
SYMPTOM_HISTORY = FLAGS_DIR / "symptom_history.jsonl"

# Escalation policy: N occurrences in 24h triggers escalation
ESCALATION_THRESHOLD = 3  # occurrences
ESCALATION_WINDOW_HOURS = 24  # hours


@dataclass
class EscalationState:
    """Escalation state for canary mode."""
    escalated: bool
    reason: str
    timestamp: float
    symptom_count: int


def record_symptom(subsystem: str, symptom: str, context: dict):
    """Record a symptom occurrence for escalation tracking."""
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": time.time(),
        "subsystem": subsystem,
        "symptom": symptom,
        "context": context
    }

    with open(SYMPTOM_HISTORY, "a") as f:
        f.write(json.dumps(record) + "\n")

    logger.info(f"Recorded symptom: {subsystem}/{symptom}")


def check_escalation_needed(subsystem: str, symptom: str) -> tuple[bool, int, str]:
    """
    Check if escalation to canary mode is needed based on symptom history.

    Args:
        subsystem: Subsystem name (e.g., "vllm")
        symptom: Symptom identifier (e.g., "oom_events")

    Returns:
        (escalate, count, reason) tuple
    """
    if not SYMPTOM_HISTORY.exists():
        return (False, 0, "No symptom history")

    # Read recent symptoms
    now = time.time()
    cutoff = now - (ESCALATION_WINDOW_HOURS * 3600)

    matching_symptoms = []
    with open(SYMPTOM_HISTORY) as f:
        for line in f:
            try:
                record = json.loads(line.strip())
                if (record.get("timestamp", 0) >= cutoff and
                    record.get("subsystem") == subsystem and
                    record.get("symptom") == symptom):
                    matching_symptoms.append(record)
            except:
                continue

    count = len(matching_symptoms)

    if count >= ESCALATION_THRESHOLD:
        reason = (f"Escalation triggered: {count} {symptom} events in last {ESCALATION_WINDOW_HOURS}h "
                 f"(threshold: {ESCALATION_THRESHOLD})")
        logger.warning(reason)
        return (True, count, reason)

    return (False, count, f"{count}/{ESCALATION_THRESHOLD} symptoms in window")


def set_escalation_flag(reason: str, symptom_count: int):
    """Set escalation flag to trigger canary mode for next maintenance window."""
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)

    state = EscalationState(
        escalated=True,
        reason=reason,
        timestamp=time.time(),
        symptom_count=symptom_count
    )

    with open(ESCALATION_FILE, "w") as f:
        json.dump({
            "escalated": state.escalated,
            "reason": state.reason,
            "timestamp": state.timestamp,
            "symptom_count": state.symptom_count
        }, f, indent=2)

    logger.warning(f"Escalation flag set: {reason}")


def check_escalation_flag() -> Optional[EscalationState]:
    """Check if escalation flag is set."""
    if not ESCALATION_FILE.exists():
        return None

    try:
        with open(ESCALATION_FILE) as f:
            data = json.load(f)

        if data.get("escalated", False):
            return EscalationState(
                escalated=data["escalated"],
                reason=data.get("reason", "Unknown"),
                timestamp=data.get("timestamp", 0),
                symptom_count=data.get("symptom_count", 0)
            )
    except Exception as e:
        logger.error(f"Failed to read escalation flag: {e}")

    return None


def clear_escalation_flag():
    """Clear escalation flag after canary run."""
    if ESCALATION_FILE.exists():
        ESCALATION_FILE.unlink()
        logger.info("Escalation flag cleared")


def should_escalate_to_canary(subsystem: str, symptom: str) -> tuple[bool, str]:
    """
    Determine if we should escalate to canary mode.

    Returns:
        (escalate, reason) tuple
    """
    # Check if already escalated
    state = check_escalation_flag()
    if state and state.escalated:
        return (True, f"Escalation flag active: {state.reason}")

    # Check symptom history
    escalate, count, reason = check_escalation_needed(subsystem, symptom)

    if escalate:
        # Set escalation flag for next run
        set_escalation_flag(reason, count)
        return (True, reason)

    return (False, reason)


if __name__ == "__main__":
    # Test escalation logic
    import sys

    if len(sys.argv) < 3:
        print("Usage: escalation_manager.py <subsystem> <symptom>")
        sys.exit(1)

    subsystem = sys.argv[1]
    symptom = sys.argv[2]

    # Record symptom
    record_symptom(subsystem, symptom, {"test": True})

    # Check escalation
    escalate, reason = should_escalate_to_canary(subsystem, symptom)

    print(f"Escalate: {escalate}")
    print(f"Reason: {reason}")

    if escalate:
        print(f"\nEscalation flag set at: {ESCALATION_FILE}")
