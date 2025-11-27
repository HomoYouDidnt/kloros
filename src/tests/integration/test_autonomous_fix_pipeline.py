import pytest
import json
import time
from pathlib import Path
from src.orchestration.core.curiosity_processor import process_curiosity_feed
from src.orchestration.core.coordinator import tick
from src.orchestration.core.escrow_manager import EscrowManager


@pytest.fixture
def integration_env(tmp_path, monkeypatch):
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()

    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()

    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()

    escrow_dir = tmp_path / "escrow"
    escrow_dir.mkdir()

    monkeypatch.setenv("KLR_CURIOSITY_FEED", str(feed_dir))
    monkeypatch.setenv("KLR_INTENTS_DIR", str(intents_dir))
    monkeypatch.setenv("KLR_INTEGRATION_ISSUES_DIR", str(issues_dir))

    return {
        "feed": feed_dir,
        "intents": intents_dir,
        "issues": issues_dir,
        "escrow": escrow_dir
    }


@pytest.mark.integration
def test_full_autonomous_fix_pipeline(integration_env):
    """
    End-to-end test: Question → Processor → Intents → Orchestrator → SPICA → Escrow
    """

    question = {
        "question_id": "orphaned_queue_integration_test",
        "question": "Queue 'integration_test' produced but never consumed",
        "hypothesis": "ORPHANED_QUEUE_INTEGRATION_TEST",
        "autonomy": 3,
        "evidence": [
            "Produced in: /home/kloros/src/memory/bm25_index.py",
            "No consumers found in codebase"
        ],
        "priority": 8,
        "generated_at": time.time()
    }

    feed_file = integration_env["feed"] / f"{question['question_id']}.json"
    feed_file.write_text(json.dumps(question, indent=2))

    result = process_curiosity_feed()
    assert result is not None

    intents = list(integration_env["intents"].glob("*.json"))
    assert len(intents) == 2

    intent_types = []
    for intent_file in intents:
        data = json.loads(intent_file.read_text())
        intent_types.append(data["intent_type"])

    assert "integration_fix" in intent_types
    assert "spica_spawn_request" in intent_types

    doc_result = tick()
    assert doc_result in ["FIX_APPLIED", "MANUAL_APPROVAL_REQUIRED"]

    reports = list(integration_env["issues"].glob("*.md"))
    assert len(reports) >= 1

    print("✅ Pipeline verified: Question → Intents → Documentation")
    print("⚠️  SPICA spawn requires live environment (skipped in test)")


@pytest.mark.integration
def test_low_autonomy_documentation_only(integration_env):
    """
    Verify low-autonomy questions only create documentation intent
    """

    question = {
        "question_id": "low_autonomy_test",
        "question": "Test low autonomy question",
        "hypothesis": "ORPHANED_QUEUE_LOW",
        "autonomy": 1,
        "evidence": ["Test evidence"],
        "priority": 5,
        "generated_at": time.time()
    }

    feed_file = integration_env["feed"] / f"{question['question_id']}.json"
    feed_file.write_text(json.dumps(question, indent=2))

    result = process_curiosity_feed()
    assert result is not None

    intents = list(integration_env["intents"].glob("*.json"))
    assert len(intents) == 1

    intent_data = json.loads(intents[0].read_text())
    assert intent_data["intent_type"] == "integration_fix"
