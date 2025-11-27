"""Tests for ObservationCache - thread-safe rolling window."""

import time
import pytest
from src.observability.introspection.observation_cache import ObservationCache


def test_cache_initialization():
    """Test cache initializes with correct window."""
    cache = ObservationCache(window_seconds=300)
    assert cache.window_seconds == 300
    assert len(cache.get_recent()) == 0


def test_append_and_retrieve():
    """Test appending observations and retrieving them."""
    cache = ObservationCache(window_seconds=60)

    obs1 = {"ts": time.time(), "zooid_name": "test_zooid", "ok": True}
    obs2 = {"ts": time.time(), "zooid_name": "test_zooid", "ok": False}

    cache.append(obs1)
    cache.append(obs2)

    recent = cache.get_recent()
    assert len(recent) == 2
    assert recent[0] == obs1
    assert recent[1] == obs2


def test_window_pruning():
    """Test old observations are pruned from cache."""
    cache = ObservationCache(window_seconds=2)

    old_obs = {"ts": time.time() - 3, "zooid_name": "old", "ok": True}
    cache.append(old_obs)

    new_obs = {"ts": time.time(), "zooid_name": "new", "ok": True}
    cache.append(new_obs)

    recent = cache.get_recent()
    assert len(recent) == 1
    assert recent[0]["zooid_name"] == "new"


def test_get_recent_with_custom_window():
    """Test retrieving observations within custom time window."""
    cache = ObservationCache(window_seconds=300)

    now = time.time()
    obs1 = {"ts": now - 100, "zooid_name": "z1", "ok": True}
    obs2 = {"ts": now - 50, "zooid_name": "z2", "ok": True}
    obs3 = {"ts": now - 10, "zooid_name": "z3", "ok": True}

    cache.append(obs1)
    cache.append(obs2)
    cache.append(obs3)

    recent_60s = cache.get_recent(seconds=60)
    assert len(recent_60s) == 2

    recent_20s = cache.get_recent(seconds=20)
    assert len(recent_20s) == 1


def test_thread_safety():
    """Test cache is thread-safe for concurrent append/read."""
    import threading

    cache = ObservationCache(window_seconds=60)
    errors = []

    def writer():
        try:
            for i in range(100):
                cache.append({"ts": time.time(), "idx": i, "ok": True})
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(100):
                _ = cache.get_recent()
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=reader),
        threading.Thread(target=reader)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread safety errors: {errors}"
    assert len(cache.get_recent()) > 0
