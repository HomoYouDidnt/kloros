"""Outcome grading and fitness scoring for chaos experiments."""

from typing import Dict, Any


def grade_outcome(
    spec,
    before: Dict[str, Any],
    after: Dict[str, Any],
    outcome: Dict[str, Any]
) -> int:
    """Grade the outcome of a chaos experiment.

    Args:
        spec: FailureSpec that was executed
        before: Metrics snapshot before experiment
        after: Metrics snapshot after experiment
        outcome: Experiment outcome dict

    Returns:
        Score from 0-100 (higher is better)
    """
    score = 50  # Base score

    # Did healing occur?
    if outcome.get("healed"):
        score += 30
        print(f"[grading] +30 healing occurred")
    else:
        score -= 20
        print(f"[grading] -20 no healing")

    # Check expected event was emitted
    expected_event = spec.expected.get("heal_event")
    if expected_event:
        if outcome.get("event") == expected_event:
            score += 10
            print(f"[grading] +10 expected event emitted")
        else:
            score -= 10
            print(f"[grading] -10 expected event missing")

    # MTTR (Mean Time To Recovery) - faster is better
    duration = outcome.get("duration_s", 0)
    max_duration = spec.guards.get("max_duration_s", 20)
    if duration < max_duration * 0.3:
        score += 15  # Very fast recovery
        print(f"[grading] +15 fast recovery ({duration:.1f}s)")
    elif duration < max_duration * 0.6:
        score += 5  # Reasonable recovery
        print(f"[grading] +5 reasonable recovery ({duration:.1f}s)")
    else:
        score -= 5  # Slow recovery
        print(f"[grading] -5 slow recovery ({duration:.1f}s)")

    # Metric improvements
    if "synth_timeout_rate" in before and "synth_timeout_rate" in after:
        delta = before["synth_timeout_rate"] - after["synth_timeout_rate"]
        if delta > 0:
            score += min(15, int(delta * 100))
            print(f"[grading] +{min(15, int(delta*100))} timeout rate improved")
        elif delta < 0:
            score -= min(10, abs(int(delta * 100)))
            print(f"[grading] -{min(10, abs(int(delta*100)))} timeout rate worsened")

    # Penalize increased false triggers
    if "false_vad_rate" in before and "false_vad_rate" in after:
        delta = after["false_vad_rate"] - before["false_vad_rate"]
        if delta > 0:
            penalty = min(15, int(delta * 100))
            score -= penalty
            print(f"[grading] -{penalty} false VAD rate increased")

    # Bonus for clean recovery (no side effects)
    if outcome.get("clean_recovery", False):
        score += 10
        print(f"[grading] +10 clean recovery")

    # Penalize if guards were triggered
    if outcome.get("guard_triggered"):
        score -= 15
        print(f"[grading] -15 safety guard triggered")

    # Normalize to 0-100
    final_score = max(0, min(100, score))
    print(f"[grading] Final score: {final_score}/100")

    return final_score


def calculate_mttr(events: list) -> float:
    """Calculate Mean Time To Recovery from event list.

    Args:
        events: List of events with timestamps

    Returns:
        MTTR in seconds
    """
    if len(events) < 2:
        return 0.0

    # Find first failure event and first heal event
    from datetime import datetime

    failure_time = None
    heal_time = None

    for evt in events:
        timestamp = evt.get("timestamp")
        if not timestamp:
            continue

        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        # Look for failure indicators
        if evt.get("severity") in ["error", "critical"]:
            if failure_time is None:
                failure_time = timestamp

        # Look for healing indicators
        if "heal" in evt.get("kind", "").lower() or evt.get("source") == "self_heal":
            heal_time = timestamp
            break

    if failure_time and heal_time:
        return (heal_time - failure_time).total_seconds()

    return 0.0


def rank_scenarios(results: list) -> list:
    """Rank scenarios by teaching value.

    Args:
        results: List of experiment result dicts

    Returns:
        Sorted list (best teachers first)
    """
    # Score based on:
    # 1. Did healing occur? (teaches system response)
    # 2. Reasonable duration (not too fast, not timeout)
    # 3. Clear outcome (not flaky)

    scored = []
    for result in results:
        score = result.get("score", 0)
        outcome = result.get("outcome", {})

        teaching_value = score

        # Bonus for scenarios that trigger healing
        if outcome.get("healed"):
            teaching_value += 20

        # Bonus for mid-range MTTR (interesting recovery time)
        duration = outcome.get("duration_s", 0)
        if 2 < duration < 15:
            teaching_value += 10

        # Penalty for timeouts (didn't teach us much)
        if outcome.get("reason") == "timeout":
            teaching_value -= 15

        scored.append((teaching_value, result))

    # Sort by teaching value (descending)
    scored.sort(key=lambda x: x[0], reverse=True)

    return [r for _, r in scored]
