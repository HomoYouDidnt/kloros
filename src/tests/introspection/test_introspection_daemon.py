"""Tests for IntrospectionDaemon - streaming scanner orchestrator."""

import time
import pytest
from unittest.mock import MagicMock, patch
from src.observability.introspection.introspection_daemon import IntrospectionDaemon


def test_daemon_initialization():
    """Test daemon initializes with correct scanners and cache."""
    with patch('kloros.introspection.introspection_daemon.UMNSub'), \
         patch('kloros.introspection.introspection_daemon.UMNPub'):
        daemon = IntrospectionDaemon()

        assert daemon.cache is not None
        assert len(daemon.scanners) == 5
        assert daemon.scan_interval == 5.0
        assert daemon.running is True


def test_observation_caching():
    """Test daemon caches observations from UMNSub callback."""
    with patch('kloros.introspection.introspection_daemon.UMNSub'), \
         patch('kloros.introspection.introspection_daemon.UMNPub'):
        daemon = IntrospectionDaemon()

        obs_msg = {
            "signal": "OBSERVATION",
            "facts": {
                "zooid": "test_zooid",
                "ok": True,
                "ttr_ms": 100
            },
            "ts": time.time()
        }

        daemon._on_observation(obs_msg)

        cached = daemon.cache.get_recent()
        assert len(cached) == 1
        assert cached[0]["zooid_name"] == "test_zooid"


def test_scan_cycle_execution():
    """Test scan cycle runs scanners and emits gaps."""
    with patch('kloros.introspection.introspection_daemon.UMNSub'), \
         patch('kloros.introspection.introspection_daemon.UMNPub') as mock_pub:

        daemon = IntrospectionDaemon()

        now = time.time()
        for i in range(5):
            daemon.cache.append({
                "ts": now - i,
                "zooid_name": f"zooid_{i}",
                "ok": True,
                "ttr_ms": 100,
                "facts": {}
            })

        daemon._run_scan_cycle()

        assert daemon.scan_count > 0


def test_scanner_timeout_protection():
    """Test scan cycle has timeout protection for hanging scanners."""
    with patch('kloros.introspection.introspection_daemon.UMNSub'), \
         patch('kloros.introspection.introspection_daemon.UMNPub'):
        daemon = IntrospectionDaemon()
        daemon.scanner_timeout = 0.1

        mock_scanner = MagicMock()
        mock_scanner.scan.side_effect = lambda: time.sleep(1)
        mock_scanner.get_metadata.return_value = MagicMock(name="HangingScanner")

        daemon.scanners = [mock_scanner]

        start = time.time()
        daemon._run_scan_cycle()
        elapsed = time.time() - start

        assert elapsed < 0.5
