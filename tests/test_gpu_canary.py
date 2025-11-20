#!/usr/bin/env python3
"""
Minimal tests for GPU canary system.

Tests budget tracking, maintenance window parsing, and lock acquisition.
"""
import os
import time
import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Setup path
import sys
sys.path.insert(0, '/home/kloros')

from src.spica.gpu_canary_runner import (
    _in_window, _budget_key, _read_budget, _write_budget,
    _sec_budget_remaining, _add_budget
)
from src.kloros.orchestration.gpu_maintenance_lock import (
    try_acquire_gpu_lock, check_gpu_lock_status, GPULock
)


class TestBudgetTracking:
    """Test budget tracking functions."""

    def test_budget_key_format(self):
        """Test budget key path format."""
        now = datetime(2025, 10, 29, 15, 30, tzinfo=ZoneInfo("America/New_York"))
        key = _budget_key(now)
        assert "gpu_budget_20251029.json" in str(key)

    def test_read_write_budget(self, tmp_path, monkeypatch):
        """Test budget read/write cycle."""
        # Patch BUDGET_DIR to use tmp_path
        import src.spica.gpu_canary_runner as runner
        original_budget_dir = runner.BUDGET_DIR
        runner.BUDGET_DIR = tmp_path

        try:
            # Write budget
            test_budget = {"seconds_used": 42.5}
            _write_budget(test_budget)

            # Read back
            read_budget = _read_budget()
            assert read_budget["seconds_used"] == 42.5
        finally:
            runner.BUDGET_DIR = original_budget_dir

    def test_add_budget_non_negative(self, tmp_path, monkeypatch):
        """Test that adding budget maintains non-negative values."""
        import src.spica.gpu_canary_runner as runner
        original_budget_dir = runner.BUDGET_DIR
        runner.BUDGET_DIR = tmp_path

        try:
            # Start with zero
            _write_budget({"seconds_used": 0})

            # Add some budget
            _add_budget(15.5)
            budget = _read_budget()
            assert budget["seconds_used"] == 15.5

            # Add more
            _add_budget(10.0)
            budget = _read_budget()
            assert budget["seconds_used"] == 25.5

            # Budget should be non-negative
            assert budget["seconds_used"] >= 0
        finally:
            runner.BUDGET_DIR = original_budget_dir

    def test_sec_budget_remaining(self, tmp_path, monkeypatch):
        """Test budget remaining calculation."""
        import src.spica.gpu_canary_runner as runner
        original_budget_dir = runner.BUDGET_DIR
        runner.BUDGET_DIR = tmp_path

        try:
            # Set used budget
            _write_budget({"seconds_used": 30})

            # With default limit of 60s
            remaining = _sec_budget_remaining()
            assert remaining == 30  # 60 - 30

            # Should never be negative
            _write_budget({"seconds_used": 100})
            remaining = _sec_budget_remaining()
            assert remaining == 0  # max(0, 60-100)
        finally:
            runner.BUDGET_DIR = original_budget_dir


class TestMaintenanceWindow:
    """Test maintenance window parsing."""

    def test_in_window_parsing(self, monkeypatch):
        """Test maintenance window time check."""
        # Mock environment
        monkeypatch.setenv("KLR_GPU_MAINTENANCE_WINDOW", "03:00-07:00 America/New_York")

        # Inside window (5:00 AM)
        inside_time = datetime(2025, 10, 29, 5, 0, tzinfo=ZoneInfo("America/New_York"))
        assert _in_window(inside_time) is True

        # Outside window (10:00 AM)
        outside_time = datetime(2025, 10, 29, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        assert _in_window(outside_time) is False

        # Boundary (exactly 3:00 AM)
        boundary_start = datetime(2025, 10, 29, 3, 0, tzinfo=ZoneInfo("America/New_York"))
        assert _in_window(boundary_start) is True

        # Boundary (exactly 7:00 AM)
        boundary_end = datetime(2025, 10, 29, 7, 0, tzinfo=ZoneInfo("America/New_York"))
        assert _in_window(boundary_end) is True


class TestGPULock:
    """Test GPU maintenance lock."""

    def test_acquire_release(self, tmp_path, monkeypatch):
        """Test lock acquire and release cycle."""
        import src.kloros.orchestration.gpu_maintenance_lock as lock_module
        original_lock_dir = lock_module.LOCK_DIR
        lock_module.LOCK_DIR = tmp_path
        lock_module.GPU_LOCK_FILE = tmp_path / "gpu_maintenance.lock"

        try:
            # Acquire lock
            lock = try_acquire_gpu_lock("test-holder", timeout_sec=2)
            assert lock is not None
            assert lock.holder == "test-holder"

            # Check status
            is_locked, holder, pid = check_gpu_lock_status()
            assert is_locked is True
            assert holder == "test-holder"
            assert pid == os.getpid()

            # Release lock
            lock.release()

            # Verify released
            is_locked, holder, pid = check_gpu_lock_status()
            assert is_locked is False
        finally:
            lock_module.LOCK_DIR = original_lock_dir
            lock_module.GPU_LOCK_FILE = original_lock_dir / "gpu_maintenance.lock"

    def test_concurrent_acquisition(self, tmp_path, monkeypatch):
        """Test that lock prevents concurrent acquisition."""
        import src.kloros.orchestration.gpu_maintenance_lock as lock_module
        original_lock_dir = lock_module.LOCK_DIR
        lock_module.LOCK_DIR = tmp_path
        lock_module.GPU_LOCK_FILE = tmp_path / "gpu_maintenance.lock"

        try:
            # First holder acquires lock
            lock1 = try_acquire_gpu_lock("holder1", timeout_sec=1)
            assert lock1 is not None

            # Second holder should fail (short timeout)
            lock2 = try_acquire_gpu_lock("holder2", timeout_sec=1)
            assert lock2 is None

            # Release first lock
            lock1.release()

            # Now second holder can acquire
            lock2 = try_acquire_gpu_lock("holder2", timeout_sec=1)
            assert lock2 is not None
            lock2.release()
        finally:
            lock_module.LOCK_DIR = original_lock_dir
            lock_module.GPU_LOCK_FILE = original_lock_dir / "gpu_maintenance.lock"


class TestModeSwitching:
    """Test two-mode operation detection."""

    def test_mode_detection(self, monkeypatch):
        """Test MODE environment variable detection."""
        # Test predictive mode (default)
        monkeypatch.delenv("KLR_CANARY_MODE", raising=False)
        import importlib
        import src.phase.domains.spica_gpu_allocation as spica_module
        importlib.reload(spica_module)
        assert spica_module.MODE == "predictive"

        # Test canary mode
        monkeypatch.setenv("KLR_CANARY_MODE", "canary")
        importlib.reload(spica_module)
        assert spica_module.MODE == "canary"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
