import pytest
import json
from pathlib import Path
from src.orchestration.core.curiosity_processor import process_curiosity_feed


@pytest.fixture
def test_data_dir(tmp_path):
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()

    intents_dir = tmp_path / "intents"
    intents_dir.mkdir()

    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()

    return {
        "feed": feed_dir,
        "intents": intents_dir,
        "issues": issues_dir
    }


def test_high_autonomy_emits_both_intents(test_data_dir, monkeypatch):
    feed_file = test_data_dir["feed"] / "curiosity_feed.json"

    monkeypatch.setattr("src.kloros.orchestration.curiosity_processor.CURIOSITY_FEED", feed_file)
    monkeypatch.setattr("src.kloros.orchestration.curiosity_processor.INTENT_DIR", test_data_dir["intents"])
    monkeypatch.setattr("src.kloros.orchestration.curiosity_processor.PROCESSED_QUESTIONS", test_data_dir["feed"] / "processed.jsonl")

    question = {
        "id": "orphaned_queue_test",
        "question": "Queue 'test_queue' produced but never consumed",
        "hypothesis": "ORPHANED_QUEUE_TEST",
        "autonomy": 3,
        "evidence": ["Produced in: /home/kloros/src/test.py"],
        "priority": 8,
        "value_estimate": 10.0,
        "cost": 2.0,
        "action_class": "propose_fix"
    }

    feed_data = {"questions": [question]}
    feed_file.write_text(json.dumps(feed_data))

    result = process_curiosity_feed()

    intents = list(test_data_dir["intents"].glob("*.json"))
    assert len(intents) == 2

    intent_types = []
    for intent_file in intents:
        data = json.loads(intent_file.read_text())
        intent_types.append(data["intent_type"])

    assert "integration_fix" in intent_types
    assert "spica_spawn_request" in intent_types


def test_low_autonomy_emits_only_integration_fix(test_data_dir, monkeypatch):
    feed_file = test_data_dir["feed"] / "curiosity_feed.json"

    monkeypatch.setattr("src.kloros.orchestration.curiosity_processor.CURIOSITY_FEED", feed_file)
    monkeypatch.setattr("src.kloros.orchestration.curiosity_processor.INTENT_DIR", test_data_dir["intents"])
    monkeypatch.setattr("src.kloros.orchestration.curiosity_processor.PROCESSED_QUESTIONS", test_data_dir["feed"] / "processed.jsonl")

    question = {
        "id": "orphaned_queue_low",
        "question": "Queue 'low_queue' produced but never consumed",
        "hypothesis": "ORPHANED_QUEUE_LOW",
        "autonomy": 2,
        "evidence": ["Produced in: /home/kloros/src/test.py"],
        "priority": 8,
        "value_estimate": 10.0,
        "cost": 2.0,
        "action_class": "propose_fix"
    }

    feed_data = {"questions": [question]}
    feed_file.write_text(json.dumps(feed_data))

    result = process_curiosity_feed()

    intents = list(test_data_dir["intents"].glob("*.json"))
    assert len(intents) == 1

    intent_data = json.loads(intents[0].read_text())
    assert intent_data["intent_type"] == "integration_fix"
