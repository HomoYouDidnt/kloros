"""Unit tests for Emotion zooid - test in isolation with mocked UMN."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.umn_mock import MockUMNPub, MockUMNSub
from src.kloros_voice_emotion import EmotionZooid


@pytest.fixture
def zooid(monkeypatch):
    """Create EmotionZooid with mocked dependencies."""
    monkeypatch.setenv("KLR_ENABLE_EMOTION", "1")

    with patch('src.kloros_voice_emotion.UMNPub', MockUMNPub), \
         patch('src.kloros_voice_emotion.UMNSub', MockUMNSub):

        zooid = EmotionZooid()
        yield zooid

        zooid.shutdown()


class TestEmotionZooidInit:
    """Test EmotionZooid initialization."""

    def test_init_sets_zooid_name(self, zooid):
        """Test that zooid name is set correctly."""
        assert zooid.zooid_name == "kloros-voice-emotion"
        assert zooid.niche == "voice.emotion"

    def test_init_statistics(self, zooid):
        """Test that statistics are initialized."""
        assert zooid.stats["total_analyses"] == 0
        assert zooid.stats["positive_detections"] == 0
        assert zooid.stats["negative_detections"] == 0
        assert zooid.stats["neutral_detections"] == 0
        assert zooid.stats["emotion_shifts_detected"] == 0

    def test_init_sentiment_lexicons(self, zooid):
        """Test that sentiment lexicons are loaded."""
        assert len(zooid.positive_words) > 0
        assert len(zooid.negative_words) > 0
        assert len(zooid.intensifiers) > 0

        assert "good" in zooid.positive_words
        assert "bad" in zooid.negative_words
        assert "very" in zooid.intensifiers

    def test_init_emotional_state(self, zooid):
        """Test that emotional state is initialized to neutral."""
        assert zooid.current_state["valence"] == 0.0
        assert zooid.current_state["arousal"] == 0.0
        assert zooid.current_state["dominance"] == 0.0


class TestEmotionZooidStart:
    """Test EmotionZooid startup."""

    def test_start_emits_ready_signal(self, zooid):
        """Test that start() emits VOICE.EMOTION.READY signal."""
        zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.EMOTION.READY") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.EMOTION.READY")
        assert msg is not None
        assert msg.ecosystem == "voice"
        assert msg.facts["zooid"] == "kloros-voice-emotion"
        assert msg.facts["method"] == "rule-based"
        assert "current_state" in msg.facts

    def test_start_subscribes_to_stt_transcription(self, zooid):
        """Test that start() subscribes to VOICE.STT.TRANSCRIPTION."""
        zooid.start()

        assert hasattr(zooid, 'transcription_sub')
        assert zooid.transcription_sub.topic == "VOICE.STT.TRANSCRIPTION"

    def test_start_disabled_emotion(self, monkeypatch):
        """Test that Emotion can be disabled via environment."""
        monkeypatch.setenv("KLR_ENABLE_EMOTION", "0")

        with patch('src.kloros_voice_emotion.UMNPub', MockUMNPub), \
             patch('src.kloros_voice_emotion.UMNSub', MockUMNSub):
            zooid = EmotionZooid()
            zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.EMOTION.READY") == 0


class TestEmotionAnalysis:
    """Test emotion analysis functionality."""

    def test_analyze_positive_sentiment(self, zooid):
        """Test analysis of positive text."""
        sentiment, valence, arousal, dominance, confidence = zooid._analyze_emotion(
            "This is great and wonderful!"
        )

        assert sentiment == "positive"
        assert valence > 0.0
        assert confidence > 0.5

    def test_analyze_negative_sentiment(self, zooid):
        """Test analysis of negative text."""
        sentiment, valence, arousal, dominance, confidence = zooid._analyze_emotion(
            "This is terrible and awful."
        )

        assert sentiment == "negative"
        assert valence < 0.0
        assert confidence > 0.5

    def test_analyze_neutral_sentiment(self, zooid):
        """Test analysis of neutral text."""
        sentiment, valence, arousal, dominance, confidence = zooid._analyze_emotion(
            "The sky is blue."
        )

        assert sentiment == "neutral"
        assert valence == 0.0
        assert confidence == 0.5

    def test_analyze_intensifier_boost(self, zooid):
        """Test that intensifiers boost sentiment."""
        sent_normal, val_normal, _, _, conf_normal = zooid._analyze_emotion("good")
        sent_intense, val_intense, _, _, conf_intense = zooid._analyze_emotion("very good")

        assert sent_normal == sent_intense == "positive"
        assert val_intense > val_normal

    def test_analyze_question_dominance(self, zooid):
        """Test that questions have lower dominance."""
        sent, val, arousal, dominance, conf = zooid._analyze_emotion(
            "What is the answer?"
        )

        assert dominance < 0.0

    def test_analyze_statement_dominance(self, zooid):
        """Test that statements have higher dominance."""
        sent, val, arousal, dominance, conf = zooid._analyze_emotion(
            "This is the answer."
        )

        assert dominance >= 0.0


class TestEmotionShiftDetection:
    """Test emotional shift detection."""

    def test_detect_shift_large_valence_change(self, zooid):
        """Test detection of large valence shift."""
        zooid.current_state["valence"] = -0.5

        shift_detected = zooid._detect_emotion_shift(
            valence=0.5,
            arousal=0.0,
            dominance=0.0
        )

        assert shift_detected is True

    def test_no_shift_small_valence_change(self, zooid):
        """Test no detection for small valence change."""
        zooid.current_state["valence"] = 0.3

        shift_detected = zooid._detect_emotion_shift(
            valence=0.5,
            arousal=0.0,
            dominance=0.0
        )

        assert shift_detected is False

    def test_shift_updates_state(self, zooid):
        """Test that shift detection updates current state."""
        old_valence = zooid.current_state["valence"]

        zooid._detect_emotion_shift(
            valence=0.8,
            arousal=0.3,
            dominance=0.1
        )

        assert zooid.current_state["valence"] == 0.8
        assert zooid.current_state["arousal"] == 0.3
        assert zooid.current_state["dominance"] == 0.1

    def test_shift_tracks_history(self, zooid):
        """Test that emotional history is tracked."""
        initial_history_len = len(zooid.emotional_history)

        for i in range(5):
            zooid._detect_emotion_shift(
                valence=i * 0.1,
                arousal=0.0,
                dominance=0.0
            )

        assert len(zooid.emotional_history) == initial_history_len + 5

    def test_history_max_length(self, zooid):
        """Test that emotional history is limited to 10 states."""
        for i in range(15):
            zooid._detect_emotion_shift(
                valence=i * 0.05,
                arousal=0.0,
                dominance=0.0
            )

        assert len(zooid.emotional_history) == 10


class TestEmotionSignalEmission:
    """Test UMN signal emission for emotion analysis."""

    def test_on_transcription_emits_emotion_state(self, zooid):
        """Test that transcription handler emits VOICE.EMOTION.STATE."""
        zooid.start()

        zooid._on_transcription({
            "facts": {
                "text": "This is great!",
                "confidence": 0.95
            },
            "incident_id": "emotion-001"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.EMOTION.STATE") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.EMOTION.STATE")
        assert msg.facts["text"] == "This is great!"
        assert msg.facts["sentiment"] == "positive"
        assert msg.facts["valence"] > 0.0
        assert msg.incident_id == "emotion-001"

    def test_on_transcription_emits_shift_signal(self, zooid):
        """Test that large emotional shift triggers shift signal."""
        zooid.start()

        zooid.current_state["valence"] = -0.8

        zooid._on_transcription({
            "facts": {
                "text": "This is absolutely wonderful and amazing!",
                "confidence": 0.95
            },
            "incident_id": "shift-001"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.EMOTION.SHIFT.DETECTED") >= 1

    def test_on_transcription_updates_statistics(self, zooid):
        """Test that transcription updates statistics."""
        zooid.start()

        initial_total = zooid.stats["total_analyses"]
        initial_positive = zooid.stats["positive_detections"]

        zooid._on_transcription({
            "facts": {
                "text": "excellent work",
                "confidence": 0.95
            }
        })

        assert zooid.stats["total_analyses"] == initial_total + 1
        assert zooid.stats["positive_detections"] == initial_positive + 1

    def test_on_transcription_missing_text(self, zooid):
        """Test handling of missing text in transcription."""
        zooid.start()

        zooid._on_transcription({
            "facts": {
                "confidence": 0.95
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.EMOTION.STATE") == 0


class TestEmotionStatistics:
    """Test Emotion statistics tracking."""

    def test_get_stats(self, zooid):
        """Test getting Emotion statistics."""
        stats = zooid.get_stats()

        assert "total_analyses" in stats
        assert "positive_detections" in stats
        assert "negative_detections" in stats
        assert "neutral_detections" in stats
        assert "emotion_shifts_detected" in stats
        assert "average_analysis_time" in stats
        assert "current_state" in stats

    def test_statistics_count_correctly(self, zooid):
        """Test that statistics count different sentiment types correctly."""
        zooid.start()

        zooid._on_transcription({"facts": {"text": "wonderful"}})
        zooid._on_transcription({"facts": {"text": "terrible"}})
        zooid._on_transcription({"facts": {"text": "the sky is blue"}})

        stats = zooid.get_stats()
        assert stats["total_analyses"] == 3
        assert stats["positive_detections"] == 1
        assert stats["negative_detections"] == 1
        assert stats["neutral_detections"] == 1


class TestEmotionZooidShutdown:
    """Test EmotionZooid shutdown."""

    def test_shutdown_emits_signal(self, zooid):
        """Test that shutdown emits VOICE.EMOTION.SHUTDOWN signal."""
        zooid.start()
        zooid.shutdown()

        assert zooid.chem_pub.get_signal_count("VOICE.EMOTION.SHUTDOWN") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.EMOTION.SHUTDOWN")
        assert "stats" in msg.facts

    def test_shutdown_stops_processing(self, zooid):
        """Test that shutdown stops processing."""
        zooid.start()
        zooid.shutdown()

        assert not zooid.running

        zooid._on_transcription({
            "facts": {
                "text": "wonderful"
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.EMOTION.STATE") == 0
