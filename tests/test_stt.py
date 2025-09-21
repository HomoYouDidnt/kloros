"""Unit tests for STT (speech-to-text) functionality."""

import os
from unittest.mock import patch

import numpy as np
import pytest

from src.stt.base import SttResult, create_stt_backend
from src.stt.mock_backend import MockSttBackend


class TestSttFactory:
    """Test STT backend factory functionality."""

    def test_factory_mock(self):
        """Test that factory creates mock backend correctly."""
        backend = create_stt_backend("mock")

        # Verify it has the transcribe method
        assert hasattr(backend, "transcribe")
        assert callable(backend.transcribe)

        # Test basic transcription
        audio = np.random.randn(1600).astype(np.float32)  # 0.1s at 16kHz
        result = backend.transcribe(audio, 16000)

        # Verify result structure
        assert isinstance(result, SttResult)
        assert hasattr(result, "transcript")
        assert hasattr(result, "confidence")
        assert hasattr(result, "lang")
        assert hasattr(result, "raw")

        # Mock backend should return fixed values
        assert result.transcript == "hello world"
        assert result.confidence == 0.92
        assert result.lang == "en-US"

    def test_factory_mock_with_custom_params(self):
        """Test mock backend with custom parameters."""
        backend = create_stt_backend("mock", transcript="custom text", confidence=0.75)

        audio = np.random.randn(1600).astype(np.float32)
        result = backend.transcribe(audio, 16000)

        assert result.transcript == "custom text"
        assert result.confidence == 0.75

    def test_factory_unknown_backend(self):
        """Test that unknown backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown STT backend: unknown"):
            create_stt_backend("unknown")

    def test_factory_vosk_missing_model_graceful(self):
        """Test that Vosk backend fails gracefully when library is missing."""
        # Mock vosk import to fail
        with patch.dict('sys.modules', {'vosk': None}):
            with pytest.raises(RuntimeError, match="vosk library not available"):
                create_stt_backend("vosk")

            # Test with non-existent model directory - also fails on library unavailable
            with pytest.raises(RuntimeError, match="vosk library not available"):
                create_stt_backend("vosk", model_dir="/nonexistent/path")

            # Test with environment variable pointing to non-existent path
            with patch.dict(os.environ, {"KLR_VOSK_MODEL_DIR": "/another/nonexistent/path"}):
                with pytest.raises(RuntimeError, match="vosk library not available"):
                    create_stt_backend("vosk")


class TestMockBackend:
    """Test mock STT backend behavior."""

    def test_transcribe_shapes_and_types(self):
        """Test transcription with various audio shapes and verify types."""
        backend = MockSttBackend()

        # Test with different audio lengths
        test_cases = [
            (16000, 16000),  # 1 second at 16kHz
            (32000, 16000),  # 2 seconds at 16kHz
            (8000, 8000),    # 1 second at 8kHz
            (100, 16000),    # Very short audio
        ]

        for num_samples, sample_rate in test_cases:
            audio = np.random.randn(num_samples).astype(np.float32)
            result = backend.transcribe(audio, sample_rate)

            # Verify no exceptions and correct types
            assert isinstance(result, SttResult)
            assert isinstance(result.transcript, str)
            assert isinstance(result.confidence, float)
            assert isinstance(result.lang, str)
            assert isinstance(result.raw, dict)

            # Verify expected values
            assert result.transcript == "hello world"
            assert result.confidence == 0.92
            assert result.lang == "en-US"

    def test_lang_passthrough(self):
        """Test that language parameter is passed through correctly."""
        backend = MockSttBackend()
        audio = np.random.randn(1600).astype(np.float32)

        # Test different language codes
        test_langs = ["en-US", "en-GB", "es-ES", "fr-FR", None]

        for lang in test_langs:
            result = backend.transcribe(audio, 16000, lang=lang)
            expected_lang = lang or "en-US"
            assert result.lang == expected_lang

    def test_audio_data_ignored(self):
        """Test that mock backend ignores actual audio content."""
        backend = MockSttBackend()

        # Create different audio signals
        silence = np.zeros(1600, dtype=np.float32)
        noise = np.random.randn(1600).astype(np.float32)
        sine_wave = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 1600)).astype(np.float32)

        # All should return the same result
        result_silence = backend.transcribe(silence, 16000)
        result_noise = backend.transcribe(noise, 16000)
        result_sine = backend.transcribe(sine_wave, 16000)

        assert result_silence.transcript == result_noise.transcript == result_sine.transcript
        assert result_silence.confidence == result_noise.confidence == result_sine.confidence

    def test_raw_data_includes_metadata(self):
        """Test that raw data includes useful metadata."""
        backend = MockSttBackend()
        audio = np.random.randn(3200).astype(np.float32)
        result = backend.transcribe(audio, 16000)

        assert result.raw is not None
        assert result.raw["mock"] is True
        assert result.raw["audio_samples"] == 3200
        assert result.raw["sample_rate"] == 16000

    def test_custom_transcript_and_confidence(self):
        """Test mock backend with custom transcript and confidence values."""
        backend = MockSttBackend(transcript="test phrase", confidence=0.85)
        audio = np.random.randn(1600).astype(np.float32)
        result = backend.transcribe(audio, 16000)

        assert result.transcript == "test phrase"
        assert result.confidence == 0.85


class TestSttIntegration:
    """Test STT integration scenarios."""

    def test_empty_audio_handling(self):
        """Test behavior with empty or very short audio."""
        backend = MockSttBackend()

        # Empty audio
        empty_audio = np.array([], dtype=np.float32)
        result = backend.transcribe(empty_audio, 16000)
        assert isinstance(result, SttResult)
        assert result.raw["audio_samples"] == 0

        # Very short audio
        short_audio = np.array([0.1], dtype=np.float32)
        result = backend.transcribe(short_audio, 16000)
        assert isinstance(result, SttResult)
        assert result.raw["audio_samples"] == 1

    def test_audio_range_validation(self):
        """Test transcription with audio in different ranges."""
        backend = MockSttBackend()

        # Test with audio in expected [-1, 1] range
        normal_audio = np.random.uniform(-1, 1, 1600).astype(np.float32)
        result = backend.transcribe(normal_audio, 16000)
        assert isinstance(result, SttResult)

        # Test with audio outside normal range (should still work for mock)
        loud_audio = np.random.uniform(-2, 2, 1600).astype(np.float32)
        result = backend.transcribe(loud_audio, 16000)
        assert isinstance(result, SttResult)

        # Test with very quiet audio
        quiet_audio = np.random.uniform(-0.1, 0.1, 1600).astype(np.float32)
        result = backend.transcribe(quiet_audio, 16000)
        assert isinstance(result, SttResult)

    def test_different_sample_rates(self):
        """Test transcription with different sample rates."""
        backend = MockSttBackend()

        sample_rates = [8000, 16000, 22050, 44100, 48000]

        for sr in sample_rates:
            # Generate 0.1 second of audio
            num_samples = sr // 10
            audio = np.random.randn(num_samples).astype(np.float32)
            result = backend.transcribe(audio, sr)

            assert isinstance(result, SttResult)
            assert result.raw["sample_rate"] == sr
            assert result.raw["audio_samples"] == num_samples

    def test_audio_dtype_conversion(self):
        """Test that audio with different dtypes is handled correctly."""
        backend = MockSttBackend()

        # Test different input dtypes
        audio_float64 = np.random.randn(1600).astype(np.float64)
        audio_int16 = (np.random.randn(1600) * 32767).astype(np.int16)

        # Mock backend should handle these gracefully
        # (in practice, callers should provide float32, but we test robustness)
        result_f64 = backend.transcribe(audio_float64, 16000)
        assert isinstance(result_f64, SttResult)

        # For int16, we'd need to convert it first in real usage
        audio_int16_as_float = audio_int16.astype(np.float32) / 32767.0
        result_int16 = backend.transcribe(audio_int16_as_float, 16000)
        assert isinstance(result_int16, SttResult)


class TestVoskBackendImport:
    """Test Vosk backend import behavior without requiring Vosk installation."""

    def test_vosk_import_failure_handling(self):
        """Test that Vosk backend fails gracefully when vosk is not installed."""
        # Mock vosk import to fail
        with patch.dict('sys.modules', {'vosk': None}):
            with pytest.raises(RuntimeError, match="vosk library not available"):
                create_stt_backend("vosk")

    def test_vosk_backend_construction_with_mock_vosk(self):
        """Test Vosk backend construction behavior with mocked vosk module."""
        # Mock vosk import to fail to test error handling
        with patch.dict('sys.modules', {'vosk': None}):
            with pytest.raises(RuntimeError, match="vosk library not available"):
                create_stt_backend("vosk")

        # Test with invalid path - still fails on library unavailable
        with patch.dict('sys.modules', {'vosk': None}):
            with pytest.raises(RuntimeError, match="vosk library not available"):
                create_stt_backend("vosk", model_dir="/invalid/path/to/model")


class TestSttResultDataclass:
    """Test SttResult dataclass behavior."""

    def test_stt_result_creation(self):
        """Test SttResult dataclass creation and field access."""
        result = SttResult(
            transcript="test transcript",
            confidence=0.95,
            lang="en-US",
            raw={"test": "data"}
        )

        assert result.transcript == "test transcript"
        assert result.confidence == 0.95
        assert result.lang == "en-US"
        assert result.raw == {"test": "data"}

    def test_stt_result_optional_raw(self):
        """Test SttResult with optional raw field."""
        result = SttResult(
            transcript="test",
            confidence=0.8,
            lang="en-US"
        )

        assert result.transcript == "test"
        assert result.confidence == 0.8
        assert result.lang == "en-US"
        assert result.raw is None

    def test_stt_result_equality(self):
        """Test SttResult equality comparison."""
        result1 = SttResult("hello", 0.9, "en-US", {"test": 1})
        result2 = SttResult("hello", 0.9, "en-US", {"test": 1})
        result3 = SttResult("hi", 0.9, "en-US", {"test": 1})

        assert result1 == result2
        assert result1 != result3
