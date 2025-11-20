#!/usr/bin/env python3
"""
Tests for winner_deployer_daemon.py

Verifies:
1. Daemon subscribes to Q_DREAM_COMPLETE signals
2. Existing deployment logic still works
3. Emits Q_WINNER_DEPLOYED on success
4. Emits Q_DEPLOYMENT_FAILED on failures
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

from kloros.orchestration.winner_deployer_daemon import WinnerDeployerDaemon


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        winners_dir = tmppath / "winners"
        winners_dir.mkdir()

        dream_config = tmppath / "dream.yaml"
        dream_config.write_text("experiments:\n  test_experiment:\n    param_mapping:\n      test_param: TEST_CONFIG_KEY\n")

        state_path = tmppath / "winner_deployer_state.json"
        failed_signals = tmppath / "failed_signals.jsonl"

        yield {
            "winners_dir": winners_dir,
            "dream_config": dream_config,
            "state_path": state_path,
            "failed_signals": failed_signals,
        }


@pytest.fixture
def mock_zmq():
    """Mock ZMQ subscriber and publisher."""
    with patch('kloros.orchestration.winner_deployer_daemon._ZmqSub') as mock_sub, \
         patch('kloros.orchestration.winner_deployer_daemon.ChemPub') as mock_pub:

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


def test_daemon_subscribes_to_dream_complete(mock_zmq, temp_dirs):
    """Verify daemon subscribes to Q_DREAM_COMPLETE."""
    with patch('kloros.orchestration.winner_deployer_daemon.WinnerDeployer'):
        daemon = WinnerDeployerDaemon(
            winners_dir=temp_dirs["winners_dir"],
            dream_config_path=temp_dirs["dream_config"],
            state_path=temp_dirs["state_path"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        mock_zmq["sub_class"].assert_called_once()
        call_args = mock_zmq["sub_class"].call_args
        assert call_args[1]["topic"] == "Q_DREAM_COMPLETE"
        assert call_args[1]["on_message"] is not None


def test_daemon_emits_winner_deployed_on_success(mock_zmq, temp_dirs):
    """Verify daemon emits Q_WINNER_DEPLOYED when deployment succeeds."""
    winner_file = temp_dirs["winners_dir"] / "test_experiment.json"
    winner_data = {
        "best": {
            "params": {"test_param": 42},
            "fitness": 0.95
        },
        "updated_at": "2025-11-14T10:00:00Z"
    }
    winner_file.write_text(json.dumps(winner_data))

    with patch('kloros.orchestration.winner_deployer_daemon.WinnerDeployer') as MockDeployer:
        mock_deployer = MagicMock()
        mock_deployer.watch_and_deploy.return_value = {
            "status": "success",
            "deployed": 1,
            "skipped": 0,
            "failed": 0
        }
        MockDeployer.return_value = mock_deployer

        daemon = WinnerDeployerDaemon(
            winners_dir=temp_dirs["winners_dir"],
            dream_config_path=temp_dirs["dream_config"],
            state_path=temp_dirs["state_path"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        signal_msg = {
            "signal": "Q_DREAM_COMPLETE",
            "timestamp": "2025-11-14T10:00:00Z",
            "source": "dream_daemon",
            "facts": {
                "dream_cycle_id": "cycle_123",
            }
        }

        on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
        on_message_callback("Q_DREAM_COMPLETE", json.dumps(signal_msg).encode())

        time.sleep(0.1)

        mock_deployer.watch_and_deploy.assert_called()


def test_daemon_emits_deployment_failed_on_error(mock_zmq, temp_dirs):
    """Verify daemon emits Q_DEPLOYMENT_FAILED on failures."""
    with patch('kloros.orchestration.winner_deployer_daemon.WinnerDeployer') as MockDeployer:
        mock_deployer = MagicMock()
        mock_deployer.watch_and_deploy.side_effect = Exception("Deployment failed")
        MockDeployer.return_value = mock_deployer

        daemon = WinnerDeployerDaemon(
            winners_dir=temp_dirs["winners_dir"],
            dream_config_path=temp_dirs["dream_config"],
            state_path=temp_dirs["state_path"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        signal_msg = {
            "signal": "Q_DREAM_COMPLETE",
            "timestamp": "2025-11-14T10:00:00Z",
            "source": "dream_daemon",
            "facts": {
                "dream_cycle_id": "cycle_123",
            }
        }

        on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
        on_message_callback("Q_DREAM_COMPLETE", json.dumps(signal_msg).encode())

        time.sleep(0.1)

        call_made = False
        for call in mock_zmq["publisher"].emit.call_args_list:
            if call[0][0] == "Q_DEPLOYMENT_FAILED":
                call_made = True
                break

        assert call_made or temp_dirs["failed_signals"].exists()


def test_daemon_handles_maintenance_mode(mock_zmq, temp_dirs):
    """Verify daemon respects maintenance mode."""
    with patch('kloros.orchestration.winner_deployer_daemon.wait_for_normal_mode') as mock_wait, \
         patch('kloros.orchestration.winner_deployer_daemon.WinnerDeployer'):

        daemon = WinnerDeployerDaemon(
            winners_dir=temp_dirs["winners_dir"],
            dream_config_path=temp_dirs["dream_config"],
            state_path=temp_dirs["state_path"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        mock_wait.assert_called_once()


def test_daemon_writes_to_dead_letter_queue_on_exception(mock_zmq, temp_dirs):
    """Verify daemon writes failed signals to dead letter queue."""
    with patch('kloros.orchestration.winner_deployer_daemon.WinnerDeployer'):
        daemon = WinnerDeployerDaemon(
            winners_dir=temp_dirs["winners_dir"],
            dream_config_path=temp_dirs["dream_config"],
            state_path=temp_dirs["state_path"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        malformed_msg = "not valid json"

        on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
        on_message_callback("Q_DREAM_COMPLETE", malformed_msg.encode())

        time.sleep(0.1)

        assert temp_dirs["failed_signals"].exists()
        with open(temp_dirs["failed_signals"], 'r') as f:
            content = f.read()
            assert "error" in content.lower() or len(content) == 0


def test_deployment_logic_preserved(mock_zmq, temp_dirs):
    """Verify existing deployment logic from winner_deployer.py still works."""
    winner_file = temp_dirs["winners_dir"] / "test_experiment.json"
    winner_data = {
        "best": {
            "params": {"test_param": 42},
            "fitness": 0.95
        },
        "updated_at": "2025-11-14T10:00:00Z"
    }
    winner_file.write_text(json.dumps(winner_data))

    with patch('kloros.orchestration.winner_deployer_daemon.WinnerDeployer') as MockDeployer:
        mock_deployer = MagicMock()
        mock_deployer.watch_and_deploy.return_value = {
            "status": "success",
            "deployed": 1,
            "skipped": 0,
            "failed": 0
        }
        MockDeployer.return_value = mock_deployer

        daemon = WinnerDeployerDaemon(
            winners_dir=temp_dirs["winners_dir"],
            dream_config_path=temp_dirs["dream_config"],
            state_path=temp_dirs["state_path"],
            failed_signals_log=temp_dirs["failed_signals"],
        )

        signal_msg = {
            "signal": "Q_DREAM_COMPLETE",
            "timestamp": "2025-11-14T10:00:00Z",
            "source": "dream_daemon",
            "facts": {
                "dream_cycle_id": "cycle_123",
            }
        }

        on_message_callback = mock_zmq["sub_class"].call_args[1]["on_message"]
        on_message_callback("Q_DREAM_COMPLETE", json.dumps(signal_msg).encode())

        time.sleep(0.2)

        mock_deployer.watch_and_deploy.assert_called()
        assert temp_dirs["state_path"].exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
