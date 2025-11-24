"""Unit tests for Intent zooid - test in isolation with mocked ChemBus."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.chembus_mock import MockChemPub, MockChemSub
from src.kloros_voice_intent import IntentZooid


@pytest.fixture
def zooid(monkeypatch):
    """Create IntentZooid with mocked dependencies."""
    monkeypatch.setenv("KLR_ENABLE_INTENT", "1")

    with patch('src.kloros_voice_intent.ChemPub', MockChemPub), \
         patch('src.kloros_voice_intent.ChemSub', MockChemSub):

        zooid = IntentZooid()
        yield zooid

        zooid.shutdown()


class TestIntentZooidInit:
    """Test IntentZooid initialization."""

    def test_init_sets_zooid_name(self, zooid):
        """Test that zooid name is set correctly."""
        assert zooid.zooid_name == "kloros-voice-intent"
        assert zooid.niche == "voice.intent"

    def test_init_statistics(self, zooid):
        """Test that statistics are initialized."""
        assert zooid.stats["total_classifications"] == 0
        assert zooid.stats["commands_detected"] == 0
        assert zooid.stats["questions_detected"] == 0
        assert zooid.stats["conversations_detected"] == 0

    def test_init_command_patterns(self, zooid):
        """Test that command patterns are loaded."""
        assert "enrollment" in zooid.command_patterns
        assert "identity" in zooid.command_patterns
        assert "system_query" in zooid.command_patterns
        assert "exit" in zooid.command_patterns

        assert len(zooid.command_patterns["enrollment"]) > 0
        assert len(zooid.command_patterns["identity"]) > 0

    def test_init_question_patterns(self, zooid):
        """Test that question patterns are loaded."""
        assert len(zooid.question_patterns) > 0
        assert any("what" in pattern for pattern in zooid.question_patterns)


class TestIntentZooidStart:
    """Test IntentZooid startup."""

    def test_start_emits_ready_signal(self, zooid):
        """Test that start() emits VOICE.INTENT.READY signal."""
        zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.INTENT.READY") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.INTENT.READY")
        assert msg is not None
        assert msg.ecosystem == "voice"
        assert msg.facts["zooid"] == "kloros-voice-intent"
        assert "command_types" in msg.facts
        assert "patterns_count" in msg.facts

    def test_start_subscribes_to_stt_transcription(self, zooid):
        """Test that start() subscribes to VOICE.STT.TRANSCRIPTION."""
        zooid.start()

        assert hasattr(zooid, 'transcription_sub')
        assert zooid.transcription_sub.topic == "VOICE.STT.TRANSCRIPTION"

    def test_start_disabled_intent(self, monkeypatch):
        """Test that Intent can be disabled via environment."""
        monkeypatch.setenv("KLR_ENABLE_INTENT", "0")

        with patch('src.kloros_voice_intent.ChemPub', MockChemPub), \
             patch('src.kloros_voice_intent.ChemSub', MockChemSub):
            zooid = IntentZooid()
            zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.INTENT.READY") == 0


class TestIntentClassification:
    """Test intent classification functionality."""

    def test_classify_enrollment_command(self, zooid):
        """Test classification of enrollment command."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "enroll me"
        )

        assert intent_type == "command"
        assert confidence == 0.95
        assert command_type == "enrollment"

    def test_classify_identity_command(self, zooid):
        """Test classification of identity command."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "what is my name"
        )

        assert intent_type == "command"
        assert confidence == 0.95
        assert command_type == "identity"

    def test_classify_system_query_command(self, zooid):
        """Test classification of system query command."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "what is your name"
        )

        assert intent_type == "command"
        assert confidence == 0.95
        assert command_type == "system_query"

    def test_classify_exit_command(self, zooid):
        """Test classification of exit command."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "exit"
        )

        assert intent_type == "command"
        assert confidence == 0.95
        assert command_type == "exit"

    def test_classify_question(self, zooid):
        """Test classification of question."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "what is the weather today?"
        )

        assert intent_type == "question"
        assert confidence == 0.85
        assert command_type is None

    def test_classify_conversation(self, zooid):
        """Test classification of conversational text."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "hello there"
        )

        assert intent_type == "conversation"
        assert confidence == 0.70
        assert command_type is None

    def test_command_priority_over_question(self, zooid):
        """Test that commands have priority over questions."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "what is my name?"
        )

        assert intent_type == "command"
        assert command_type == "identity"


class TestParameterExtraction:
    """Test parameter extraction from commands."""

    def test_extract_name_from_identity(self, zooid):
        """Test extracting name from 'my name is X' command."""
        intent_type, confidence, command_type, parameters = zooid._classify_intent(
            "my name is Alice"
        )

        assert intent_type == "command"
        assert command_type == "identity"
        assert "name" in parameters
        assert parameters["name"] == "Alice"

    def test_extract_user_from_delete(self, zooid):
        """Test extracting user from delete command."""
        parameters = zooid._extract_parameters(
            "delete user Bob",
            "enrollment"
        )

        assert "target_user" in parameters
        assert parameters["target_user"] == "Bob"

    def test_extract_user_from_remove(self, zooid):
        """Test extracting user from remove command."""
        parameters = zooid._extract_parameters(
            "remove user Charlie",
            "enrollment"
        )

        assert "target_user" in parameters
        assert parameters["target_user"] == "Charlie"


class TestIntentSignalEmission:
    """Test ChemBus signal emission for classified intents."""

    def test_on_transcription_emits_classified_signal(self, zooid):
        """Test that transcription handler emits VOICE.INTENT.CLASSIFIED."""
        zooid.start()

        zooid._on_transcription({
            "facts": {
                "text": "enroll me",
                "confidence": 0.95
            },
            "incident_id": "intent-001"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.INTENT.CLASSIFIED") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.INTENT.CLASSIFIED")
        assert msg.facts["text"] == "enroll me"
        assert msg.facts["intent_type"] == "command"
        assert msg.facts["command_type"] == "enrollment"
        assert msg.incident_id == "intent-001"

    def test_on_transcription_updates_statistics(self, zooid):
        """Test that transcription updates statistics."""
        zooid.start()

        initial_total = zooid.stats["total_classifications"]
        initial_commands = zooid.stats["commands_detected"]

        zooid._on_transcription({
            "facts": {
                "text": "exit",
                "confidence": 0.95
            }
        })

        assert zooid.stats["total_classifications"] == initial_total + 1
        assert zooid.stats["commands_detected"] == initial_commands + 1

    def test_on_transcription_missing_text(self, zooid):
        """Test handling of missing text in transcription."""
        zooid.start()

        zooid._on_transcription({
            "facts": {
                "confidence": 0.95
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.INTENT.CLASSIFIED") == 0


class TestIntentStatistics:
    """Test Intent statistics tracking."""

    def test_get_stats(self, zooid):
        """Test getting Intent statistics."""
        stats = zooid.get_stats()

        assert "total_classifications" in stats
        assert "commands_detected" in stats
        assert "questions_detected" in stats
        assert "conversations_detected" in stats
        assert "average_classification_time" in stats

    def test_statistics_count_correctly(self, zooid):
        """Test that statistics count different intent types correctly."""
        zooid.start()

        zooid._on_transcription({"facts": {"text": "enroll me"}})
        zooid._on_transcription({"facts": {"text": "what is the weather?"}})
        zooid._on_transcription({"facts": {"text": "hello there"}})

        stats = zooid.get_stats()
        assert stats["total_classifications"] == 3
        assert stats["commands_detected"] == 1
        assert stats["questions_detected"] == 1
        assert stats["conversations_detected"] == 1


class TestIntentZooidShutdown:
    """Test IntentZooid shutdown."""

    def test_shutdown_emits_signal(self, zooid):
        """Test that shutdown emits VOICE.INTENT.SHUTDOWN signal."""
        zooid.start()
        zooid.shutdown()

        assert zooid.chem_pub.get_signal_count("VOICE.INTENT.SHUTDOWN") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.INTENT.SHUTDOWN")
        assert "stats" in msg.facts

    def test_shutdown_stops_processing(self, zooid):
        """Test that shutdown stops processing."""
        zooid.start()
        zooid.shutdown()

        assert not zooid.running

        zooid._on_transcription({
            "facts": {
                "text": "enroll me"
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.INTENT.CLASSIFIED") == 0
