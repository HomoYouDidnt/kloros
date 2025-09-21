"""Smoke tests for turn orchestrator end-to-end functionality."""

import os
import tempfile
import time
from typing import Dict, List

import numpy as np
import pytest

from src.core.turn import new_trace_id, run_turn
from src.stt.mock_backend import MockSttBackend
from src.tts.mock_backend import MockTtsBackend


class EventCapture:
    """Capture log events for testing."""

    def __init__(self):
        self.events: List[Dict] = []

    def log_event(self, name: str, **payload):
        """Capture a log event."""
        event = {"name": name, **payload}
        self.events.append(event)

    def get_events_by_name(self, name: str) -> List[Dict]:
        """Get all events with a specific name."""
        return [event for event in self.events if event["name"] == name]

    def has_event(self, name: str) -> bool:
        """Check if an event with given name was logged."""
        return len(self.get_events_by_name(name)) > 0

    def clear(self):
        """Clear all captured events."""
        self.events.clear()


class TestTurnOrchestrator:
    """Test turn orchestrator functionality."""

    @pytest.fixture
    def sample_rate(self):
        """Standard sample rate for tests."""
        return 16000

    @pytest.fixture
    def event_capture(self):
        """Event capture fixture."""
        return EventCapture()

    @pytest.fixture
    def stt_backend(self):
        """Mock STT backend fixture."""
        return MockSttBackend(transcript="hello world", confidence=0.9)

    @pytest.fixture
    def tts_backend(self):
        """Mock TTS backend fixture."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield MockTtsBackend(out_dir=tmp_dir)

    @pytest.fixture
    def reason_fn(self):
        """Simple reason function fixture."""
        def simple_reason(transcript: str) -> str:
            if not transcript:
                return ""
            return "ok"
        return simple_reason

    def _create_test_audio(self, sample_rate: int) -> np.ndarray:
        """Create test audio: 0.5s noise + 0.8s tone + 0.2s noise."""
        # 0.5s of -60 dBFS noise
        noise1_samples = int(0.5 * sample_rate)
        rng = np.random.default_rng(42)
        noise1 = rng.normal(0, 0.001, noise1_samples).astype(np.float32)  # ~-60 dBFS

        # 0.8s of 440 Hz tone at -20 dBFS
        tone_duration = 0.8
        tone_samples = int(tone_duration * sample_rate)
        t = np.linspace(0, tone_duration, tone_samples, endpoint=False)
        tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        # Scale to -20 dBFS (RMS = amplitude/sqrt(2), so amplitude = RMS * sqrt(2))
        target_rms = 10**(-20.0 / 20)  # -20 dBFS RMS
        target_amplitude = target_rms * np.sqrt(2)
        tone = tone * target_amplitude

        # 0.2s more noise
        noise2_samples = int(0.2 * sample_rate)
        noise2 = rng.normal(0, 0.001, noise2_samples).astype(np.float32)

        return np.concatenate([noise1, tone, noise2])

    def _create_noise_only_audio(self, sample_rate: int) -> np.ndarray:
        """Create audio with only low-level noise."""
        duration_s = 1.5
        samples = int(duration_s * sample_rate)
        rng = np.random.default_rng(123)
        return rng.normal(0, 0.001, samples).astype(np.float32)  # ~-60 dBFS

    def test_turn_ok_end_to_end_mock(self, sample_rate, event_capture, stt_backend, tts_backend, reason_fn):
        """Test successful end-to-end turn with mock backends."""
        # Create test audio with voice activity
        audio = self._create_test_audio(sample_rate)

        # Run turn with threshold that should detect the tone
        summary = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=reason_fn,
            tts=tts_backend,
            vad_threshold_dbfs=-50.0,
            frame_ms=30,
            hop_ms=10,
            attack_ms=50,
            release_ms=200,
            min_active_ms=200,
            margin_db=2.0,
            max_turn_seconds=30.0,
            logger=event_capture
        )

        # Verify summary
        assert summary.ok is True
        assert summary.reason == "ok"
        assert summary.transcript == "hello world"
        assert summary.reply_text == "ok"
        assert summary.tts is not None
        assert summary.vad is not None
        assert summary.timings_ms is not None

        # Verify TTS output file exists
        assert os.path.exists(summary.tts.audio_path)
        assert summary.tts.duration_s == 0.1  # Mock TTS duration

        # Verify event sequence
        assert event_capture.has_event("turn_start")
        assert event_capture.has_event("vad_gate")
        assert event_capture.has_event("stt_done")
        assert event_capture.has_event("reason_done")
        assert event_capture.has_event("tts_done")
        assert event_capture.has_event("turn_done")

        # Verify VAD gate opened
        vad_events = event_capture.get_events_by_name("vad_gate")
        assert len(vad_events) == 1
        assert vad_events[0]["open"] is True

        # Verify turn completion
        turn_done_events = event_capture.get_events_by_name("turn_done")
        assert len(turn_done_events) == 1
        assert turn_done_events[0]["ok"] is True

        # Verify trace_id is present in all events
        for event in event_capture.events:
            assert "trace_id" in event
            assert event["trace_id"] == summary.trace_id

    def test_turn_no_voice_skips_stt(self, sample_rate, event_capture, stt_backend, tts_backend, reason_fn):
        """Test that no voice activity skips STT and TTS."""
        # Create noise-only audio
        audio = self._create_noise_only_audio(sample_rate)

        # Run turn with threshold that won't detect noise
        summary = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=reason_fn,
            tts=tts_backend,
            vad_threshold_dbfs=-50.0,
            frame_ms=30,
            hop_ms=10,
            attack_ms=50,
            release_ms=200,
            min_active_ms=200,
            margin_db=2.0,
            max_turn_seconds=30.0,
            logger=event_capture
        )

        # Verify summary
        assert summary.ok is False
        assert summary.reason == "no_voice"
        assert summary.transcript == ""
        assert summary.reply_text == ""
        assert summary.tts is None
        assert summary.vad is not None

        # Verify event sequence (should stop after VAD)
        assert event_capture.has_event("turn_start")
        assert event_capture.has_event("vad_gate")
        assert event_capture.has_event("turn_done")

        # Should NOT have STT, reason, or TTS events
        assert not event_capture.has_event("stt_done")
        assert not event_capture.has_event("reason_done")
        assert not event_capture.has_event("tts_done")

        # Verify VAD gate was closed
        vad_events = event_capture.get_events_by_name("vad_gate")
        assert len(vad_events) == 1
        assert vad_events[0]["open"] is False

        # Verify turn completion indicates no voice
        turn_done_events = event_capture.get_events_by_name("turn_done")
        assert len(turn_done_events) == 1
        assert turn_done_events[0]["ok"] is False
        assert turn_done_events[0]["reason"] == "no_voice"

    def test_timeout_abort(self, sample_rate, event_capture, stt_backend, tts_backend):
        """Test that turn times out appropriately."""
        # Create a reason function that takes time
        def slow_reason_fn(transcript: str) -> str:
            time.sleep(0.05)  # Sleep for 50ms
            return "slow response"

        # Create test audio with voice activity
        audio = self._create_test_audio(sample_rate)

        # Run turn with timeout shorter than the slow reason function
        summary = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=slow_reason_fn,
            tts=tts_backend,
            vad_threshold_dbfs=-50.0,
            frame_ms=30,
            hop_ms=10,
            attack_ms=50,
            release_ms=200,
            min_active_ms=200,
            margin_db=2.0,
            max_turn_seconds=0.01,  # 10ms timeout, less than 50ms sleep
            logger=event_capture
        )

        # Verify summary indicates timeout
        assert summary.ok is False
        assert summary.reason == "timeout"

        # Should have turn_done event with timeout reason
        turn_done_events = event_capture.get_events_by_name("turn_done")
        assert len(turn_done_events) == 1
        assert turn_done_events[0]["ok"] is False
        assert "timeout" in turn_done_events[0]["reason"]

        # Should have at least gotten through VAD and STT
        assert event_capture.has_event("vad_gate")
        assert event_capture.has_event("stt_done")

    def test_trace_id_generation(self, sample_rate, event_capture, stt_backend, reason_fn):
        """Test trace ID generation and propagation."""
        audio = self._create_test_audio(sample_rate)

        # Test with explicit trace_id
        custom_trace = "test-trace-123"
        summary1 = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=reason_fn,
            vad_threshold_dbfs=-50.0,
            logger=event_capture,
            trace_id=custom_trace
        )

        assert summary1.trace_id == custom_trace

        # Clear events and test auto-generation
        event_capture.clear()
        summary2 = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=reason_fn,
            vad_threshold_dbfs=-50.0,
            logger=event_capture
        )

        # Should generate a trace ID
        assert summary2.trace_id is not None
        assert len(summary2.trace_id) > 0
        assert summary2.trace_id != custom_trace

        # All events should have the generated trace_id
        for event in event_capture.events:
            assert event["trace_id"] == summary2.trace_id

    def test_no_tts_backend(self, sample_rate, event_capture, stt_backend, reason_fn):
        """Test turn without TTS backend."""
        audio = self._create_test_audio(sample_rate)

        summary = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=reason_fn,
            tts=None,  # No TTS backend
            vad_threshold_dbfs=-50.0,
            logger=event_capture
        )

        # Turn should succeed but without TTS
        assert summary.ok is True
        assert summary.transcript == "hello world"
        assert summary.reply_text == "ok"
        assert summary.tts is None

        # Should have all events except tts_done
        assert event_capture.has_event("turn_start")
        assert event_capture.has_event("vad_gate")
        assert event_capture.has_event("stt_done")
        assert event_capture.has_event("reason_done")
        assert event_capture.has_event("turn_done")
        assert not event_capture.has_event("tts_done")

    def test_empty_reason_response(self, sample_rate, event_capture, stt_backend, tts_backend):
        """Test turn with reason function that returns empty response."""
        def empty_reason_fn(transcript: str) -> str:
            return ""

        audio = self._create_test_audio(sample_rate)

        summary = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=empty_reason_fn,
            tts=tts_backend,
            vad_threshold_dbfs=-50.0,
            logger=event_capture
        )

        # Turn should succeed but with empty reply
        assert summary.ok is True
        assert summary.transcript == "hello world"
        assert summary.reply_text == ""
        assert summary.tts is None  # No TTS for empty text

        # Should have reasoning event but no TTS
        assert event_capture.has_event("reason_done")
        assert not event_capture.has_event("tts_done")

        reason_events = event_capture.get_events_by_name("reason_done")
        assert reason_events[0]["tokens_out"] == 0

    def test_timing_metrics(self, sample_rate, event_capture, stt_backend, tts_backend, reason_fn):
        """Test that timing metrics are captured."""
        audio = self._create_test_audio(sample_rate)

        summary = run_turn(
            audio,
            sample_rate,
            stt=stt_backend,
            reason_fn=reason_fn,
            tts=tts_backend,
            vad_threshold_dbfs=-50.0,
            logger=event_capture
        )

        # Verify timing metrics exist
        assert summary.timings_ms is not None
        assert "vad_ms" in summary.timings_ms
        assert "stt_ms" in summary.timings_ms
        assert "reason_ms" in summary.timings_ms
        assert "tts_ms" in summary.timings_ms
        assert "total_ms" in summary.timings_ms

        # All timings should be positive
        for _stage, timing in summary.timings_ms.items():
            assert timing >= 0

        # Total should be greater than sum of parts (includes overhead)
        stage_total = (summary.timings_ms["vad_ms"] +
                      summary.timings_ms["stt_ms"] +
                      summary.timings_ms["reason_ms"] +
                      summary.timings_ms["tts_ms"])
        assert summary.timings_ms["total_ms"] >= stage_total


class TestHelperFunctions:
    """Test helper functions."""

    def test_new_trace_id(self):
        """Test trace ID generation."""
        trace1 = new_trace_id()
        trace2 = new_trace_id()

        # Should generate different IDs
        assert trace1 != trace2
        assert len(trace1) > 0
        assert len(trace2) > 0

        # Should be hex strings
        assert all(c in "0123456789abcdef" for c in trace1)
        assert all(c in "0123456789abcdef" for c in trace2)


class TestEventCapture:
    """Test the event capture helper used in tests."""

    def test_event_capture_basic(self):
        """Test basic event capture functionality."""
        capture = EventCapture()

        # Capture some events
        capture.log_event("test1", value=123)
        capture.log_event("test2", data="hello")
        capture.log_event("test1", value=456)

        # Verify capture
        assert len(capture.events) == 3
        assert capture.has_event("test1")
        assert capture.has_event("test2")
        assert not capture.has_event("test3")

        # Verify filtering
        test1_events = capture.get_events_by_name("test1")
        assert len(test1_events) == 2
        assert test1_events[0]["value"] == 123
        assert test1_events[1]["value"] == 456

        test2_events = capture.get_events_by_name("test2")
        assert len(test2_events) == 1
        assert test2_events[0]["data"] == "hello"

        # Test clear
        capture.clear()
        assert len(capture.events) == 0
        assert not capture.has_event("test1")
