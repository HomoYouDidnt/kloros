import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.orchestration.core.coordinator import tick


@pytest.fixture
def mock_spica_intent(tmp_path):
    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()

    intent = {
        "schema": "orchestration.intent/v1",
        "intent_type": "spica_spawn_request",
        "priority": 8,
        "data": {
            "question_id": "orphaned_queue_test",
            "question": "Queue 'test' orphaned",
            "hypothesis": "ORPHANED_QUEUE_TEST",
            "fix_context": {
                "evidence": ["Produced in: /home/kloros/src/test.py"],
                "target_files": ["/home/kloros/src/test.py"],
                "proposed_changes": "Add consumer"
            },
            "validation": {
                "run_tests": True,
                "test_command": "pytest",
                "require_pass": True
            }
        }
    }

    intent_file = intents_dir / "spica_spawn_test.json"
    intent_file.write_text(json.dumps(intent))

    return {"intents_dir": intents_dir, "intent_file": intent_file}


@patch("src.orchestration.coordinator._archive_intent")
@patch("src.orchestration.state_manager.acquire")
@patch("src.orchestration.state_manager.release")
@patch("src.orchestration.intent_queue.process_queue")
@patch("src.orchestration.coordinator._has_idle_intents")
@patch("src.orchestration.winner_deployer.run_deployment_cycle")
@patch("src.orchestration.curiosity_processor.process_curiosity_feed")
@patch("src.orchestration.coordinator._is_orchestration_enabled")
@patch("src.dream.config_tuning.llm_code_generator.LLMCodeGenerator")
@patch("src.dream.config_tuning.spica_spawner.spawn_instance")
@patch("src.dream.config_tuning.spica_spawner.apply_code_patch")
@patch("src.dream.config_tuning.spica_spawner.run_tests_in_instance")
@patch("src.orchestration.escrow_manager.EscrowManager")
def test_spica_spawn_handler_success(
    mock_escrow,
    mock_run_tests,
    mock_apply_patch,
    mock_spawn,
    mock_llm,
    mock_orch_enabled,
    mock_curiosity,
    mock_winner,
    mock_has_intents,
    mock_queue,
    mock_release,
    mock_acquire,
    mock_archive,
    mock_spica_intent,
    monkeypatch
):
    mock_acquire.return_value = Mock()
    mock_release.return_value = None
    mock_archive.return_value = None
    monkeypatch.setenv("KLR_INTENTS_DIR", str(mock_spica_intent["intents_dir"]))

    mock_orch_enabled.return_value = True
    mock_curiosity.return_value = {"intents_emitted": 0}
    mock_winner.return_value = {"deployed": 0}
    mock_has_intents.return_value = True

    mock_llm_instance = Mock()
    mock_llm_instance.generate_fix_patch.return_value = "patched code"
    mock_llm.return_value = mock_llm_instance

    mock_spawn_result = Mock()
    mock_spawn_result.instance_dir = Path("/tmp/spica-test")
    mock_spawn_result.spica_id = "spica-test123"
    mock_spawn.return_value = mock_spawn_result

    mock_apply_patch.return_value = True
    mock_run_tests.return_value = {"success": True, "output": "All tests passed"}

    mock_escrow_instance = Mock()
    mock_escrow_instance.add_to_escrow.return_value = "escrow-abc"
    mock_escrow.return_value = mock_escrow_instance

    mock_queue.side_effect = [
        {
            "next_intent": mock_spica_intent["intent_file"],
            "queue_depth": 1,
            "stats": {"deduplicated": 0, "pruned": 0, "dropped": 0}
        },
        {
            "next_intent": None,
            "queue_depth": 0,
            "stats": {"deduplicated": 0, "pruned": 0, "dropped": 0}
        }
    ]

    result = tick()

    assert result == "CURIOSITY_SPAWNED"
    mock_llm_instance.generate_fix_patch.assert_called_once()
    mock_spawn.assert_called_once()
    mock_apply_patch.assert_called_once()
    mock_run_tests.assert_called_once()
    mock_escrow_instance.add_to_escrow.assert_called_once()


@patch("src.orchestration.coordinator._archive_intent")
@patch("src.orchestration.state_manager.acquire")
@patch("src.orchestration.state_manager.release")
@patch("src.orchestration.intent_queue.process_queue")
@patch("src.orchestration.coordinator._has_idle_intents")
@patch("src.orchestration.winner_deployer.run_deployment_cycle")
@patch("src.orchestration.curiosity_processor.process_curiosity_feed")
@patch("src.orchestration.coordinator._is_orchestration_enabled")
@patch("src.dream.config_tuning.llm_code_generator.LLMCodeGenerator")
def test_spica_spawn_handler_llm_failure(
    mock_llm,
    mock_orch_enabled,
    mock_curiosity,
    mock_winner,
    mock_has_intents,
    mock_queue,
    mock_release,
    mock_acquire,
    mock_archive,
    mock_spica_intent,
    monkeypatch
):
    mock_acquire.return_value = Mock()
    mock_release.return_value = None
    mock_archive.return_value = None
    monkeypatch.setenv("KLR_INTENTS_DIR", str(mock_spica_intent["intents_dir"]))

    mock_orch_enabled.return_value = True
    mock_curiosity.return_value = {"intents_emitted": 0}
    mock_winner.return_value = {"deployed": 0}
    mock_has_intents.return_value = True

    mock_llm_instance = Mock()
    mock_llm_instance.generate_fix_patch.return_value = None
    mock_llm.return_value = mock_llm_instance

    mock_queue.side_effect = [
        {
            "next_intent": mock_spica_intent["intent_file"],
            "queue_depth": 1,
            "stats": {"deduplicated": 0, "pruned": 0, "dropped": 0}
        },
        {
            "next_intent": None,
            "queue_depth": 0,
            "stats": {"deduplicated": 0, "pruned": 0, "dropped": 0}
        }
    ]

    result = tick()

    assert result == "SPICA_SPAWN_FAILED"
    mock_archive.assert_called()


@patch("src.orchestration.coordinator._archive_intent")
@patch("src.orchestration.state_manager.acquire")
@patch("src.orchestration.state_manager.release")
@patch("src.orchestration.intent_queue.process_queue")
@patch("src.orchestration.coordinator._has_idle_intents")
@patch("src.orchestration.winner_deployer.run_deployment_cycle")
@patch("src.orchestration.curiosity_processor.process_curiosity_feed")
@patch("src.orchestration.coordinator._is_orchestration_enabled")
@patch("src.dream.config_tuning.spica_spawner.spawn_instance")
@patch("src.dream.config_tuning.llm_code_generator.LLMCodeGenerator")
def test_spica_spawn_handler_no_target_files(
    mock_llm,
    mock_spawn,
    mock_orch_enabled,
    mock_curiosity,
    mock_winner,
    mock_has_intents,
    mock_queue,
    mock_release,
    mock_acquire,
    mock_archive,
    tmp_path,
    monkeypatch
):
    mock_acquire.return_value = Mock()
    mock_release.return_value = None
    mock_archive.return_value = None
    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()

    intent = {
        "schema": "orchestration.intent/v1",
        "intent_type": "spica_spawn_request",
        "priority": 8,
        "data": {
            "question_id": "test_no_files",
            "question": "Test question",
            "hypothesis": "TEST_HYPOTHESIS",
            "fix_context": {
                "evidence": ["Some evidence"],
                "target_files": []
            },
            "validation": {
                "run_tests": False
            }
        }
    }

    intent_file = intents_dir / "spica_no_files.json"
    intent_file.write_text(json.dumps(intent))

    monkeypatch.setenv("KLR_INTENTS_DIR", str(intents_dir))

    mock_orch_enabled.return_value = True
    mock_curiosity.return_value = {"intents_emitted": 0}
    mock_winner.return_value = {"deployed": 0}
    mock_has_intents.return_value = True

    mock_queue.side_effect = [
        {
            "next_intent": intent_file,
            "queue_depth": 1,
            "stats": {"deduplicated": 0, "pruned": 0, "dropped": 0}
        },
        {
            "next_intent": None,
            "queue_depth": 0,
            "stats": {"deduplicated": 0, "pruned": 0, "dropped": 0}
        }
    ]

    result = tick()

    assert result == "SPICA_SPAWN_FAILED"
    mock_archive.assert_called()
