"""Unit tests for LinUCB bandit tool selection."""
import numpy as np
import pytest

from src.kloros.learning.bandit import LinUCBBandit, LinUCBArm, compute_reward


def test_linucb_arm_initialization():
    """Test LinUCB arm initialization."""
    arm = LinUCBArm(name="test_tool", d=4)

    assert arm.name == "test_tool"
    assert arm.d == 4
    assert arm.A.shape == (4, 4)
    assert arm.b.shape == (4, 1)
    assert np.allclose(arm.A, np.eye(4))
    assert np.allclose(arm.b, np.zeros((4, 1)))


def test_linucb_arm_update():
    """Test LinUCB arm parameter updates."""
    arm = LinUCBArm(name="test_tool", d=4)

    x = np.array([1.0, 0.0, 0.0, 0.0])
    reward = 0.8

    arm.update(x, reward)

    # A should now be I + xx^T
    expected_A = np.eye(4)
    expected_A[0, 0] = 2.0  # 1 + 1*1
    assert np.allclose(arm.A, expected_A)

    # b should be reward * x
    expected_b = np.array([[0.8], [0.0], [0.0], [0.0]])
    assert np.allclose(arm.b, expected_b)


def test_linucb_arm_ucb():
    """Test UCB score computation."""
    arm = LinUCBArm(name="test_tool", d=4)

    # Update with some data
    x1 = np.array([1.0, 0.0, 0.0, 0.0])
    arm.update(x1, 0.8)

    # Compute UCB for same context
    ucb = arm.ucb(x1, alpha=1.0)

    # UCB should be positive (mean + exploration bonus)
    assert ucb > 0


def test_linucb_bandit_initialization():
    """Test LinUCB bandit initialization."""
    bandit = LinUCBBandit(d=4, alpha=1.5, warm_start_reward=0.5)

    assert bandit.d == 4
    assert bandit.alpha == 1.5
    assert bandit.warm_start_reward == 0.5
    assert len(bandit.arms) == 0


def test_linucb_bandit_ensure_arm():
    """Test lazy arm creation."""
    bandit = LinUCBBandit(d=4, alpha=1.0, warm_start_reward=0.6)

    assert "tool_a" not in bandit.arms

    bandit.ensure_arm("tool_a")

    assert "tool_a" in bandit.arms
    assert isinstance(bandit.arms["tool_a"], LinUCBArm)


def test_linucb_bandit_rank():
    """Test candidate ranking."""
    bandit = LinUCBBandit(d=4, alpha=1.0, warm_start_reward=0.5)

    x = np.array([1.0, 0.0, 0.0, 0.0])
    candidates = ["tool_a", "tool_b", "tool_c"]

    ranked = bandit.rank(x, candidates)

    # Should return 3 candidates
    assert len(ranked) == 3

    # Each should be (name, score) tuple
    for name, score in ranked:
        assert name in candidates
        assert isinstance(score, float)

    # Scores should be in descending order
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_linucb_bandit_observe_and_learn():
    """Test learning from observations."""
    bandit = LinUCBBandit(d=4, alpha=1.0, warm_start_reward=0.5)

    x = np.array([1.0, 0.0, 0.0, 0.0])

    # Initially, all tools have similar scores
    initial_ranked = bandit.rank(x, ["tool_good", "tool_bad"])
    initial_scores = {name: score for name, score in initial_ranked}

    # Observe: tool_good performs well, tool_bad performs poorly
    for _ in range(10):
        bandit.observe("tool_good", x, reward=0.9)
        bandit.observe("tool_bad", x, reward=0.1)

    # After learning, tool_good should rank higher
    final_ranked = bandit.rank(x, ["tool_good", "tool_bad"])
    assert final_ranked[0][0] == "tool_good"
    assert final_ranked[1][0] == "tool_bad"


def test_compute_reward_success():
    """Test reward computation for successful execution."""
    reward = compute_reward(success=True, latency_ms=1000, tool_hops=1)

    # Base = 1.0, latency penalty = -1000/5000 = -0.2, hops penalty = 0
    expected = 1.0 - 0.2
    assert abs(reward - expected) < 0.01


def test_compute_reward_failure():
    """Test reward computation for failed execution."""
    reward = compute_reward(success=False, latency_ms=1000, tool_hops=1)

    # Base = 0.0, penalties don't matter
    assert reward == 0.0


def test_compute_reward_slow():
    """Test reward computation with high latency."""
    reward = compute_reward(success=True, latency_ms=10000, tool_hops=1)

    # Base = 1.0, latency penalty capped at -0.5
    expected = 1.0 - 0.5
    assert abs(reward - expected) < 0.01


def test_compute_reward_many_hops():
    """Test reward computation with many tool hops."""
    reward = compute_reward(success=True, latency_ms=1000, tool_hops=5)

    # Base = 1.0, latency = -0.2, hops = -(5-1)*0.05 = -0.2
    expected = 1.0 - 0.2 - 0.2
    assert abs(reward - expected) < 0.01


def test_compute_reward_bounds():
    """Test that reward is always in [0, 1]."""
    # Extremely bad case
    reward = compute_reward(success=True, latency_ms=100000, tool_hops=50)
    assert 0.0 <= reward <= 1.0

    # Best case
    reward = compute_reward(success=True, latency_ms=0, tool_hops=1)
    assert 0.0 <= reward <= 1.0
