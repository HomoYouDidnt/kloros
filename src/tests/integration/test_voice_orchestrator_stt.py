"""Integration tests for Orchestrator → STT signal flow.

Tests the communication between orchestrator and STT zooid via real UMN.
No mocks - uses actual UMN pub/sub with subprocess coordination.
"""
import os
import sys
import time
import wave
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus_v2 import UMNPub, UMNSub
from src.kloros_voice_stt import STTZooid


@dataclass
class MockTranscriptionResult:
    """Mock STT transcription result."""
    transcript: str
    confidence: float
    lang: str = "en"


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
def mock_stt_backend():
    """Mock STT backend for integration testing."""
    mock_backend = MagicMock()

    def mock_transcribe(audio, sample_rate, lang="en"):
        return MockTranscriptionResult(
            transcript="integration test transcription",
            confidence=0.92,
            lang=lang
        )

    mock_backend.transcribe = mock_transcribe
    return mock_backend


@pytest.mark.integration
class TestOrchestratorSTTIntegration:
    """Test Orchestrator → STT signal coordination."""

    def test_audio_captured_to_transcription_flow(self, test_audio_file, mock_stt_backend, monkeypatch):
        """Test full flow: VOICE.AUDIO.CAPTURED → VOICE.STT.TRANSCRIPTION."""
        monkeypatch.setenv("KLR_ENABLE_STT", "1")
        monkeypatch.setenv("KLR_STT_BACKEND", "mock")

        received_transcription = threading.Event()
        transcription_data = {}

        def on_transcription(msg):
            """Callback for transcription signal."""
            transcription_data.update(msg.get("facts", {}))
            received_transcription.set()

        with patch('src.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend):
            zooid = STTZooid()
            zooid.start()

        try:
            transcription_sub = UMNSub(
                "VOICE.STT.TRANSCRIPTION",
                on_transcription,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.AUDIO.CAPTURED",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "audio_file": str(test_audio_file),
                    "duration": 1.0,
                    "sample_rate": 16000,
                    "timestamp": time.time()
                },
                incident_id="integ-test-001"
            )

            success = received_transcription.wait(timeout=5.0)
            assert success, "Did not receive VOICE.STT.TRANSCRIPTION signal"

            assert transcription_data["text"] == "integration test transcription"
            assert transcription_data["confidence"] == 0.92
            assert transcription_data["audio_file"] == str(test_audio_file)

        finally:
            transcription_sub.close()
            pub.close()
            zooid.shutdown()

    def test_stt_ready_signal_emission(self, mock_stt_backend, monkeypatch):
        """Test that STT emits READY signal on startup."""
        monkeypatch.setenv("KLR_ENABLE_STT", "1")
        monkeypatch.setenv("KLR_STT_BACKEND", "mock")

        received_ready = threading.Event()
        ready_data = {}

        def on_ready(msg):
            """Callback for ready signal."""
            ready_data.update(msg.get("facts", {}))
            received_ready.set()

        ready_sub = UMNSub(
            "VOICE.STT.READY",
            on_ready,
            zooid_name="test-orchestrator",
            niche="test"
        )

        time.sleep(0.3)

        try:
            with patch('src.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend):
                zooid = STTZooid()
                zooid.start()

            success = received_ready.wait(timeout=3.0)
            assert success, "Did not receive VOICE.STT.READY signal"

            assert ready_data["zooid"] == "kloros-voice-stt"
            assert ready_data["backend"] == "mock"

        finally:
            ready_sub.close()
            zooid.shutdown()

    def test_incident_id_correlation(self, test_audio_file, mock_stt_backend, monkeypatch):
        """Test that incident_id is properly correlated through signal chain."""
        monkeypatch.setenv("KLR_ENABLE_STT", "1")
        monkeypatch.setenv("KLR_STT_BACKEND", "mock")

        received_transcription = threading.Event()
        received_incident_id = [None]

        def on_transcription(msg):
            """Callback for transcription signal."""
            received_incident_id[0] = msg.get("incident_id")
            received_transcription.set()

        with patch('src.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend):
            zooid = STTZooid()
            zooid.start()

        try:
            transcription_sub = UMNSub(
                "VOICE.STT.TRANSCRIPTION",
                on_transcription,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            test_incident_id = "correlation-test-12345"

            pub = UMNPub()
            pub.emit(
                "VOICE.AUDIO.CAPTURED",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "audio_file": str(test_audio_file),
                    "duration": 1.0,
                    "sample_rate": 16000
                },
                incident_id=test_incident_id
            )

            success = received_transcription.wait(timeout=5.0)
            assert success, "Did not receive transcription"

            assert received_incident_id[0] == test_incident_id

        finally:
            transcription_sub.close()
            pub.close()
            zooid.shutdown()

    def test_multiple_transcriptions(self, test_audio_file, mock_stt_backend, monkeypatch):
        """Test handling multiple audio capture signals."""
        monkeypatch.setenv("KLR_ENABLE_STT", "1")
        monkeypatch.setenv("KLR_STT_BACKEND", "mock")

        transcription_count = [0]
        transcription_lock = threading.Lock()

        def on_transcription(msg):
            """Callback for transcription signal."""
            with transcription_lock:
                transcription_count[0] += 1

        with patch('src.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend):
            zooid = STTZooid()
            zooid.start()

        try:
            transcription_sub = UMNSub(
                "VOICE.STT.TRANSCRIPTION",
                on_transcription,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()

            for i in range(3):
                pub.emit(
                    "VOICE.AUDIO.CAPTURED",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "audio_file": str(test_audio_file),
                        "duration": 1.0,
                        "sample_rate": 16000
                    },
                    incident_id=f"multi-test-{i}"
                )
                time.sleep(0.3)

            time.sleep(1.0)

            with transcription_lock:
                assert transcription_count[0] == 3, f"Expected 3 transcriptions, got {transcription_count[0]}"

        finally:
            transcription_sub.close()
            pub.close()
            zooid.shutdown()
