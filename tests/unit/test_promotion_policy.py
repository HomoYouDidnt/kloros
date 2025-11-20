"""Unit tests for promotion policy and state management."""
import json
import tempfile
from pathlib import Path
import pytest

from src.kloros.synthesis.promotion import (
    PromotionState,
    CandidateStats,
    load_policy,
    load_state,
    save_state,
    reset_if_new_day,
    promote_if_eligible,
)


def test_candidate_stats_initialization():
    """Test CandidateStats initialization."""
    stats = CandidateStats()

    assert stats.trials == 0
    assert stats.wins == 0
    assert stats.avg_delta == 0.0


def test_promotion_state_record():
    """Test recording shadow test outcomes."""
    state = PromotionState()

    # Record positive delta (win)
    state.record("tool_a", delta=0.05)

    assert state.stats["tool_a"].trials == 1
    assert state.stats["tool_a"].wins == 1
    assert abs(state.stats["tool_a"].avg_delta - 0.05) < 0.001

    # Record negative delta (loss)
    state.record("tool_a", delta=-0.02)

    assert state.stats["tool_a"].trials == 2
    assert state.stats["tool_a"].wins == 1
    # Average: (0.05 + -0.02) / 2 = 0.015
    assert abs(state.stats["tool_a"].avg_delta - 0.015) < 0.001


def test_promotion_state_online_mean():
    """Test online mean calculation for avg_delta."""
    state = PromotionState()

    # Record several outcomes
    deltas = [0.05, -0.02, 0.03, 0.01, -0.01]
    for delta in deltas:
        state.record("tool_b", delta)

    expected_mean = sum(deltas) / len(deltas)
    assert abs(state.stats["tool_b"].avg_delta - expected_mean) < 0.001


def test_load_save_state(tmp_path):
    """Test state persistence."""
    state_file = tmp_path / "test_state.json"

    # Create state with data
    state = PromotionState()
    state.record("tool_a", 0.05)
    state.record("tool_a", 0.03)
    state.today_promoted = 1
    state.last_reset = "2025-10-14"

    # Save
    save_state(state, str(state_file))
    assert state_file.exists()

    # Load
    loaded = load_state(str(state_file))

    assert "tool_a" in loaded.stats
    assert loaded.stats["tool_a"].trials == 2
    assert loaded.stats["tool_a"].wins == 2
    assert loaded.today_promoted == 1
    assert loaded.last_reset == "2025-10-14"


def test_reset_if_new_day():
    """Test daily quota reset."""
    state = PromotionState()
    state.today_promoted = 5
    state.last_reset = "2025-10-13"  # Yesterday

    reset_if_new_day(state)

    # Should reset if date changed
    import datetime as dt
    today = dt.date.today().isoformat()

    if state.last_reset != today:
        assert state.today_promoted == 0
        assert state.last_reset == today


def test_load_policy_default():
    """Test loading default policy when file not found."""
    policy = load_policy("/nonexistent/path/policy.toml")

    # Should return default policy
    assert "promotion" in policy
    assert "shadow" in policy
    assert "bandit" in policy
    assert "risk" in policy


def test_load_policy_from_file():
    """Test loading policy from actual file."""
    policy = load_policy("/home/kloros/config/policy.toml")

    # Check required sections exist
    assert "promotion" in policy
    assert "shadow" in policy
    assert "bandit" in policy

    # Check promotion settings
    prom = policy["promotion"]
    assert "shadow_win_min" in prom
    assert "min_shadow_trials" in prom
    assert "max_tools_promote_per_day" in prom
    assert "require_tests_green" in prom
    assert "risk_allow" in prom


def test_promote_if_eligible_not_enough_trials():
    """Test promotion blocked by insufficient trials."""
    policy = load_policy()
    state = PromotionState()

    # Only 5 trials (need 20 by default)
    for i in range(5):
        state.record("tool_test", 0.05)

    promoted, reason = promote_if_eligible(
        "tool_test", policy=policy, state=state
    )

    assert not promoted
    assert "not_enough_trials" in reason


def test_promote_if_eligible_low_win_rate():
    """Test promotion blocked by low win rate."""
    policy = load_policy()
    state = PromotionState()

    # 25 trials but mostly losses (avg_delta < 0.02)
    for i in range(25):
        delta = 0.01 if i % 5 == 0 else -0.01  # 20% wins
        state.record("tool_test", delta)

    promoted, reason = promote_if_eligible(
        "tool_test", policy=policy, state=state
    )

    assert not promoted
    assert "not_winning_enough" in reason


def test_promote_if_eligible_quota_exhausted():
    """Test promotion blocked by daily quota."""
    import datetime as dt
    policy = load_policy()
    state = PromotionState()

    # Exhaust quota
    state.today_promoted = policy["promotion"]["max_tools_promote_per_day"]
    state.last_reset = dt.date.today().isoformat()  # Use today's date to prevent reset

    # Good tool but quota exhausted
    for i in range(25):
        state.record("tool_test", 0.05)

    promoted, reason = promote_if_eligible(
        "tool_test", policy=policy, state=state
    )

    assert not promoted
    assert "quota_exhausted" in reason


def test_promote_if_eligible_high_risk_blocked():
    """Test promotion blocked by high risk level."""
    policy = load_policy()
    policy["risk"]["dangerous_tool"] = "high"

    state = PromotionState()

    # Good stats but high risk
    for i in range(25):
        state.record("dangerous_tool", 0.05)

    promoted, reason = promote_if_eligible(
        "dangerous_tool", policy=policy, state=state
    )

    assert not promoted
    assert "risk_blocked" in reason
