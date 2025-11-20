#!/usr/bin/env python3
"""
Tests for state_manager.py - Lock management.
"""

import pytest
import time
from pathlib import Path

from src.kloros.orchestration.state_manager import acquire, release, is_stale, reap_stale_locks, LOCK_DIR


def test_lock_acquire_release():
    """Test basic lock acquire and release."""
    handle = acquire("test_basic")
    assert handle is not None
    assert handle.name == "test_basic"
    assert handle._fd is not None

    release(handle)
    assert handle._fd is None


def test_double_acquire_blocks():
    """Test that acquiring the same lock twice fails."""
    handle1 = acquire("test_double")

    with pytest.raises(RuntimeError, match="held by another process"):
        acquire("test_double")

    release(handle1)


def test_different_locks_independent():
    """Test that different locks don't interfere."""
    handle1 = acquire("test_lock_a")
    handle2 = acquire("test_lock_b")

    assert handle1.name != handle2.name

    release(handle1)
    release(handle2)


def test_lock_reacquire_after_release():
    """Test that lock can be reacquired after release."""
    handle1 = acquire("test_reacquire")
    release(handle1)

    # Should be able to acquire again
    handle2 = acquire("test_reacquire")
    release(handle2)


def test_is_stale():
    """Test stale detection."""
    handle = acquire("test_stale")

    # Fresh lock should not be stale
    assert not is_stale(handle, max_age_s=10)

    # Modify timestamp to simulate old lock
    handle.started_at = time.time() - 3700  # 1 hour + 100 seconds ago

    # Should be stale
    assert is_stale(handle, max_age_s=3600)

    release(handle)


def test_reap_stale_locks():
    """Test stale lock reaping."""
    # Create a lock and release it
    handle = acquire("test_reap")
    lock_path = handle.path
    release(handle)

    # Manually modify the lock file to make it stale
    import json
    with open(lock_path, 'r') as f:
        data = json.load(f)

    data['started_at'] = time.time() - 7200  # 2 hours ago
    with open(lock_path, 'w') as f:
        json.dump(data, f)

    # Reap stale locks
    reaped = reap_stale_locks(max_age_s=3600)

    # Our lock should have been reaped
    assert "test_reap" in reaped


def test_lock_directory_created():
    """Test that lock directory is created automatically."""
    assert LOCK_DIR.exists()
    assert LOCK_DIR.is_dir()
