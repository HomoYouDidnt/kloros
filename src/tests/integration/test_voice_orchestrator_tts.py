"""Integration tests for Orchestrator → TTS signal flow.

Tests the communication between orchestrator and TTS zooid via real UMN.
No mocks - uses actual UMN pub/sub with subprocess coordination.
"""
import os
import sys
import time
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus_v2 import UMNPub, UMNSub
from src.voice.kloros_voice_tts import TTSZooid


@dataclass
class MockSynthesisResult:
    """Mock TTS synthesis result."""
    audio_path: str
    duration_s: float
    sample_rate: int
    voice: str


@pytest.fixture
def temp_tts_dir():
    """Create temporary TTS output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_tts_backend(temp_tts_dir):
    """Mock TTS backend for integration testing."""
    mock_backend = MagicMock()

    def mock_synthesize(text, sample_rate=22050, voice=None, out_dir=None):
        out_path = Path(out_dir or temp_tts_dir) / f"tts_{time.time()}.wav"
        out_path.touch()
        return MockSynthesisResult(
            audio_path=str(out_path),
            duration_s=len(text.split()) * 0.5,
            sample_rate=sample_rate,
            voice=voice or "default"
        )

    mock_backend.synthesize = mock_synthesize
    return mock_backend


@pytest.mark.integration
class TestOrchestratorTTSIntegration:
    """Test Orchestrator → TTS signal coordination."""

    def test_speak_request_to_audio_ready_flow(self, temp_tts_dir, mock_tts_backend, monkeypatch):
        """Test full flow: VOICE.ORCHESTRATOR.SPEAK → VOICE.TTS.AUDIO.READY."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        received_audio_ready = threading.Event()
        audio_ready_data = {}

        def on_audio_ready(msg):
            """Callback for audio ready signal."""
            audio_ready_data.update(msg.get("facts", {}))
            received_audio_ready.set()

        zooid = TTSZooid()
        zooid.tts_backend = mock_tts_backend
        zooid.start()

        try:
            audio_ready_sub = UMNSub(
                "VOICE.TTS.AUDIO.READY",
                on_audio_ready,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.SPEAK",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "text": "Hello integration test",
                    "urgency": 0.7
                },
                incident_id="integ-tts-001"
            )

            success = received_audio_ready.wait(timeout=5.0)
            assert success, "Did not receive VOICE.TTS.AUDIO.READY signal"

            assert audio_ready_data["text"] == "Hello integration test"
            assert "file_path" in audio_ready_data
            assert Path(audio_ready_data["file_path"]).exists()
            assert audio_ready_data["duration_s"] > 0

        finally:
            audio_ready_sub.close()
            pub.close()
            zooid.shutdown()

    def test_speak_request_to_play_audio_flow(self, temp_tts_dir, mock_tts_backend, monkeypatch):
        """Test full flow: VOICE.ORCHESTRATOR.SPEAK → VOICE.TTS.PLAY.AUDIO."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        received_play_audio = threading.Event()
        play_audio_data = {}

        def on_play_audio(msg):
            """Callback for play audio signal."""
            play_audio_data.update(msg.get("facts", {}))
            received_play_audio.set()

        zooid = TTSZooid()
        zooid.tts_backend = mock_tts_backend
        zooid.start()

        try:
            play_audio_sub = UMNSub(
                "VOICE.TTS.PLAY.AUDIO",
                on_play_audio,
                zooid_name="test-audio-io",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.SPEAK",
                ecosystem="voice",
                intensity=0.8,
                facts={
                    "text": "Test playback signal",
                    "urgency": 0.9
                },
                incident_id="integ-tts-002"
            )

            success = received_play_audio.wait(timeout=5.0)
            assert success, "Did not receive VOICE.TTS.PLAY.AUDIO signal"

            assert "file_path" in play_audio_data
            assert Path(play_audio_data["file_path"]).exists()

        finally:
            play_audio_sub.close()
            pub.close()
            zooid.shutdown()

    def test_tts_ready_signal_emission(self, temp_tts_dir, mock_tts_backend, monkeypatch):
        """Test that TTS emits READY signal on startup."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        received_ready = threading.Event()
        ready_data = {}

        def on_ready(msg):
            """Callback for ready signal."""
            ready_data.update(msg.get("facts", {}))
            received_ready.set()

        ready_sub = UMNSub(
            "VOICE.TTS.READY",
            on_ready,
            zooid_name="test-orchestrator",
            niche="test"
        )

        time.sleep(0.3)

        try:
            zooid = TTSZooid()
            zooid.tts_backend = mock_tts_backend
            zooid.start()

            success = received_ready.wait(timeout=3.0)
            assert success, "Did not receive VOICE.TTS.READY signal"

            assert ready_data["zooid"] == "kloros-voice-tts"
            assert ready_data["backend"] == "mock"

        finally:
            ready_sub.close()
            zooid.shutdown()

    def test_incident_id_correlation(self, temp_tts_dir, mock_tts_backend, monkeypatch):
        """Test that incident_id is properly correlated through signal chain."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        received_audio_ready = threading.Event()
        received_incident_id = [None]

        def on_audio_ready(msg):
            """Callback for audio ready signal."""
            received_incident_id[0] = msg.get("incident_id")
            received_audio_ready.set()

        zooid = TTSZooid()
        zooid.tts_backend = mock_tts_backend
        zooid.start()

        try:
            audio_ready_sub = UMNSub(
                "VOICE.TTS.AUDIO.READY",
                on_audio_ready,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            test_incident_id = "tts-correlation-67890"

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.SPEAK",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "text": "Correlation test"
                },
                incident_id=test_incident_id
            )

            success = received_audio_ready.wait(timeout=5.0)
            assert success, "Did not receive audio ready"

            assert received_incident_id[0] == test_incident_id

        finally:
            audio_ready_sub.close()
            pub.close()
            zooid.shutdown()

    def test_urgency_propagation(self, temp_tts_dir, mock_tts_backend, monkeypatch):
        """Test that urgency value is propagated to PLAY.AUDIO signal."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        received_play_audio = threading.Event()
        received_intensity = [None]

        def on_play_audio(msg):
            """Callback for play audio signal."""
            received_intensity[0] = msg.get("intensity")
            received_play_audio.set()

        zooid = TTSZooid()
        zooid.tts_backend = mock_tts_backend
        zooid.start()

        try:
            play_audio_sub = UMNSub(
                "VOICE.TTS.PLAY.AUDIO",
                on_play_audio,
                zooid_name="test-audio-io",
                niche="test"
            )

            time.sleep(0.5)

            test_urgency = 0.85

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.SPEAK",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "text": "Urgent message",
                    "urgency": test_urgency
                },
                incident_id="urgency-test-001"
            )

            success = received_play_audio.wait(timeout=5.0)
            assert success, "Did not receive play audio signal"

            assert received_intensity[0] == test_urgency

        finally:
            play_audio_sub.close()
            pub.close()
            zooid.shutdown()

    def test_multiple_speak_requests(self, temp_tts_dir, mock_tts_backend, monkeypatch):
        """Test handling multiple speak requests."""
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_tts_dir))

        audio_ready_count = [0]
        audio_ready_lock = threading.Lock()

        def on_audio_ready(msg):
            """Callback for audio ready signal."""
            with audio_ready_lock:
                audio_ready_count[0] += 1

        zooid = TTSZooid()
        zooid.tts_backend = mock_tts_backend
        zooid.start()

        try:
            audio_ready_sub = UMNSub(
                "VOICE.TTS.AUDIO.READY",
                on_audio_ready,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()

            for i in range(3):
                pub.emit(
                    "VOICE.ORCHESTRATOR.SPEAK",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "text": f"Message {i}"
                    },
                    incident_id=f"multi-speak-{i}"
                )
                time.sleep(0.2)

            time.sleep(1.0)

            with audio_ready_lock:
                assert audio_ready_count[0] == 3, f"Expected 3 audio ready signals, got {audio_ready_count[0]}"

        finally:
            audio_ready_sub.close()
            pub.close()
            zooid.shutdown()
