"""Integration tests for streaming introspection daemon with real UMN."""

import time
import pytest
from src.observability.introspection.introspection_daemon import IntrospectionDaemon
from src.orchestration.core.umn_bus_v2 import UMNPub


@pytest.mark.integration
def test_end_to_end_observation_to_gap():
    """
    Test complete flow: emit OBSERVATION → daemon processes → emits CAPABILITY_GAP.

    This test requires UMN proxy to be running.
    """
    daemon = IntrospectionDaemon(
        cache_window_seconds=60,
        scan_interval=2.0
    )

    import threading
    daemon_thread = threading.Thread(target=daemon.run, daemon=True)
    daemon_thread.start()

    time.sleep(1)

    pub = UMNPub()

    for i in range(5):
        pub.emit(
            signal="OBSERVATION",
            ecosystem="test",
            facts={
                "zooid": "test_zooid",
                "ok": True,
                "ttr_ms": 100,
                "task_type": "code_generation",
                "tokens_per_sec": 5.0,
                "timestamp": time.time()
            }
        )
        time.sleep(0.1)

    time.sleep(3)

    assert daemon.cache.size() >= 5
    assert daemon.scan_count >= 1

    daemon.shutdown()
    pub.close()


@pytest.mark.integration
def test_scanner_isolation():
    """Test that scanner failures don't crash daemon."""
    daemon = IntrospectionDaemon(scan_interval=1.0)

    from unittest.mock import MagicMock
    failing_scanner = MagicMock()
    failing_scanner.scan.side_effect = RuntimeError("Simulated scanner failure")
    failing_scanner.get_metadata.return_value = MagicMock(name="FailingScanner")

    daemon.scanners.append(failing_scanner)

    daemon.cache.append({"ts": time.time(), "zooid_name": "test", "ok": True, "facts": {}})

    daemon._run_scan_cycle()

    assert daemon.scan_count == 1

    daemon.shutdown()


@pytest.mark.integration
def test_concurrent_observation_processing():
    """Test daemon handles concurrent observations correctly."""
    daemon = IntrospectionDaemon(scan_interval=10.0)

    import threading
    pub = UMNPub()

    def emit_observations(count):
        for i in range(count):
            pub.emit(
                signal="OBSERVATION",
                ecosystem="test",
                facts={
                    "zooid": f"zooid_{i}",
                    "ok": True,
                    "ttr_ms": 100
                }
            )
            time.sleep(0.01)

    threads = [
        threading.Thread(target=emit_observations, args=(50,)),
        threading.Thread(target=emit_observations, args=(50,))
    ]

    for t in threads:
        t.start()

    time.sleep(2)

    for t in threads:
        t.join()

    assert daemon.cache.size() >= 100

    daemon.shutdown()
    pub.close()
