import pytest
import json
import tempfile
from pathlib import Path
from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor


def test_monitor_initialization():
    """Test CapabilityDiscoveryMonitor initialization."""
    monitor = CapabilityDiscoveryMonitor()

    assert monitor is not None
    assert hasattr(monitor, 'scanners')
    assert isinstance(monitor.scanners, list)


def test_monitor_loads_scanner_state():
    """Test monitor loads scanner state from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "scanner_state.json"
        patterns_path = Path(tmpdir) / "operation_patterns.jsonl"

        test_state = {
            "TestScanner": {
                "last_run": 1234567890.0,
                "suspended": False
            }
        }
        with open(state_path, 'w') as f:
            json.dump(test_state, f)

        monitor = CapabilityDiscoveryMonitor(
            scanner_state_path=state_path,
            operation_patterns_path=patterns_path
        )

        assert "TestScanner" in monitor.scanner_state
        assert monitor.scanner_state["TestScanner"]["last_run"] == 1234567890.0


def test_monitor_loads_operation_patterns():
    """Test monitor loads operation patterns from disk."""
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "scanner_state.json"
        patterns_path = Path(tmpdir) / "operation_patterns.jsonl"

        with open(patterns_path, 'w') as f:
            recent = {
                "timestamp": time.time() - 86400,
                "operation": "grep",
                "file_size": 1000000
            }
            f.write(json.dumps(recent) + '\n')

            old = {
                "timestamp": time.time() - (8 * 86400),
                "operation": "grep",
                "file_size": 500000
            }
            f.write(json.dumps(old) + '\n')

        monitor = CapabilityDiscoveryMonitor(
            scanner_state_path=state_path,
            operation_patterns_path=patterns_path
        )

        assert "grep" in monitor.operation_patterns
        assert len(monitor.operation_patterns["grep"]) == 1


def test_monitor_discovers_scanners():
    """Test monitor discovers available scanners."""
    monitor = CapabilityDiscoveryMonitor()

    assert len(monitor.scanners) > 0

    scanner_names = [s.get_metadata().name for s in monitor.scanners]
    assert 'PyPIScanner' in scanner_names


def test_monitor_restores_scanner_state():
    """Test monitor restores scanner state from disk."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "scanner_state.json"
        patterns_path = Path(tmpdir) / "operation_patterns.jsonl"

        test_state = {
            "PyPIScanner": {
                "last_run": 1234567890.0,
                "suspended": False
            }
        }
        with open(state_path, 'w') as f:
            json.dump(test_state, f)

        monitor = CapabilityDiscoveryMonitor(
            scanner_state_path=state_path,
            operation_patterns_path=patterns_path
        )

        pypi_scanner = None
        for scanner in monitor.scanners:
            if scanner.get_metadata().name == 'PyPIScanner':
                pypi_scanner = scanner
                break

        assert pypi_scanner is not None
        assert pypi_scanner.last_run == 1234567890.0
        assert pypi_scanner.suspended is False
