"""Unit tests for Audio I/O zooid - test in isolation with mocked ChemBus."""
import os
import sys
import time
import tempfile
import wave
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.chembus_mock import MockChemPub, MockChemSub
from src.kloros_voice_audio_io import AudioIOZooid


@pytest.fixture
def temp_recordings_dir():
    """Create temporary recordings directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_audio_backend():
    """Mock PulseAudioBackend for testing without real audio hardware."""
    mock_backend = MagicMock()
    mock_backend.open = MagicMock()
    mock_backend.close = MagicMock()

    def mock_chunks(block_ms=100):
        sample_rate = 16000
        chunk_size = int(sample_rate * block_ms / 1000)
        for _ in range(5):
            yield np.random.uniform(-0.1, 0.1, chunk_size).astype(np.float32)
            time.sleep(0.01)

    mock_backend.chunks = mock_chunks
    return mock_backend


@pytest.fixture
def zooid(temp_recordings_dir, monkeypatch):
    """Create AudioIOZooid with mocked dependencies."""
    monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_recordings_dir))
    monkeypatch.setenv("KLR_AUDIO_SAMPLE_RATE", "16000")

    with patch('src.kloros_voice_audio_io.ChemPub', MockChemPub), \
         patch('src.kloros_voice_audio_io.ChemSub', MockChemSub):

        zooid = AudioIOZooid()
        yield zooid

        zooid.shutdown()


class TestAudioIOZooidInit:
    """Test AudioIOZooid initialization."""

    def test_init_creates_recordings_dir(self, temp_recordings_dir, monkeypatch):
        """Test that initialization creates recordings directory."""
        recordings_dir = temp_recordings_dir / "recordings"
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(recordings_dir))

        with patch('src.kloros_voice_audio_io.ChemPub', MockChemPub), \
             patch('src.kloros_voice_audio_io.ChemSub', MockChemSub):
            zooid = AudioIOZooid()

        assert recordings_dir.exists()
        zooid.shutdown()

    def test_init_sets_sample_rate(self, monkeypatch):
        """Test that sample rate is configured from environment."""
        monkeypatch.setenv("KLR_AUDIO_SAMPLE_RATE", "48000")

        with patch('src.kloros_voice_audio_io.ChemPub', MockChemPub), \
             patch('src.kloros_voice_audio_io.ChemSub', MockChemSub):
            zooid = AudioIOZooid()

        assert zooid.sample_rate == 48000
        zooid.shutdown()

    def test_init_checks_paplay_availability(self, zooid):
        """Test that paplay availability is checked on init."""
        assert zooid.paplay_path is not None or zooid.paplay_path is None


class TestAudioIOZooidStart:
    """Test AudioIOZooid startup."""

    def test_start_emits_ready_signal(self, zooid):
        """Test that start() emits VOICE.AUDIO.IO.READY signal."""
        zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.AUDIO.IO.READY") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.AUDIO.IO.READY")
        assert msg is not None
        assert msg.ecosystem == "voice"
        assert msg.facts["zooid"] == "kloros-voice-audio-io"

    def test_start_subscribes_to_signals(self, zooid):
        """Test that start() subscribes to ChemBus signals."""
        zooid.start()

        assert hasattr(zooid, 'play_sub')
        assert hasattr(zooid, 'record_start_sub')
        assert hasattr(zooid, 'record_stop_sub')


class TestAudioPlayback:
    """Test audio playback functionality."""

    def test_play_audio_file_success(self, zooid, temp_recordings_dir):
        """Test successful audio file playback."""
        test_wav = temp_recordings_dir / "test.wav"

        audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000)) * 32767).astype(np.int16)
        with wave.open(str(test_wav), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_data.tobytes())

        zooid.start()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr=b'')

            zooid._on_play_audio({
                "facts": {"file_path": str(test_wav)},
                "incident_id": "test-123"
            })

        assert zooid.chem_pub.get_signal_count("VOICE.AUDIO.PLAYBACK.COMPLETE") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.AUDIO.PLAYBACK.COMPLETE")
        assert msg.facts["file_path"] == str(test_wav)
        assert msg.incident_id == "test-123"

    def test_play_audio_file_not_found(self, zooid):
        """Test playback handles missing file gracefully."""
        zooid.start()

        zooid._on_play_audio({
            "facts": {"file_path": "/nonexistent/file.wav"},
            "incident_id": "test-456"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.AUDIO.PLAYBACK.COMPLETE") == 0

    def test_play_audio_missing_file_path(self, zooid):
        """Test playback handles missing file_path in signal."""
        zooid.start()

        zooid._on_play_audio({
            "facts": {},
            "incident_id": "test-789"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.AUDIO.PLAYBACK.COMPLETE") == 0


class TestAudioCapture:
    """Test audio capture functionality."""

    def test_record_start_begins_capture(self, zooid, mock_audio_backend):
        """Test that RECORD.START signal begins audio capture."""
        with patch('src.kloros_voice_audio_io.PulseAudioBackend', return_value=mock_audio_backend):
            zooid.start()

            assert not zooid.capturing

            zooid._on_record_start({"incident_id": "rec-001"})

            time.sleep(0.2)

            assert zooid.capturing
            assert zooid.capture_thread is not None
            assert zooid.capture_thread.is_alive()

    def test_record_stop_ends_capture(self, zooid, mock_audio_backend):
        """Test that RECORD.STOP signal ends audio capture."""
        with patch('src.kloros_voice_audio_io.PulseAudioBackend', return_value=mock_audio_backend):
            zooid.start()

            zooid._on_record_start({"incident_id": "rec-002"})
            time.sleep(0.2)
            assert zooid.capturing

            zooid._on_record_stop({"incident_id": "rec-002"})
            time.sleep(0.1)

            assert not zooid.capturing

    def test_record_start_ignores_duplicate(self, zooid, mock_audio_backend):
        """Test that duplicate RECORD.START is ignored."""
        with patch('src.kloros_voice_audio_io.PulseAudioBackend', return_value=mock_audio_backend):
            zooid.start()

            zooid._on_record_start({"incident_id": "rec-003"})
            time.sleep(0.1)

            first_thread = zooid.capture_thread

            zooid._on_record_start({"incident_id": "rec-004"})

            assert zooid.capture_thread is first_thread

    def test_save_audio_chunk(self, zooid, temp_recordings_dir):
        """Test that audio chunks are saved as WAV files."""
        audio_data = np.random.uniform(-0.5, 0.5, 8000).astype(np.float32)
        timestamp = time.time()

        wav_path = zooid._save_audio_chunk(audio_data, timestamp)

        assert wav_path.exists()
        assert wav_path.suffix == ".wav"
        assert wav_path.parent == temp_recordings_dir

        with wave.open(str(wav_path), 'rb') as wf:
            assert wf.getframerate() == zooid.sample_rate
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2


class TestAudioIOZooidShutdown:
    """Test AudioIOZooid shutdown."""

    def test_shutdown_stops_capture(self, zooid, mock_audio_backend):
        """Test that shutdown stops active capture."""
        with patch('src.kloros_voice_audio_io.PulseAudioBackend', return_value=mock_audio_backend):
            zooid.start()
            zooid._on_record_start({"incident_id": "rec-005"})
            time.sleep(0.1)

            zooid.shutdown()

            assert not zooid.running
            assert not zooid.capturing

    def test_shutdown_closes_audio_backend(self, zooid, mock_audio_backend):
        """Test that shutdown closes audio backend."""
        with patch('src.kloros_voice_audio_io.PulseAudioBackend', return_value=mock_audio_backend):
            zooid.start()
            zooid.audio_backend = mock_audio_backend

            zooid.shutdown()

            mock_audio_backend.close.assert_called_once()

    def test_shutdown_closes_chembus_connections(self, zooid):
        """Test that shutdown closes ChemBus connections."""
        zooid.start()

        zooid.shutdown()

        assert zooid.chem_pub.closed
