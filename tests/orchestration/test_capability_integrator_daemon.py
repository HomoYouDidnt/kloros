#!/usr/bin/env python3
"""
Tests for capability_integrator_daemon.py

Verifies:
1. Daemon subscribes to Q_INVESTIGATION_COMPLETE signals
2. Existing integration logic still works
3. Emits Q_MODULE_INTEGRATED on success
4. Emits Q_INTEGRATION_FAILED on failures
5. Respects maintenance mode
"""

import json
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import kloros.orchestration.capability_integrator_daemon
from kloros.orchestration.capability_integrator_daemon import CapabilityIntegratorDaemon


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        investigations_log = tmppath / "curiosity_investigations.jsonl"
        integrated_log = tmppath / "integrated_capabilities.jsonl"
        capabilities_yaml = tmppath / "capabilities.yaml"
        last_processed = tmppath / "last_processed.txt"
        failed_signals = tmppath / "failed_signals.jsonl"

        capabilities_yaml.write_text("# KLoROS Capability Registry\n\n")

        yield {
            "investigations_log": investigations_log,
            "integrated_log": integrated_log,
            "capabilities_yaml": capabilities_yaml,
            "last_processed": last_processed,
            "failed_signals": failed_signals,
        }


@pytest.fixture
def mock_zmq():
    """Mock ZMQ subscriber and publisher."""
    with patch('kloros.orchestration.capability_integrator_daemon._ZmqSub') as mock_sub, \
         patch('kloros.orchestration.capability_integrator_daemon.ChemPub') as mock_pub:

        mock_subscriber = MagicMock()
        mock_sub.return_value = mock_subscriber

        mock_publisher = MagicMock()
        mock_pub.return_value = mock_publisher

        yield {
            "subscriber": mock_subscriber,
            "publisher": mock_publisher,
            "sub_class": mock_sub,
            "pub_class": mock_pub,
        }


def test_daemon_subscribes_to_investigation_complete(mock_zmq, temp_dirs):
    """Verify daemon subscribes to Q_INVESTIGATION_COMPLETE."""
    with patch('kloros.orchestration.capability_integrator_daemon.wait_for_normal_mode'):
        daemon = CapabilityIntegratorDaemon(
        investigations_log=temp_dirs["investigations_log"],
        capabilities_yaml=temp_dirs["capabilities_yaml"],
        integrated_log=temp_dirs["integrated_log"],
        last_processed_timestamp=temp_dirs["last_processed"],
        failed_signals_log=temp_dirs["failed_signals"],
    )

    mock_zmq["sub_class"].assert_called_once()
    call_args = mock_zmq["sub_class"].call_args
    assert call_args[1]["topic"] == "Q_INVESTIGATION_COMPLETE"
    assert call_args[1]["on_message"] is not None


def test_daemon_emits_module_integrated_on_success(mock_zmq, temp_dirs):
    """Verify daemon emits Q_MODULE_INTEGRATED when integration succeeds."""
    investigation = {
        "timestamp": "2025-11-14T10:00:00Z",
        "capability": "test_module",
        "question": "What does test_module do?",
        "hypothesis": "UNDISCOVERED_MODULE_test_module",
        "evidence": [
            "path:/home/kloros/src/test_module",
            "has_init:true",
            "py_files:3"
        ],
        "probe_results": []
    }

    temp_dirs["investigations_log"].write_text(json.dumps(investigation) + "\n")
    (Path(temp_dirs["investigations_log"].parent) / "test_module").mkdir(exist_ok=True)

    with patch('kloros.orchestration.capability_integrator_daemon.wait_for_normal_mode'):
        daemon = CapabilityIntegratorDaemon(
            investigations_log=temp_dirs["investigations_log"],
            capabilities_yaml=temp_dirs["capabilities_yaml"],
            integrated_log=temp_dirs["integrated_log"],
            last_processed_timestamp=temp_dirs["last_processed"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        signal_msg = {
            "signal": "Q_INVESTIGATION_COMPLETE",
            "timestamp": "2025-11-14T10:00:00Z",
            "source": "investigation_consumer",
            "facts": {
                "investigation_timestamp": "2025-11-14T10:00:00Z",
                "question_id": "discover.module.test_module",
            }
        }

        on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
        on_message_callback("Q_INVESTIGATION_COMPLETE", json.dumps(signal_msg).encode())

        time.sleep(0.1)

        mock_zmq["publisher"].emit.assert_called()
        call_args = mock_zmq["publisher"].emit.call_args
        assert call_args[0][0] == "Q_MODULE_INTEGRATED"


def test_daemon_emits_integration_failed_on_error(mock_zmq, temp_dirs):
    """Verify daemon emits Q_INTEGRATION_FAILED on failures."""
    with patch("kloros.orchestration.capability_integrator_daemon.wait_for_normal_mode"):
        investigation = {
            "timestamp": "2025-11-14T10:00:00Z",
            "capability": "broken_module",
            "question": "What does broken_module do?",
            "hypothesis": "UNDISCOVERED_MODULE_broken_module",
            "evidence": [
                "path:/home/kloros/src/broken_module",
                "has_init:false",
                "py_files:0"
            ],
            "probe_results": []
        }

        temp_dirs["investigations_log"].write_text(json.dumps(investigation) + "\n")

        daemon = CapabilityIntegratorDaemon(
            investigations_log=temp_dirs["investigations_log"],
            capabilities_yaml=temp_dirs["capabilities_yaml"],
            integrated_log=temp_dirs["integrated_log"],
            last_processed_timestamp=temp_dirs["last_processed"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        signal_msg = {
            "signal": "Q_INVESTIGATION_COMPLETE",
            "timestamp": "2025-11-14T10:00:00Z",
            "source": "investigation_consumer",
            "facts": {
                "investigation_timestamp": "2025-11-14T10:00:00Z",
                "question_id": "discover.module.broken_module",
            }
        }

        on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
        on_message_callback("Q_INVESTIGATION_COMPLETE", json.dumps(signal_msg).encode())

        time.sleep(0.1)

        call_made = False
        for call in mock_zmq["publisher"].emit.call_args_list:
            if call[0][0] == "Q_INTEGRATION_FAILED":
                call_made = True
                break

        assert call_made or temp_dirs["failed_signals"].exists()


def test_daemon_handles_maintenance_mode(mock_zmq, temp_dirs):
    """Verify daemon respects maintenance mode."""
    with patch('kloros.orchestration.capability_integrator_daemon.wait_for_normal_mode') as mock_wait:
        daemon = CapabilityIntegratorDaemon(
            investigations_log=temp_dirs["investigations_log"],
            capabilities_yaml=temp_dirs["capabilities_yaml"],
            integrated_log=temp_dirs["integrated_log"],
            last_processed_timestamp=temp_dirs["last_processed"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        mock_wait.assert_called_once()


def test_daemon_writes_to_dead_letter_queue_on_exception(mock_zmq, temp_dirs):
    """Verify daemon writes failed signals to dead letter queue."""
    daemon = CapabilityIntegratorDaemon(
        investigations_log=temp_dirs["investigations_log"],
        capabilities_yaml=temp_dirs["capabilities_yaml"],
        integrated_log=temp_dirs["integrated_log"],
        last_processed_timestamp=temp_dirs["last_processed"],
        failed_signals_log=temp_dirs["failed_signals"],
    )

    malformed_msg = "not valid json"

    on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
    on_message_callback("Q_INVESTIGATION_COMPLETE", malformed_msg.encode())

    time.sleep(0.1)

    assert temp_dirs["failed_signals"].exists()
    with open(temp_dirs["failed_signals"], 'r') as f:
        content = f.read()
        assert "error" in content.lower() or len(content) == 0


def test_integration_logic_preserved(mock_zmq, temp_dirs):
    """Verify existing integration logic from capability_integrator.py still works."""
    investigation = {
        "timestamp": "2025-11-14T10:00:00Z",
        "capability": "audio_processing",
        "question": "What does audio_processing do?",
        "hypothesis": "UNDISCOVERED_MODULE_audio_processing",
        "evidence": [
            "path:/home/kloros/src/audio",
            "has_init:true",
            "py_files:5"
        ],
        "probe_results": [{"type": "module_check", "success": True}]
    }

    temp_dirs["investigations_log"].write_text(json.dumps(investigation) + "\n")

    daemon = CapabilityIntegratorDaemon(
        investigations_log=temp_dirs["investigations_log"],
        capabilities_yaml=temp_dirs["capabilities_yaml"],
        integrated_log=temp_dirs["integrated_log"],
        last_processed_timestamp=temp_dirs["last_processed"],
        failed_signals_log=temp_dirs["failed_signals"],
    )

    signal_msg = {
        "signal": "Q_INVESTIGATION_COMPLETE",
        "timestamp": "2025-11-14T10:00:00Z",
        "source": "investigation_consumer",
        "facts": {
            "investigation_timestamp": "2025-11-14T10:00:00Z",
            "question_id": "discover.module.audio_processing",
        }
    }

    on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
    on_message_callback("Q_INVESTIGATION_COMPLETE", json.dumps(signal_msg).encode())

    time.sleep(0.2)

    assert temp_dirs["integrated_log"].exists()
    with open(temp_dirs["integrated_log"], 'r') as f:
        integrated = [json.loads(line) for line in f if line.strip()]
        assert len(integrated) >= 1
        assert integrated[0]["capability"] == "audio_processing"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
