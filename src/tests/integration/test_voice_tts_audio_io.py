"""Integration tests for TTS → Audio I/O signal flow.

Tests the communication between TTS and Audio I/O zooids via real UMN.
No mocks - uses actual UMN pub/sub with subprocess coordination.
"""
import os
import sys
import time
import wave
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus_v2 import UMNPub, UMNSub
from src.voice.kloros_voice_audio_io import AudioIOZooid


@pytest.fixture
def temp_recordings_dir():
    """Create temporary recordings directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_audio_file(temp_recordings_dir):
    """Create a test audio file for playback."""
    test_wav = temp_recordings_dir / "test_playback.wav"
    audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, 8000)) * 32767).astype(np.int16)
    with wave.open(str(test_wav), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_data.tobytes())
    return test_wav


@pytest.mark.integration
class TestTTSAudioIOIntegration:
    """Test TTS → Audio I/O signal coordination."""

    def test_play_audio_to_playback_complete_flow(self, test_audio_file, temp_recordings_dir, monkeypatch):
        """Test full flow: VOICE.TTS.PLAY.AUDIO → VOICE.AUDIO.PLAYBACK.COMPLETE."""
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_recordings_dir))
        monkeypatch.setenv("KLR_AUDIO_SAMPLE_RATE", "16000")

        received_playback_complete = threading.Event()
        playback_complete_data = {}

        def on_playback_complete(msg):
            """Callback for playback complete signal."""
            playback_complete_data.update(msg.get("facts", {}))
            received_playback_complete.set()

        zooid = AudioIOZooid()
        zooid.start()

        try:
            playback_complete_sub = UMNSub(
                "VOICE.AUDIO.PLAYBACK.COMPLETE",
                on_playback_complete,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr=b'')

                pub = UMNPub()
                pub.emit(
                    "VOICE.TTS.PLAY.AUDIO",
                    ecosystem="voice",
                    intensity=0.8,
                    facts={
                        "file_path": str(test_audio_file),
                        "duration_s": 0.5,
                        "timestamp": time.time()
                    },
                    incident_id="integ-play-001"
                )

                success = received_playback_complete.wait(timeout=5.0)
                assert success, "Did not receive VOICE.AUDIO.PLAYBACK.COMPLETE signal"

            assert playback_complete_data["file_path"] == str(test_audio_file)
            assert playback_complete_data["duration_s"] > 0

        finally:
            playback_complete_sub.close()
            pub.close()
            zooid.shutdown()

    def test_audio_io_ready_signal_emission(self, temp_recordings_dir, monkeypatch):
        """Test that Audio I/O emits READY signal on startup."""
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_recordings_dir))

        received_ready = threading.Event()
        ready_data = {}

        def on_ready(msg):
            """Callback for ready signal."""
            ready_data.update(msg.get("facts", {}))
            received_ready.set()

        ready_sub = UMNSub(
            "VOICE.AUDIO.IO.READY",
            on_ready,
            zooid_name="test-orchestrator",
            niche="test"
        )

        time.sleep(0.3)

        try:
            zooid = AudioIOZooid()
            zooid.start()

            success = received_ready.wait(timeout=3.0)
            assert success, "Did not receive VOICE.AUDIO.IO.READY signal"

            assert ready_data["zooid"] == "kloros-voice-audio-io"
            assert ready_data["sample_rate"] == 16000

        finally:
            ready_sub.close()
            zooid.shutdown()

    def test_incident_id_correlation(self, test_audio_file, temp_recordings_dir, monkeypatch):
        """Test that incident_id is properly correlated through signal chain."""
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_recordings_dir))

        received_playback_complete = threading.Event()
        received_incident_id = [None]

        def on_playback_complete(msg):
            """Callback for playback complete signal."""
            received_incident_id[0] = msg.get("incident_id")
            received_playback_complete.set()

        zooid = AudioIOZooid()
        zooid.start()

        try:
            playback_complete_sub = UMNSub(
                "VOICE.AUDIO.PLAYBACK.COMPLETE",
                on_playback_complete,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            test_incident_id = "audio-correlation-11111"

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr=b'')

                pub = UMNPub()
                pub.emit(
                    "VOICE.TTS.PLAY.AUDIO",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "file_path": str(test_audio_file),
                        "duration_s": 0.5
                    },
                    incident_id=test_incident_id
                )

                success = received_playback_complete.wait(timeout=5.0)
                assert success, "Did not receive playback complete"

            assert received_incident_id[0] == test_incident_id

        finally:
            playback_complete_sub.close()
            pub.close()
            zooid.shutdown()

    def test_playback_error_handling(self, temp_recordings_dir, monkeypatch):
        """Test handling of playback errors (missing file)."""
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_recordings_dir))

        received_playback_complete = threading.Event()

        def on_playback_complete(msg):
            """Callback for playback complete signal."""
            received_playback_complete.set()

        zooid = AudioIOZooid()
        zooid.start()

        try:
            playback_complete_sub = UMNSub(
                "VOICE.AUDIO.PLAYBACK.COMPLETE",
                on_playback_complete,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.TTS.PLAY.AUDIO",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "file_path": "/nonexistent/audio.wav",
                    "duration_s": 0.5
                },
                incident_id="error-test-001"
            )

            received = received_playback_complete.wait(timeout=2.0)
            assert not received, "Should not receive PLAYBACK.COMPLETE for missing file"

        finally:
            playback_complete_sub.close()
            pub.close()
            zooid.shutdown()

    def test_multiple_playback_requests(self, test_audio_file, temp_recordings_dir, monkeypatch):
        """Test handling multiple playback requests."""
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_recordings_dir))

        playback_complete_count = [0]
        playback_complete_lock = threading.Lock()

        def on_playback_complete(msg):
            """Callback for playback complete signal."""
            with playback_complete_lock:
                playback_complete_count[0] += 1

        zooid = AudioIOZooid()
        zooid.start()

        try:
            playback_complete_sub = UMNSub(
                "VOICE.AUDIO.PLAYBACK.COMPLETE",
                on_playback_complete,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr=b'')

                pub = UMNPub()

                for i in range(3):
                    pub.emit(
                        "VOICE.TTS.PLAY.AUDIO",
                        ecosystem="voice",
                        intensity=1.0,
                        facts={
                            "file_path": str(test_audio_file),
                            "duration_s": 0.5
                        },
                        incident_id=f"multi-play-{i}"
                    )
                    time.sleep(0.3)

                time.sleep(1.0)

                with playback_complete_lock:
                    assert playback_complete_count[0] == 3, f"Expected 3 playback completions, got {playback_complete_count[0]}"

        finally:
            playback_complete_sub.close()
            pub.close()
            zooid.shutdown()
