"""Unit tests for system smoke harness."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("src.tools.system_smoke")

from src.tools.system_smoke import SmokeResult, run_smoke, synth_sample


class TestSyntheticAudio:
    """Test synthetic audio generation."""

    def test_synth_sample_structure(self):
        """Test that synthetic sample has correct structure and duration."""
        sample_rate = 16000
        audio = synth_sample(sample_rate)

        # Should be 1.8 seconds total (0.5 + 0.8 + 0.5)
        expected_samples = int(1.8 * sample_rate)
        assert len(audio) == expected_samples

        # Should be float32 in range [-1, 1]
        assert audio.dtype == np.float32
        assert np.all(audio >= -1.0)
        assert np.all(audio <= 1.0)

    def test_synth_sample_tone_detection(self):
        """Test that the 440Hz tone is present in the middle segment."""
        sample_rate = 16000
        audio = synth_sample(sample_rate)

        # Extract the middle tone segment (0.5s to 1.3s)
        start_idx = int(0.5 * sample_rate)
        end_idx = int(1.3 * sample_rate)
        tone_segment = audio[start_idx:end_idx]

        # The tone should have significantly higher energy than noise
        tone_energy = np.mean(tone_segment**2)

        # Extract noise segments for comparison
        noise1 = audio[: int(0.5 * sample_rate)]
        noise2 = audio[int(1.3 * sample_rate) :]
        noise_energy = (np.mean(noise1**2) + np.mean(noise2**2)) / 2

        # Tone should be much louder than noise (-20 dBFS vs -60 dBFS)
        assert tone_energy > noise_energy * 100  # At least 20dB difference

    def test_synth_sample_deterministic(self):
        """Test that synthetic sample generation is deterministic."""
        # Set random seed for reproducibility
        np.random.seed(42)
        audio1 = synth_sample(16000)

        np.random.seed(42)
        audio2 = synth_sample(16000)

        # Should be identical when using same seed
        np.testing.assert_array_equal(audio1, audio2)


class TestSmokeRunner:
    """Test smoke test runner functionality."""

    def test_smoke_with_mocks_ok(self):
        """Test successful smoke test with mock backends."""
        # Mock the output directory creation
        with (
            patch("src.tools.system_smoke._get_output_dir") as mock_get_dir,
            patch("src.tools.system_smoke.load_profile") as mock_load_profile,
            patch("shutil.copy2"),
        ):
            # Setup mocks
            mock_get_dir.return_value = "/tmp/test_out"
            mock_load_profile.return_value = {"vad_threshold_dbfs": -40.0}

            # Run smoke test
            result = run_smoke(stt_backend="mock", tts_backend="mock", reason_backend="mock")

            # Should succeed
            assert isinstance(result, SmokeResult)
            assert result.ok is True
            assert result.reason == "ok"
            assert result.transcript  # Mock STT should return some text
            assert result.reply_text  # Mock reasoning should return some text
            assert "total_ms" in result.timings_ms

    def test_smoke_no_voice_returns_false(self):
        """Test that all-noise input returns no_voice failure."""
        # Generate all-noise input (very quiet)
        sample_rate = 16000
        duration = 1.0
        noise_amplitude = 10 ** (-70 / 20)  # Very quiet noise at -70 dBFS
        all_noise = np.random.normal(0, noise_amplitude, int(duration * sample_rate)).astype(
            np.float32
        )

        with (
            patch("src.tools.system_smoke.synth_sample", return_value=all_noise),
            patch("src.tools.system_smoke._get_output_dir") as mock_get_dir,
            patch("src.tools.system_smoke.load_profile") as mock_load_profile,
        ):
            # Setup mocks
            mock_get_dir.return_value = "/tmp/test_out"
            mock_load_profile.return_value = {"vad_threshold_dbfs": -40.0}

            # Run smoke test
            result = run_smoke(stt_backend="mock", tts_backend="mock", reason_backend="mock")

            # Should fail with no_voice
            assert result.ok is False
            assert result.reason == "no_voice"
            assert result.tts_path is None

    def test_smoke_adapter_init_failure(self):
        """Test handling of adapter initialization failures."""
        with patch("src.tools.system_smoke.create_stt_backend") as mock_create_stt:
            # Make STT backend creation fail
            mock_create_stt.side_effect = RuntimeError("STT backend unavailable")

            result = run_smoke(stt_backend="nonexistent", tts_backend="mock", reason_backend="mock")

            # Should fail with adapter_init_failure
            assert result.ok is False
            assert "adapter_init_failure" in result.reason
            assert result.tts_path is None

    def test_smoke_wav_input_loading(self):
        """Test loading audio from WAV file input."""
        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_path = tmp_wav.name

        try:
            # Create a simple WAV file with wave module
            import wave

            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)  # mono
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(16000)

                # Write some test audio data
                test_audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000)) * 16383).astype(
                    np.int16
                )
                wf.writeframes(test_audio.tobytes())

            with (
                patch("src.tools.system_smoke._get_output_dir") as mock_get_dir,
                patch("src.tools.system_smoke.load_profile") as mock_load_profile,
                patch("shutil.copy2"),
            ):
                # Setup mocks
                mock_get_dir.return_value = "/tmp/test_out"
                mock_load_profile.return_value = {"vad_threshold_dbfs": -30.0}

                # Run smoke test with WAV input
                result = run_smoke(
                    wav_in=tmp_path, stt_backend="mock", tts_backend="mock", reason_backend="mock"
                )

                # Should succeed
                assert result.ok is True
                assert result.reason == "ok"

        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

    def test_smoke_respects_env_vad_threshold(self):
        """Test that VAD threshold respects environment variable when no calibration."""
        with (
            patch("src.tools.system_smoke.load_profile", side_effect=Exception("No calibration")),
            patch.dict(os.environ, {"KLR_VAD_THRESHOLD_DBFS": "-35.0"}),
            patch("src.tools.system_smoke._get_output_dir") as mock_get_dir,
            patch("shutil.copy2"),
        ):
            mock_get_dir.return_value = "/tmp/test_out"

            # This should run without error and use the env var threshold
            result = run_smoke(stt_backend="mock", tts_backend="mock", reason_backend="mock")

            # Should succeed (mock backends are very permissive)
            assert result.ok is True

    def test_smoke_creates_output_directory(self):
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_out_dir = Path(tmp_dir) / "test_kloros_out"

            with (
                patch("src.tools.system_smoke._get_output_dir", return_value=str(test_out_dir)),
                patch("src.tools.system_smoke.load_profile") as mock_load_profile,
                patch("shutil.copy2"),
            ):
                mock_load_profile.return_value = {"vad_threshold_dbfs": -40.0}

                # Directory shouldn't exist initially
                assert not test_out_dir.exists()

                # Run smoke test
                result = run_smoke(stt_backend="mock", tts_backend="mock", reason_backend="mock")

                # Directory should be created during run_smoke
                assert test_out_dir.exists()
                assert result.ok is True
