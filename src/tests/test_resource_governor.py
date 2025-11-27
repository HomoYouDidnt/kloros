#!/usr/bin/env python3
"""
Tests for ResourceGovernor

Covers all safety mechanisms:
- Disk space checks
- Spawn rate limiting
- Instance count limits
- Circuit breaker
"""

import pytest
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import time

import sys
sys.path.insert(0, '/home/kloros')
from src.governance.guidance.resource_governor import ResourceGovernor, CircuitState, ResourceStatus


@pytest.fixture
def temp_config():
    """Temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_kloros.yaml"
        state_file = Path(tmpdir) / "state.json"
        instances_dir = Path(tmpdir) / "instances"
        instances_dir.mkdir()
        
        yield {
            "config_path": config_path,
            "state_file": state_file,
            "instances_dir": instances_dir
        }


@pytest.fixture
def governor(temp_config):
    """Fresh ResourceGovernor instance."""
    gov = ResourceGovernor(config_path=temp_config["config_path"])
    gov.state_file = temp_config["state_file"]
    gov.config["instances_dir"] = str(temp_config["instances_dir"])
    return gov


class TestDiskSpaceChecks:
    """Test disk space safety checks."""

    @patch('shutil.disk_usage')
    def test_sufficient_disk_space(self, mock_usage, governor):
        """Allow spawn when disk space is sufficient."""
        mock_usage.return_value = MagicMock(
            free=30 * 1024**3,  # 30GB free
            total=100 * 1024**3
        )

        can_spawn, reason = governor.check_disk_space()
        assert can_spawn is True
        assert reason is None

    @patch('shutil.disk_usage')
    def test_insufficient_disk_space(self, mock_usage, governor):
        """Block spawn when disk space is low."""
        mock_usage.return_value = MagicMock(
            free=10 * 1024**3,  # 10GB free (below 20GB limit)
            total=100 * 1024**3
        )

        can_spawn, reason = governor.check_disk_space()
        assert can_spawn is False
        assert "Disk space too low" in reason
        assert "10.0GB" in reason


class TestSpawnRateLimiting:
    """Test spawn rate limiting."""

    def test_allows_spawns_within_limit(self, governor):
        """Allow spawns when under rate limit."""
        # Record 2 successful spawns (limit is 3/hour)
        governor.record_spawn_attempt(success=True)
        governor.record_spawn_attempt(success=True)

        can_spawn, reason = governor.check_spawn_rate()
        assert can_spawn is True
        assert reason is None

    def test_blocks_spawns_over_limit(self, governor):
        """Block spawns when rate limit exceeded."""
        # Record 3 successful spawns (hitting limit)
        for _ in range(3):
            governor.record_spawn_attempt(success=True)

        can_spawn, reason = governor.check_spawn_rate()
        assert can_spawn is False
        assert "Spawn rate exceeded" in reason

    def test_old_events_dont_count(self, governor):
        """Events older than 1 hour don't count against limit."""
        # Record spawn from 2 hours ago
        old_event = {
            "timestamp": time.time() - 7200,
            "success": True
        }
        governor.state["spawn_history"].append(old_event)
        governor._save_state()

        # Should still allow 3 new spawns
        for _ in range(3):
            can_spawn, _ = governor.check_spawn_rate()
            assert can_spawn is True
            governor.record_spawn_attempt(success=True)


class TestInstanceCountLimits:
    """Test instance count hard cap."""

    def test_allows_spawns_under_limit(self, governor, temp_config):
        """Allow spawns when under instance limit."""
        instances_dir = temp_config["instances_dir"]

        # Create 3 instances (limit is 5)
        for i in range(3):
            (instances_dir / f"spica-{i:08x}").mkdir()

        can_spawn, reason = governor.check_instance_count()
        assert can_spawn is True
        assert reason is None

    def test_blocks_spawns_at_limit(self, governor, temp_config):
        """Block spawns when at instance limit."""
        instances_dir = temp_config["instances_dir"]

        # Create 5 instances (hitting limit)
        for i in range(5):
            (instances_dir / f"spica-{i:08x}").mkdir()

        can_spawn, reason = governor.check_instance_count()
        assert can_spawn is False
        assert "Instance limit reached" in reason

    def test_ignores_non_spica_dirs(self, governor, temp_config):
        """Don't count directories that aren't SPICA instances."""
        instances_dir = temp_config["instances_dir"]

        (instances_dir / "spica-12345678").mkdir()
        (instances_dir / "not-a-spica-instance").mkdir()
        (instances_dir / "instances").mkdir()  # metadata dir

        can_spawn, reason = governor.check_instance_count()
        assert can_spawn is True  # Only 1 real instance


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_closed_allows_spawns(self, governor):
        """Circuit breaker in CLOSED state allows spawns."""
        governor.state["circuit_state"] = CircuitState.CLOSED.value

        can_spawn, reason = governor.check_circuit_breaker()
        assert can_spawn is True
        assert reason is None

    def test_circuit_opens_after_failures(self, governor):
        """Circuit opens after threshold failures."""
        # Record 3 failures (hitting threshold)
        for _ in range(3):
            governor.record_spawn_attempt(success=False, reason="test failure")

        assert governor.state["circuit_state"] == CircuitState.OPEN.value
        assert governor.state["consecutive_failures"] == 3

    def test_circuit_open_blocks_spawns(self, governor):
        """Circuit in OPEN state blocks spawns."""
        governor.state["circuit_state"] = CircuitState.OPEN.value
        governor.state["circuit_opened_at"] = time.time()

        can_spawn, reason = governor.check_circuit_breaker()
        assert can_spawn is False
        assert "Circuit breaker OPEN" in reason

    def test_circuit_transitions_to_half_open(self, governor):
        """Circuit transitions to HALF_OPEN after recovery period."""
        governor.state["circuit_state"] = CircuitState.OPEN.value
        governor.state["circuit_opened_at"] = time.time() - 400  # 400s ago (recovery is 300s)

        can_spawn, reason = governor.check_circuit_breaker()
        assert can_spawn is True
        assert governor.state["circuit_state"] == CircuitState.HALF_OPEN.value

    def test_success_closes_half_open_circuit(self, governor):
        """Success in HALF_OPEN closes circuit."""
        governor.state["circuit_state"] = CircuitState.HALF_OPEN.value
        governor.state["consecutive_failures"] = 2

        governor.record_spawn_attempt(success=True)

        assert governor.state["circuit_state"] == CircuitState.CLOSED.value
        assert governor.state["consecutive_failures"] == 0


class TestIntegratedChecks:
    """Test integrated can_spawn() checks."""

    @patch('shutil.disk_usage')
    def test_all_checks_passing(self, mock_usage, governor):
        """Allow spawn when all checks pass."""
        mock_usage.return_value = MagicMock(
            free=50 * 1024**3,
            total=100 * 1024**3
        )

        can_spawn, reason = governor.can_spawn()
        assert can_spawn is True
        assert reason is None

    @patch('shutil.disk_usage')
    def test_any_check_failing_blocks_spawn(self, mock_usage, governor):
        """Block spawn if any check fails."""
        mock_usage.return_value = MagicMock(
            free=10 * 1024**3,  # Failing disk check
            total=100 * 1024**3
        )

        can_spawn, reason = governor.can_spawn()
        assert can_spawn is False
        assert reason is not None


class TestStatus:
    """Test status reporting."""

    @patch('shutil.disk_usage')
    def test_get_status(self, mock_usage, governor, temp_config):
        """Status includes all metrics."""
        mock_usage.return_value = MagicMock(
            free=25 * 1024**3,
            used=75 * 1024**3,
            total=100 * 1024**3
        )

        # Create 2 instances
        instances_dir = temp_config["instances_dir"]
        (instances_dir / "spica-aaaaaaaa").mkdir()
        (instances_dir / "spica-bbbbbbbb").mkdir()

        # Record 1 spawn
        governor.record_spawn_attempt(success=True)

        status = governor.get_status()

        assert status.disk_free_gb == pytest.approx(25.0, rel=0.1)
        assert status.disk_usage_pct == pytest.approx(75.0, rel=0.1)
        assert status.active_instances == 2
        assert status.recent_spawns == 1
        assert status.circuit_state == CircuitState.CLOSED.value
        assert status.can_spawn is True


class TestManualReset:
    """Test manual circuit reset."""

    def test_reset_circuit(self, governor):
        """Manual reset closes circuit and clears failures."""
        governor.state["circuit_state"] = CircuitState.OPEN.value
        governor.state["consecutive_failures"] = 5
        governor.state["circuit_opened_at"] = time.time()

        result = governor.reset_circuit()

        assert result is True
        assert governor.state["circuit_state"] == CircuitState.CLOSED.value
        assert governor.state["consecutive_failures"] == 0
        assert governor.state["circuit_opened_at"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
