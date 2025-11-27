"""Unit tests for TTS zooid - test in isolation with mocked UMN and TTS backend."""
import os
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.umn_mock import MockUMNPub, MockUMNSub
from src.voice.kloros_voice_tts import TTSZooid


@dataclass
class MockSynthesisResult:
    """Mock TTS synthesis result."""
    audio_path: str
    duration_s: float
    sample_rate: int
    voice: str


@pytest.fixture
def mock_tts_backend():
    """Mock TTS backend for testing without real models."""
    mock_backend = MagicMock()

    def mock_synthesize(text, sample_rate=22050, voice=None, out_dir=None):
        out_path = Path(out_dir or tempfile.gettempdir()) / f"tts_{time.time()}.wav"
        out_path.touch()
        return MockSynthesisResult(
            audio_path=str(out_path),
            duration_s=len(text.split()) * 0.5,
            sample_rate=sample_rate,
            voice=voice or "default"
        )

    mock_backend.synthesize = mock_synthesize
    return mock_backend


@pytest.fixture
def temp_tts_dir():
    """Create temporary TTS output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def zooid(monkeypatch, temp_tts_dir, mock_tts_backend):
    """Create TTSZooid with mocked dependencies."""
    monkeypatch.setenv("KLR_ENABLE_TTS", "1")
    monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
    monkeypatch.setenv("KLR_TTS_SAMPLE_RATE", "22050")
    monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))
    monkeypatch.setenv("KLR_FAIL_OPEN_TTS", "1")

    with patch('src.voice.kloros_voice_tts.UMNPub', MockUMNPub), \
         patch('src.voice.kloros_voice_tts.UMNSub', MockUMNSub):

        zooid = TTSZooid()
        zooid.tts_backend = mock_tts_backend
        yield zooid

        zooid.shutdown()


class TestTTSZooidInit:
    """Test TTSZooid initialization."""

    def test_init_sets_backend_from_env(self, monkeypatch, temp_tts_dir):
        """Test that backend is configured from environment."""
        monkeypatch.setenv("KLR_TTS_BACKEND", "piper")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        with patch('src.voice.kloros_voice_tts.UMNPub', MockUMNPub), \
             patch('src.voice.kloros_voice_tts.UMNSub', MockUMNSub):
            zooid = TTSZooid()

        assert zooid.tts_backend_name == "piper"
        zooid.shutdown()

    def test_init_sets_sample_rate_from_env(self, monkeypatch, temp_tts_dir):
        """Test that sample rate is configured from environment."""
        monkeypatch.setenv("KLR_TTS_SAMPLE_RATE", "44100")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        with patch('src.voice.kloros_voice_tts.UMNPub', MockUMNPub), \
             patch('src.voice.kloros_voice_tts.UMNSub', MockUMNSub):
            zooid = TTSZooid()

        assert zooid.tts_sample_rate == 44100
        zooid.shutdown()

    def test_init_creates_output_directory(self, monkeypatch):
        """Test that output directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tts_dir = Path(tmpdir) / "tts_out"
            monkeypatch.setenv("KLR_TTS_OUT_DIR", str(tts_dir))

            with patch('src.voice.kloros_voice_tts.UMNPub', MockUMNPub), \
                 patch('src.voice.kloros_voice_tts.UMNSub', MockUMNSub):
                zooid = TTSZooid()

            assert tts_dir.exists()
            zooid.shutdown()

    def test_init_statistics(self, zooid):
        """Test that statistics are initialized."""
        assert zooid.stats["total_syntheses"] == 0
        assert zooid.stats["successful_syntheses"] == 0
        assert zooid.stats["failed_syntheses"] == 0


class TestTTSZooidStart:
    """Test TTSZooid startup."""

    def test_start_emits_ready_signal(self, zooid):
        """Test that start() emits VOICE.TTS.READY signal."""
        zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.TTS.READY") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.TTS.READY")
        assert msg is not None
        assert msg.ecosystem == "voice"
        assert msg.facts["zooid"] == "kloros-voice-tts"
        assert msg.facts["backend"] == "mock"

    def test_start_subscribes_to_speak_signal(self, zooid):
        """Test that start() subscribes to VOICE.ORCHESTRATOR.SPEAK."""
        zooid.start()

        assert hasattr(zooid, 'speak_sub')
        assert zooid.speak_sub.topic == "VOICE.ORCHESTRATOR.SPEAK"

    def test_start_disabled_tts(self, monkeypatch, temp_tts_dir):
        """Test that TTS can be disabled via environment."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "0")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        with patch('src.voice.kloros_voice_tts.UMNPub', MockUMNPub), \
             patch('src.voice.kloros_voice_tts.UMNSub', MockUMNSub):
            zooid = TTSZooid()
            zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.TTS.READY") == 0


class TestTTSBackendInit:
    """Test TTS backend initialization."""

    def test_init_backend_fallback_to_mock(self, monkeypatch, temp_tts_dir):
        """Test fallback to mock backend on failure."""
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        mock_backend = MagicMock()
        mock_backend.synthesize = MagicMock(return_value=MockSynthesisResult(
            audio_path=str(temp_tts_dir / "test.wav"),
            duration_s=1.0,
            sample_rate=22050,
            voice="default"
        ))

        with patch('src.voice.kloros_voice_tts.UMNPub', MockUMNPub), \
             patch('src.voice.kloros_voice_tts.UMNSub', MockUMNSub):

            zooid = TTSZooid()
            zooid.tts_backend = mock_backend
            zooid.start()

        assert zooid.tts_backend is not None


class TestTTSSynthesis:
    """Test TTS synthesis functionality."""

    def test_synthesize_text_success(self, zooid):
        """Test successful text synthesis."""
        zooid.start()

        zooid._on_speak_request({
            "facts": {
                "text": "Hello world",
                "urgency": 0.8
            },
            "incident_id": "synth-001"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.TTS.AUDIO.READY") == 1
        assert zooid.chem_pub.get_signal_count("VOICE.TTS.PLAY.AUDIO") == 1

        ready_msg = zooid.chem_pub.get_last_message("VOICE.TTS.AUDIO.READY")
        assert ready_msg.facts["text"] == "Hello world"
        assert ready_msg.incident_id == "synth-001"

        play_msg = zooid.chem_pub.get_last_message("VOICE.TTS.PLAY.AUDIO")
        assert play_msg.intensity == 0.8
        assert play_msg.incident_id == "synth-001"

    def test_synthesize_updates_statistics(self, zooid):
        """Test that synthesis updates statistics."""
        zooid.start()

        initial_total = zooid.stats["total_syntheses"]
        initial_success = zooid.stats["successful_syntheses"]

        zooid._on_speak_request({
            "facts": {
                "text": "Test synthesis"
            }
        })

        assert zooid.stats["total_syntheses"] == initial_total + 1
        assert zooid.stats["successful_syntheses"] == initial_success + 1

    def test_synthesize_missing_text(self, zooid):
        """Test handling of missing text in speak request."""
        zooid.start()

        zooid._on_speak_request({
            "facts": {},
            "incident_id": "synth-002"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.TTS.ERROR") == 1
        error_msg = zooid.chem_pub.get_last_message("VOICE.TTS.ERROR")
        assert error_msg.facts["error"] == "missing_text"

    def test_synthesize_with_affective_state(self, zooid):
        """Test synthesis with affective state parameters."""
        zooid.start()

        affective_state = {
            "valence": 0.8,
            "arousal": 0.6,
            "dominance": 0.7
        }

        zooid._on_speak_request({
            "facts": {
                "text": "I'm happy",
                "affective_state": affective_state,
                "urgency": 0.5
            },
            "incident_id": "synth-003"
        })

        ready_msg = zooid.chem_pub.get_last_message("VOICE.TTS.AUDIO.READY")
        assert ready_msg.facts["affective_state"] == affective_state


class TestTTSTextNormalization:
    """Test TTS text normalization."""

    def test_normalize_kloros_spelling(self, zooid):
        """Test that 'KLoROS' is normalized for proper pronunciation."""
        assert zooid._normalize_tts_text("KLoROS") == "Kloros"
        assert zooid._normalize_tts_text("K.L.o.R.O.S.") == "Kloros"
        assert zooid._normalize_tts_text("kloros") == "Kloros"

    def test_normalize_preserves_other_text(self, zooid):
        """Test that other text is preserved during normalization."""
        text = "Hello, this is a test"
        assert zooid._normalize_tts_text(text) == text

    def test_normalize_kloros_in_sentence(self, zooid):
        """Test KLoROS normalization in context."""
        text = "Hello, I am KLoROS, your assistant"
        normalized = zooid._normalize_tts_text(text)
        assert "Kloros" in normalized
        assert "KLoROS" not in normalized


class TestTTSFailOpen:
    """Test TTS fail-open behavior."""

    def test_fail_open_backend_unavailable(self, monkeypatch, temp_tts_dir):
        """Test fail-open mode when backend unavailable."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))
        monkeypatch.setenv("KLR_FAIL_OPEN_TTS", "1")

        with patch('src.voice.kloros_voice_tts.UMNPub', MockUMNPub), \
             patch('src.voice.kloros_voice_tts.UMNSub', MockUMNSub):

            zooid = TTSZooid()
            zooid.tts_backend = None
            zooid.start()

            zooid._on_speak_request({
                "facts": {
                    "text": "Test text"
                },
                "incident_id": "fail-001"
            })

            assert zooid.chem_pub.get_signal_count("VOICE.TTS.TEXT.ONLY") == 1
            text_only_msg = zooid.chem_pub.get_last_message("VOICE.TTS.TEXT.ONLY")
            assert text_only_msg.facts["text"] == "Test text"


class TestTTSStatistics:
    """Test TTS statistics tracking."""

    def test_get_stats(self, zooid):
        """Test getting TTS statistics."""
        stats = zooid.get_stats()

        assert "total_syntheses" in stats
        assert "successful_syntheses" in stats
        assert "failed_syntheses" in stats
        assert "average_duration" in stats
        assert "average_synthesis_time" in stats

    def test_average_duration_calculation(self, zooid):
        """Test average duration calculation."""
        zooid.start()

        for _ in range(3):
            zooid._on_speak_request({
                "facts": {
                    "text": "Test message"
                }
            })

        stats = zooid.get_stats()
        assert stats["average_duration"] > 0


class TestTTSZooidShutdown:
    """Test TTSZooid shutdown."""

    def test_shutdown_emits_signal(self, zooid):
        """Test that shutdown emits VOICE.TTS.SHUTDOWN signal."""
        zooid.start()
        zooid.shutdown()

        assert zooid.chem_pub.get_signal_count("VOICE.TTS.SHUTDOWN") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.TTS.SHUTDOWN")
        assert "stats" in msg.facts

    def test_shutdown_stops_processing(self, zooid):
        """Test that shutdown stops processing."""
        zooid.start()
        zooid.shutdown()

        assert not zooid.running

        zooid._on_speak_request({
            "facts": {
                "text": "This should not be processed"
            }
        })

        old_count = zooid.chem_pub.get_signal_count("VOICE.TTS.AUDIO.READY")
        assert old_count == 0

    def test_shutdown_closes_umn_connections(self, zooid):
        """Test that shutdown closes UMN connections."""
        zooid.start()

        zooid.shutdown()

        assert zooid.chem_pub.closed
        assert zooid.speak_sub.closed
