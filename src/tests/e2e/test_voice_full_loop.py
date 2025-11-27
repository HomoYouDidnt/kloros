"""End-to-end tests for full voice conversation loop.

Tests the complete voice interaction flow across all zooids.
This is a minimal E2E test - comprehensive testing happens at unit/integration layers.
"""
import os
import sys
import time
import wave
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from dataclasses import dataclass

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus_v2 import UMNPub, UMNSub
from src.voice.kloros_voice_audio_io import AudioIOZooid
from src.voice.kloros_voice_stt import STTZooid
from src.voice.kloros_voice_tts import TTSZooid


@dataclass
class MockTranscriptionResult:
    """Mock STT transcription result."""
    transcript: str
    confidence: float
    lang: str = "en"


@dataclass
class MockSynthesisResult:
    """Mock TTS synthesis result."""
    audio_path: str
    duration_s: float
    sample_rate: int
    voice: str


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as recordings_dir, \
         tempfile.TemporaryDirectory() as tts_dir:
        yield {
            "recordings": Path(recordings_dir),
            "tts": Path(tts_dir)
        }


@pytest.fixture
def test_audio_input(temp_dirs):
    """Create a test audio input file."""
    test_wav = temp_dirs["recordings"] / "test_input.wav"
    audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000)) * 32767).astype(np.int16)
    with wave.open(str(test_wav), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_data.tobytes())
    return test_wav


@pytest.fixture
def mock_stt_backend():
    """Mock STT backend for E2E testing."""
    mock_backend = MagicMock()

    def mock_transcribe(audio, sample_rate, lang="en"):
        return MockTranscriptionResult(
            transcript="what is the weather today",
            confidence=0.94,
            lang=lang
        )

    mock_backend.transcribe = mock_transcribe
    return mock_backend


@pytest.fixture
def mock_tts_backend(temp_dirs):
    """Mock TTS backend for E2E testing."""
    mock_backend = MagicMock()

    def mock_synthesize(text, sample_rate=22050, voice=None, out_dir=None):
        out_path = Path(out_dir or temp_dirs["tts"]) / f"tts_e2e_{time.time()}.wav"

        audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, 11025)) * 32767).astype(np.int16)
        with wave.open(str(out_path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data.tobytes())

        return MockSynthesisResult(
            audio_path=str(out_path),
            duration_s=len(text.split()) * 0.5,
            sample_rate=sample_rate,
            voice=voice or "default"
        )

    mock_backend.synthesize = mock_synthesize
    return mock_backend


@pytest.mark.e2e
@pytest.mark.slow
class TestVoiceFullLoop:
    """End-to-end tests for complete voice interaction."""

    def test_basic_voice_loop_simulation(self, temp_dirs, test_audio_input,
                                         mock_stt_backend, mock_tts_backend, monkeypatch):
        """Test basic voice loop: Audio Capture → STT → (Orchestrator) → TTS → Audio Playback.

        This simulates a minimal conversation loop without the full orchestrator.
        """
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_dirs["recordings"]))
        monkeypatch.setenv("KLR_AUDIO_SAMPLE_RATE", "16000")
        monkeypatch.setenv("KLR_ENABLE_STT", "1")
        monkeypatch.setenv("KLR_STT_BACKEND", "mock")
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_dirs["tts"]))

        transcription_received = threading.Event()
        audio_ready_received = threading.Event()
        playback_complete_received = threading.Event()

        transcription_text = [None]
        synthesized_audio_path = [None]

        def on_transcription(msg):
            """Handle transcription signal."""
            transcription_text[0] = msg.get("facts", {}).get("text")
            transcription_received.set()

        def on_audio_ready(msg):
            """Handle audio ready signal and trigger playback."""
            audio_path = msg.get("facts", {}).get("file_path")
            synthesized_audio_path[0] = audio_path
            audio_ready_received.set()

        def on_playback_complete(msg):
            """Handle playback complete signal."""
            playback_complete_received.set()

        with patch('src.voice.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend), \
             patch('src.voice.kloros_voice_tts.create_tts_backend', return_value=mock_tts_backend):

            audio_io = AudioIOZooid()
            stt = STTZooid()
            tts = TTSZooid()

            audio_io.start()
            stt.start()
            tts.start()

        try:
            transcription_sub = UMNSub(
                "VOICE.STT.TRANSCRIPTION",
                on_transcription,
                zooid_name="test-e2e-orchestrator",
                niche="test"
            )

            audio_ready_sub = UMNSub(
                "VOICE.TTS.AUDIO.READY",
                on_audio_ready,
                zooid_name="test-e2e-orchestrator",
                niche="test"
            )

            playback_complete_sub = UMNSub(
                "VOICE.AUDIO.PLAYBACK.COMPLETE",
                on_playback_complete,
                zooid_name="test-e2e-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()

            print("[E2E] Step 1: Simulating audio capture")
            pub.emit(
                "VOICE.AUDIO.CAPTURED",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "audio_file": str(test_audio_input),
                    "duration": 1.0,
                    "sample_rate": 16000,
                    "timestamp": time.time()
                },
                incident_id="e2e-loop-001"
            )

            print("[E2E] Step 2: Waiting for transcription...")
            success = transcription_received.wait(timeout=5.0)
            assert success, "Did not receive transcription"
            assert transcription_text[0] is not None
            print(f"[E2E] Transcribed: {transcription_text[0]}")

            print("[E2E] Step 3: Simulating orchestrator response")
            pub.emit(
                "VOICE.ORCHESTRATOR.SPEAK",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "text": f"You said: {transcription_text[0]}",
                    "urgency": 0.7
                },
                incident_id="e2e-loop-001"
            )

            print("[E2E] Step 4: Waiting for TTS synthesis...")
            success = audio_ready_received.wait(timeout=5.0)
            assert success, "Did not receive TTS audio ready"
            assert synthesized_audio_path[0] is not None
            assert Path(synthesized_audio_path[0]).exists()
            print(f"[E2E] Synthesized: {synthesized_audio_path[0]}")

            print("[E2E] Step 5: Waiting for playback completion...")
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr=b'')

                success = playback_complete_received.wait(timeout=5.0)
                assert success, "Did not receive playback complete"
                print("[E2E] Playback complete")

            print("[E2E] ✅ Full voice loop successful")

        finally:
            transcription_sub.close()
            audio_ready_sub.close()
            playback_complete_sub.close()
            pub.close()

            audio_io.shutdown()
            stt.shutdown()
            tts.shutdown()

    def test_all_zooids_start_and_emit_ready_signals(self, temp_dirs,
                                                       mock_stt_backend, mock_tts_backend, monkeypatch):
        """Test that all zooids can start and emit READY signals."""
        monkeypatch.setenv("KLR_AUDIO_RECORDINGS_DIR", str(temp_dirs["recordings"]))
        monkeypatch.setenv("KLR_ENABLE_STT", "1")
        monkeypatch.setenv("KLR_STT_BACKEND", "mock")
        monkeypatch.setenv("KLR_ENABLE_TTS", "1")
        monkeypatch.setenv("KLR_TTS_BACKEND", "mock")
        monkeypatch.setenv("KLR_TTS_OUT_DIR", str(temp_dirs["tts"]))

        ready_signals = {
            "audio_io": threading.Event(),
            "stt": threading.Event(),
            "tts": threading.Event()
        }

        def on_audio_io_ready(msg):
            ready_signals["audio_io"].set()

        def on_stt_ready(msg):
            ready_signals["stt"].set()

        def on_tts_ready(msg):
            ready_signals["tts"].set()

        audio_io_ready_sub = UMNSub(
            "VOICE.AUDIO.IO.READY",
            on_audio_io_ready,
            zooid_name="test-e2e",
            niche="test"
        )

        stt_ready_sub = UMNSub(
            "VOICE.STT.READY",
            on_stt_ready,
            zooid_name="test-e2e",
            niche="test"
        )

        tts_ready_sub = UMNSub(
            "VOICE.TTS.READY",
            on_tts_ready,
            zooid_name="test-e2e",
            niche="test"
        )

        time.sleep(0.3)

        try:
            with patch('src.voice.kloros_voice_stt.create_stt_backend', return_value=mock_stt_backend), \
                 patch('src.voice.kloros_voice_tts.create_tts_backend', return_value=mock_tts_backend):

                audio_io = AudioIOZooid()
                stt = STTZooid()
                tts = TTSZooid()

                audio_io.start()
                stt.start()
                tts.start()

            for zooid_name, event in ready_signals.items():
                success = event.wait(timeout=3.0)
                assert success, f"Did not receive READY signal from {zooid_name}"
                print(f"[E2E] ✅ {zooid_name} is ready")

        finally:
            audio_io_ready_sub.close()
            stt_ready_sub.close()
            tts_ready_sub.close()

            audio_io.shutdown()
            stt.shutdown()
            tts.shutdown()
