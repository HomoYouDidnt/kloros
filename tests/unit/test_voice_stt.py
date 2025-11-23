"""Unit tests for STT zooid - test in isolation with mocked ChemBus and STT backend."""
import os
import sys
import time
import wave
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.chembus_mock import MockChemPub, MockChemSub
from src.kloros_voice_stt import STTZooid


@dataclass
class MockTranscriptionResult:
    """Mock STT transcription result."""
    transcript: str
    confidence: float
    lang: str = "en"


@pytest.fixture
def mock_stt_backend():
    """Mock STT backend for testing without real models."""
    mock_backend = MagicMock()

    def mock_transcribe(audio, sample_rate, lang="en"):
        if len(audio) < 1000:
            return MockTranscriptionResult(transcript="", confidence=0.0, lang=lang)
        return MockTranscriptionResult(
            transcript="hello world test",
            confidence=0.95,
            lang=lang
        )

    mock_backend.transcribe = mock_transcribe
    mock_backend.get_info = lambda: {"enable_corrections": True}
    return mock_backend


@pytest.fixture
def test_audio_file():
    """Create a temporary test audio file."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000)) * 32767).astype(np.int16)
        with wave.open(tmp.name, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_data.tobytes())
        yield Path(tmp.name)
        Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture
def zooid(monkeypatch, mock_stt_backend):
    """Create STTZooid with mocked dependencies."""
    monkeypatch.setenv("KLR_ENABLE_STT", "1")
    monkeypatch.setenv("KLR_STT_BACKEND", "mock")
    monkeypatch.setenv("KLR_STT_LANG", "en-US")

    with patch('src.kloros_voice_stt.ChemPub', MockChemPub), \
         patch('src.kloros_voice_stt.ChemSub', MockChemSub), \
         patch('src.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend):

        zooid = STTZooid()
        yield zooid

        zooid.shutdown()


class TestSTTZooidInit:
    """Test STTZooid initialization."""

    def test_init_sets_backend_from_env(self, monkeypatch):
        """Test that backend is configured from environment."""
        monkeypatch.setenv("KLR_STT_BACKEND", "whisper")

        with patch('src.kloros_voice_stt.ChemPub', MockChemPub), \
             patch('src.kloros_voice_stt.ChemSub', MockChemSub):
            zooid = STTZooid()

        assert zooid.stt_backend_name == "whisper"
        zooid.shutdown()

    def test_init_sets_language_from_env(self, monkeypatch):
        """Test that language is configured from environment."""
        monkeypatch.setenv("KLR_STT_LANG", "es-ES")

        with patch('src.kloros_voice_stt.ChemPub', MockChemPub), \
             patch('src.kloros_voice_stt.ChemSub', MockChemSub):
            zooid = STTZooid()

        assert zooid.stt_lang == "es-ES"
        zooid.shutdown()

    def test_init_statistics(self, zooid):
        """Test that statistics are initialized."""
        assert zooid.stats["total_transcriptions"] == 0
        assert zooid.stats["successful_transcriptions"] == 0
        assert zooid.stats["failed_transcriptions"] == 0


class TestSTTZooidStart:
    """Test STTZooid startup."""

    def test_start_emits_ready_signal(self, zooid):
        """Test that start() emits VOICE.STT.READY signal."""
        zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.STT.READY") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.STT.READY")
        assert msg is not None
        assert msg.ecosystem == "voice"
        assert msg.facts["zooid"] == "kloros-voice-stt"
        assert msg.facts["backend"] == "mock"

    def test_start_subscribes_to_audio_captured(self, zooid):
        """Test that start() subscribes to VOICE.AUDIO.CAPTURED."""
        zooid.start()

        assert hasattr(zooid, 'audio_sub')
        assert zooid.audio_sub.topic == "VOICE.AUDIO.CAPTURED"

    def test_start_disabled_stt(self, monkeypatch):
        """Test that STT can be disabled via environment."""
        monkeypatch.setenv("KLR_ENABLE_STT", "0")

        with patch('src.kloros_voice_stt.ChemPub', MockChemPub), \
             patch('src.kloros_voice_stt.ChemSub', MockChemSub):
            zooid = STTZooid()
            zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.STT.READY") == 0


class TestSTTBackendInit:
    """Test STT backend initialization."""

    def test_init_backend_hybrid(self, monkeypatch, mock_stt_backend):
        """Test hybrid backend initialization."""
        monkeypatch.setenv("KLR_STT_BACKEND", "hybrid")
        monkeypatch.setenv("ASR_VOSK_MODEL", "/tmp/vosk-model")
        monkeypatch.setenv("ASR_WHISPER_SIZE", "small")

        with patch('src.kloros_voice_stt.ChemPub', MockChemPub), \
             patch('src.kloros_voice_stt.ChemSub', MockChemSub), \
             patch('src.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend) as mock_create:

            zooid = STTZooid()
            zooid.start()

        mock_create.assert_called_once()
        assert zooid.stt_backend is not None

    def test_init_backend_fallback_to_mock(self, monkeypatch):
        """Test fallback to mock backend on failure."""
        monkeypatch.setenv("KLR_STT_BACKEND", "nonexistent")

        mock_backend = MagicMock()

        def create_backend_side_effect(name, **kwargs):
            if name == "nonexistent":
                raise ValueError("Backend not found")
            return mock_backend

        with patch('src.kloros_voice_stt.ChemPub', MockChemPub), \
             patch('src.kloros_voice_stt.ChemSub', MockChemSub), \
             patch('src.kloros_voice_stt.create_stt_backend', side_effect=create_backend_side_effect):

            zooid = STTZooid()
            zooid.start()

        assert zooid.stt_backend is not None


class TestSTTTranscription:
    """Test STT transcription functionality."""

    def test_transcribe_audio_success(self, zooid, test_audio_file):
        """Test successful audio transcription."""
        zooid.start()

        zooid._on_audio_captured({
            "facts": {
                "audio_file": str(test_audio_file),
                "duration": 1.0,
                "sample_rate": 16000,
                "timestamp": time.time()
            },
            "incident_id": "trans-001"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.STT.TRANSCRIPTION") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.STT.TRANSCRIPTION")
        assert msg.facts["text"] == "hello world test"
        assert msg.facts["confidence"] == 0.95
        assert msg.incident_id == "trans-001"

    def test_transcribe_updates_statistics(self, zooid, test_audio_file):
        """Test that transcription updates statistics."""
        zooid.start()

        initial_total = zooid.stats["total_transcriptions"]
        initial_success = zooid.stats["successful_transcriptions"]

        zooid._on_audio_captured({
            "facts": {
                "audio_file": str(test_audio_file),
                "duration": 1.0,
                "sample_rate": 16000
            }
        })

        assert zooid.stats["total_transcriptions"] == initial_total + 1
        assert zooid.stats["successful_transcriptions"] == initial_success + 1

    def test_transcribe_missing_audio_file(self, zooid):
        """Test handling of missing audio_file in event."""
        zooid.start()

        zooid._on_audio_captured({
            "facts": {
                "duration": 1.0
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.STT.TRANSCRIPTION") == 0

    def test_transcribe_file_not_found(self, zooid):
        """Test handling of non-existent audio file."""
        zooid.start()

        initial_failed = zooid.stats["failed_transcriptions"]

        zooid._on_audio_captured({
            "facts": {
                "audio_file": "/nonexistent/audio.wav",
                "duration": 1.0
            }
        })

        assert zooid.stats["failed_transcriptions"] == initial_failed + 1
        assert zooid.chem_pub.get_signal_count("VOICE.STT.TRANSCRIPTION") == 0

    def test_load_audio_file(self, zooid, test_audio_file):
        """Test audio file loading."""
        audio_data, sample_rate = zooid._load_audio_file(test_audio_file)

        assert audio_data is not None
        assert isinstance(audio_data, np.ndarray)
        assert audio_data.dtype == np.float32
        assert sample_rate == 16000
        assert len(audio_data) > 0

    def test_load_audio_file_not_found(self, zooid):
        """Test audio file loading with non-existent file."""
        audio_data, sample_rate = zooid._load_audio_file(Path("/nonexistent.wav"))

        assert audio_data is None
        assert sample_rate == 0


class TestSTTStatistics:
    """Test STT statistics tracking."""

    def test_get_stats(self, zooid):
        """Test getting STT statistics."""
        stats = zooid.get_stats()

        assert "total_transcriptions" in stats
        assert "successful_transcriptions" in stats
        assert "failed_transcriptions" in stats
        assert "average_confidence" in stats
        assert "average_processing_time" in stats

    def test_average_confidence_calculation(self, zooid, test_audio_file):
        """Test average confidence calculation."""
        zooid.start()

        for i in range(3):
            zooid._on_audio_captured({
                "facts": {
                    "audio_file": str(test_audio_file),
                    "duration": 1.0
                }
            })

        stats = zooid.get_stats()
        assert stats["average_confidence"] == pytest.approx(0.95, rel=0.01)


class TestSTTZooidShutdown:
    """Test STTZooid shutdown."""

    def test_shutdown_emits_signal(self, zooid):
        """Test that shutdown emits VOICE.STT.SHUTDOWN signal."""
        zooid.start()
        zooid.shutdown()

        assert zooid.chem_pub.get_signal_count("VOICE.STT.SHUTDOWN") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.STT.SHUTDOWN")
        assert "stats" in msg.facts

    def test_shutdown_stops_processing(self, zooid, test_audio_file):
        """Test that shutdown stops processing."""
        zooid.start()
        zooid.shutdown()

        assert not zooid.running

        zooid._on_audio_captured({
            "facts": {
                "audio_file": str(test_audio_file),
                "duration": 1.0
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.STT.TRANSCRIPTION") == 0
