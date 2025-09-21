"""Unit tests for TTS (Text-to-Speech) functionality."""

import os
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from src.tts.base import create_tts_backend, TtsResult
from src.tts.mock_backend import MockTtsBackend


class TestTtsFactory:
    """Test TTS backend factory functionality."""

    def test_factory_mock(self):
        """Test that factory creates mock backend correctly."""
        backend = create_tts_backend("mock")

        # Verify it has the synthesize method
        assert hasattr(backend, "synthesize")
        assert callable(backend.synthesize)

        # Test basic synthesis
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = backend.synthesize(
                "hello world",
                sample_rate=22050,
                out_dir=tmp_dir,
                basename="test"
            )

            # Verify result structure
            assert isinstance(result, TtsResult)
            assert hasattr(result, "audio_path")
            assert hasattr(result, "duration_s")
            assert hasattr(result, "sample_rate")
            assert hasattr(result, "voice")

            # Verify audio file was created
            assert os.path.exists(result.audio_path)
            assert result.audio_path.endswith(".wav")

    def test_factory_unknown_backend(self):
        """Test that unknown backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown TTS backend: unknown"):
            create_tts_backend("unknown")

    def test_factory_piper_unavailable_graceful(self):
        """Test that Piper backend fails gracefully when unavailable."""
        # Test when Piper module and CLI are both unavailable
        with patch.dict('sys.modules', {'piper': None}):
            with patch('subprocess.run', side_effect=FileNotFoundError("piper not found")):
                with pytest.raises(RuntimeError, match="piper unavailable"):
                    create_tts_backend("piper")


class TestMockBackend:
    """Test mock TTS backend behavior."""

    def test_mock_writes_wav(self):
        """Test that mock backend writes a valid WAV file."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = backend.synthesize(
                "test text",
                sample_rate=22050,
                out_dir=tmp_dir,
                basename="test_output"
            )

            # File should exist
            assert os.path.exists(result.audio_path)
            assert result.audio_path.endswith("test_output.wav")

            # Should be a valid WAV file
            with wave.open(result.audio_path, 'rb') as wav_file:
                assert wav_file.getnchannels() == 1  # mono
                assert wav_file.getsampwidth() == 2  # 16-bit
                assert wav_file.getframerate() == 22050

                # Check duration is approximately 0.1 seconds (±0.02)
                frames = wav_file.getnframes()
                duration = frames / wav_file.getframerate()
                assert 0.08 <= duration <= 0.12

            # Result should match expectations
            assert abs(result.duration_s - 0.1) <= 0.02
            assert result.sample_rate == 22050

    def test_sample_rate_plumbed(self):
        """Test that sample rate parameter is handled correctly."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = backend.synthesize(
                "test",
                sample_rate=24000,
                out_dir=tmp_dir,
                basename="sample_rate_test"
            )

            # Result should reflect requested sample rate
            assert result.sample_rate == 24000

            # WAV file should have correct sample rate
            with wave.open(result.audio_path, 'rb') as wav_file:
                assert wav_file.getframerate() == 24000

    def test_voice_passthrough(self):
        """Test that voice parameter is passed through correctly."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Test with voice specified
            result = backend.synthesize(
                "test",
                voice="test-voice",
                out_dir=tmp_dir,
                basename="voice_test"
            )

            assert result.voice == "test-voice"

            # Test with no voice specified
            result_no_voice = backend.synthesize(
                "test",
                out_dir=tmp_dir,
                basename="no_voice_test"
            )

            assert result_no_voice.voice is None

    def test_custom_output_directory(self):
        """Test that custom output directory is used."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            backend = MockTtsBackend(out_dir=tmp_dir)

            result = backend.synthesize("test", basename="custom_dir_test")

            # File should be in the specified directory
            assert result.audio_path.startswith(tmp_dir)
            assert os.path.exists(result.audio_path)

    def test_basename_generation(self):
        """Test automatic basename generation when not specified."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result1 = backend.synthesize("test1", out_dir=tmp_dir)
            # Small delay to ensure different timestamps
            import time
            time.sleep(0.001)
            result2 = backend.synthesize("test2", out_dir=tmp_dir)

            # Should generate different basenames
            basename1 = Path(result1.audio_path).stem
            basename2 = Path(result2.audio_path).stem

            assert basename1 != basename2
            assert basename1.startswith("mock_tts_")
            assert basename2.startswith("mock_tts_")

    def test_text_ignored(self):
        """Test that mock backend ignores actual text content."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Different texts should produce identical audio
            result1 = backend.synthesize("hello", out_dir=tmp_dir, basename="text1")
            result2 = backend.synthesize("completely different text", out_dir=tmp_dir, basename="text2")

            # Duration and sample rate should be identical
            assert result1.duration_s == result2.duration_s
            assert result1.sample_rate == result2.sample_rate

            # Both files should have same size (same content)
            size1 = os.path.getsize(result1.audio_path)
            size2 = os.path.getsize(result2.audio_path)
            assert size1 == size2


class TestTtsIntegration:
    """Test TTS integration scenarios."""

    def test_directory_creation(self):
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as base_tmp:
            nonexistent_dir = os.path.join(base_tmp, "nonexistent", "nested")

            backend = MockTtsBackend(out_dir=nonexistent_dir)
            result = backend.synthesize("test", basename="dir_creation_test")

            # Directory should have been created
            assert os.path.exists(nonexistent_dir)
            assert os.path.exists(result.audio_path)

    def test_override_parameters(self):
        """Test that synthesize parameters can override backend defaults."""
        with tempfile.TemporaryDirectory() as tmp_dir1:
            with tempfile.TemporaryDirectory() as tmp_dir2:
                # Backend configured with tmp_dir1
                backend = MockTtsBackend(out_dir=tmp_dir1)

                # Synthesize with override to tmp_dir2
                result = backend.synthesize(
                    "test",
                    out_dir=tmp_dir2,
                    basename="override_test"
                )

                # File should be in override directory, not backend default
                assert result.audio_path.startswith(tmp_dir2)
                assert not result.audio_path.startswith(tmp_dir1)
                assert os.path.exists(result.audio_path)

    def test_multiple_synthesis_same_backend(self):
        """Test multiple synthesis calls on the same backend instance."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            results = []
            for i in range(3):
                result = backend.synthesize(
                    f"test message {i}",
                    out_dir=tmp_dir,
                    basename=f"multi_test_{i}"
                )
                results.append(result)

            # All files should exist and be valid
            for i, result in enumerate(results):
                assert os.path.exists(result.audio_path)
                assert f"multi_test_{i}.wav" in result.audio_path

                # Each should be a valid WAV
                with wave.open(result.audio_path, 'rb') as wav_file:
                    assert wav_file.getnchannels() == 1
                    assert wav_file.getsampwidth() == 2

    def test_edge_case_empty_text(self):
        """Test behavior with empty text input."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = backend.synthesize("", out_dir=tmp_dir, basename="empty_text")

            # Should still create a valid WAV file
            assert os.path.exists(result.audio_path)
            assert result.duration_s == 0.1  # Mock always creates 0.1s silence

            with wave.open(result.audio_path, 'rb') as wav_file:
                assert wav_file.getnframes() > 0

    def test_special_characters_in_text(self):
        """Test behavior with special characters in text."""
        backend = MockTtsBackend()

        with tempfile.TemporaryDirectory() as tmp_dir:
            special_text = "Hello! 你好 🌟 @#$%^&*()_+"
            result = backend.synthesize(special_text, out_dir=tmp_dir, basename="special_chars")

            # Should handle gracefully (mock ignores text anyway)
            assert os.path.exists(result.audio_path)
            assert result.duration_s == 0.1