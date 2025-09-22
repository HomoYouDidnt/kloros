"""Unit tests for microphone calibration."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from src.audio.calibration import (
    CalibrationProfile,
    _compute_rms,
    _compute_snr_to_wake_conf,
    _compute_spectral_tilt,
    _rms_to_dbfs,
    default_profile_path,
    load_profile,
    run_calibration,
    save_profile,
)


class MockAudioBackend:
    """Mock audio backend for testing without hardware."""

    def __init__(
        self, silence_dbfs: float = -60.0, speech_dbfs: float = -24.0, sample_rate: int = 16000
    ):
        """Initialize mock backend with specified noise and speech levels.

        Args:
            silence_dbfs: RMS level for silence recording in dBFS
            speech_dbfs: RMS level for speech recording in dBFS
            sample_rate: Sample rate for recordings
        """
        self.silence_dbfs = silence_dbfs
        self.speech_dbfs = speech_dbfs
        self.sample_rate = sample_rate
        self.is_open = False
        np.random.seed(42)  # Deterministic noise

    def open(self, sample_rate: int, channels: int) -> None:
        """Open mock audio stream."""
        self.is_open = True
        self.sample_rate = sample_rate

    def record(self, seconds: float) -> np.ndarray:
        """Generate synthetic audio for the specified duration."""
        if not self.is_open:
            raise RuntimeError("Backend not opened")

        num_samples = int(seconds * self.sample_rate)

        # Determine if this is silence or speech based on call order
        # First call is typically silence, second is speech
        if not hasattr(self, "_call_count"):
            self._call_count = 0
        self._call_count += 1

        if self._call_count == 1:
            # Generate silence (white noise at specified level)
            target_rms = 10 ** (self.silence_dbfs / 20.0)  # Convert dBFS to linear
            noise = np.random.normal(0, target_rms, num_samples).astype(np.float32)
        else:
            # Generate speech (mix of tone and noise)
            target_rms = 10 ** (self.speech_dbfs / 20.0)  # Convert dBFS to linear

            # Generate a mix of tone and noise to simulate speech
            t = np.linspace(0, seconds, num_samples)
            tone = np.float32(0.3) * np.sin(2 * np.pi * 440 * t).astype(np.float32)  # 440 Hz tone
            noise = np.float32(0.7) * np.random.normal(0, 1, num_samples).astype(np.float32)
            mixed = tone + noise

            # Scale to target RMS
            current_rms = np.sqrt(np.mean(mixed**2))
            if current_rms > 0:
                mixed = mixed * np.float32(target_rms / current_rms)

            noise = mixed.astype(np.float32)

        return noise

    def close(self) -> None:
        """Close mock audio stream."""
        self.is_open = False


class TestCalibrationUtils:
    """Test utility functions for calibration."""

    def test_rms_computation(self):
        """Test RMS calculation."""
        # Test with known signal
        signal = np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float32)
        rms = _compute_rms(signal)
        assert abs(rms - 1.0) < 1e-6

        # Test with zero signal
        zeros = np.zeros(100, dtype=np.float32)
        rms = _compute_rms(zeros)
        assert rms == 0.0

        # Test empty array
        empty = np.array([], dtype=np.float32)
        rms = _compute_rms(empty)
        assert rms == 0.0

    def test_rms_to_dbfs_conversion(self):
        """Test RMS to dBFS conversion."""
        # Test full scale (RMS = 1.0 should be 0 dBFS)
        dbfs = _rms_to_dbfs(1.0)
        assert abs(dbfs - 0.0) < 1e-6

        # Test half scale (RMS = 0.5 should be ~-6 dBFS)
        dbfs = _rms_to_dbfs(0.5)
        assert abs(dbfs - (-6.02)) < 0.1

        # Test very small RMS (should clip to -120 dBFS)
        dbfs = _rms_to_dbfs(1e-12)
        assert dbfs == -120.0

    def test_spectral_tilt_computation(self):
        """Test spectral tilt calculation."""
        sample_rate = 16000

        # Test with low-frequency tone (should have high tilt)
        t = np.linspace(0, 1, sample_rate)
        low_freq_tone = np.sin(2 * np.pi * 200 * t).astype(np.float32)
        tilt = _compute_spectral_tilt(low_freq_tone, sample_rate)
        assert tilt > 0.7  # Should be heavily weighted toward low frequencies

        # Test with high-frequency tone (should have low tilt)
        high_freq_tone = np.sin(2 * np.pi * 4000 * t).astype(np.float32)
        tilt = _compute_spectral_tilt(high_freq_tone, sample_rate)
        assert tilt < 0.3  # Should be weighted toward high frequencies

        # Test with short signal (should return 0.5)
        short_signal = np.array([1, 2, 3], dtype=np.float32)
        tilt = _compute_spectral_tilt(short_signal, sample_rate)
        assert tilt == 0.5

    def test_snr_to_wake_conf_mapping(self):
        """Test SNR to wake confidence mapping."""
        # Test low SNR (should give low confidence)
        low_conf = _compute_snr_to_wake_conf(5.0)
        assert low_conf == 0.5

        # Test high SNR (should give high confidence)
        high_conf = _compute_snr_to_wake_conf(35.0)
        assert high_conf == 0.8

        # Test moderate SNR (should interpolate)
        mid_conf = _compute_snr_to_wake_conf(20.0)
        assert abs(mid_conf - 0.65) < 0.1

        # Test monotonicity (higher SNR should give higher confidence)
        conf_10 = _compute_snr_to_wake_conf(10.0)
        conf_20 = _compute_snr_to_wake_conf(20.0)
        conf_30 = _compute_snr_to_wake_conf(30.0)
        assert conf_10 <= conf_20 <= conf_30


class TestCalibrationCore:
    """Test core calibration functionality."""

    def test_noise_floor_estimation(self):
        """Test noise floor measurement with known synthetic data."""
        backend = MockAudioBackend(silence_dbfs=-60.0, speech_dbfs=-24.0)
        profile = run_calibration(backend, sample_rate=16000, silence_secs=2.0, speech_secs=2.0)

        # Check noise floor is approximately correct (within 2 dB tolerance)
        assert abs(profile.noise_floor_dbfs - (-60.0)) < 2.0

    def test_speech_rms_estimation(self):
        """Test speech RMS measurement with known synthetic data."""
        backend = MockAudioBackend(silence_dbfs=-60.0, speech_dbfs=-24.0)
        profile = run_calibration(backend, sample_rate=16000, silence_secs=2.0, speech_secs=2.0)

        # Check speech RMS is approximately correct (within 2 dB tolerance)
        assert abs(profile.speech_rms_dbfs - (-24.0)) < 2.0

    def test_threshold_and_agc_computation(self):
        """Test VAD threshold and AGC gain computation."""
        backend = MockAudioBackend(silence_dbfs=-60.0, speech_dbfs=-24.0)
        profile = run_calibration(
            backend,
            sample_rate=16000,
            silence_secs=2.0,
            speech_secs=2.0,
            target_rms_dbfs=-20.0,
            noise_margin_db=10.0,
            agc_max_gain_db=12.0,
        )

        # Check VAD threshold is noise floor + margin
        expected_vad = profile.noise_floor_dbfs + 10.0
        assert abs(profile.vad_threshold_dbfs - expected_vad) < 0.5

        # Check AGC gain computation
        # Need gain to go from -24 dBFS to -20 dBFS = +4 dB
        assert 3.0 <= profile.agc_gain_db <= 5.0

        # Check AGC gain is within bounds
        assert 0.0 <= profile.agc_gain_db <= 12.0

    def test_recommended_wake_conf_min_monotonic(self):
        """Test that higher SNR leads to higher recommended confidence."""
        # Test with different noise floors (same speech level)
        backend1 = MockAudioBackend(silence_dbfs=-70.0, speech_dbfs=-24.0)  # High SNR
        profile1 = run_calibration(backend1, silence_secs=1.0, speech_secs=1.0)

        backend2 = MockAudioBackend(silence_dbfs=-40.0, speech_dbfs=-24.0)  # Low SNR
        profile2 = run_calibration(backend2, silence_secs=1.0, speech_secs=1.0)

        # Higher SNR should give higher confidence recommendation
        snr1 = profile1.speech_rms_dbfs - profile1.noise_floor_dbfs
        snr2 = profile2.speech_rms_dbfs - profile2.noise_floor_dbfs

        assert snr1 > snr2  # Verify SNR assumption
        assert profile1.recommended_wake_conf_min >= profile2.recommended_wake_conf_min

    def test_environment_variable_defaults(self):
        """Test that environment variables affect calibration parameters."""
        backend = MockAudioBackend()

        # Test with custom environment variables
        with patch.dict(
            os.environ,
            {
                "KLR_TARGET_RMS_DBFS": "-18.0",
                "KLR_NOISE_FLOOR_DBFS_MARGIN": "8.0",
                "KLR_AGC_MAX_GAIN_DB": "6.0",
            },
        ):
            profile = run_calibration(backend, sample_rate=16000, silence_secs=1.0, speech_secs=1.0)

            # AGC computation should use custom target
            # Speech at -24, target at -18, so need +6 dB, but max is 6 dB
            assert profile.agc_gain_db <= 6.0

            # VAD threshold should use custom margin
            expected_vad = profile.noise_floor_dbfs + 8.0
            assert abs(profile.vad_threshold_dbfs - expected_vad) < 0.5


class TestCalibrationPersistence:
    """Test calibration profile saving and loading."""

    def test_profile_persistence_roundtrip(self):
        """Test saving and loading calibration profile."""
        # Create a test profile
        original_profile = CalibrationProfile(
            version=1,
            device={"name": "test_device", "sample_rate": 16000},
            noise_floor_dbfs=-60.5,
            speech_rms_dbfs=-23.7,
            vad_threshold_dbfs=-50.5,
            agc_gain_db=4.2,
            spectral_tilt=0.37,
            recommended_wake_conf_min=0.62,
            created_utc="2025-09-21T13:37:00Z",
        )

        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            temp_path = tmp.name

        try:
            # Save and load
            saved_path = save_profile(original_profile, temp_path)
            assert saved_path == temp_path

            loaded_profile = load_profile(temp_path)
            assert loaded_profile is not None

            # Check all fields match
            assert loaded_profile.version == original_profile.version
            assert loaded_profile.device == original_profile.device
            assert abs(loaded_profile.noise_floor_dbfs - original_profile.noise_floor_dbfs) < 1e-6
            assert abs(loaded_profile.speech_rms_dbfs - original_profile.speech_rms_dbfs) < 1e-6
            assert (
                abs(loaded_profile.vad_threshold_dbfs - original_profile.vad_threshold_dbfs) < 1e-6
            )
            assert abs(loaded_profile.agc_gain_db - original_profile.agc_gain_db) < 1e-6
            assert abs(loaded_profile.spectral_tilt - original_profile.spectral_tilt) < 1e-6
            assert (
                abs(
                    loaded_profile.recommended_wake_conf_min
                    - original_profile.recommended_wake_conf_min
                )
                < 1e-6
            )
            assert loaded_profile.created_utc == original_profile.created_utc

        finally:
            # Clean up
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    def test_load_nonexistent_profile(self):
        """Test loading a profile that doesn't exist."""
        nonexistent_path = "/path/that/does/not/exist/calibration.json"
        profile = load_profile(nonexistent_path)
        assert profile is None

    def test_load_invalid_profile(self):
        """Test loading an invalid profile file."""
        # Create invalid JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp.write("invalid json content")
            temp_path = tmp.name

        try:
            profile = load_profile(temp_path)
            assert profile is None
        finally:
            os.unlink(temp_path)

    def test_load_incomplete_profile(self):
        """Test loading a profile missing required fields."""
        incomplete_data = {
            "version": 1,
            "device": {"name": "test"},
            # Missing other required fields
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(incomplete_data, tmp)
            temp_path = tmp.name

        try:
            profile = load_profile(temp_path)
            assert profile is None
        finally:
            os.unlink(temp_path)

    def test_default_profile_path_windows(self):
        """Test default profile path generation on Windows."""
        with patch("platform.system", return_value="Windows"):
            with patch.dict(os.environ, {"USERPROFILE": "C:\\Users\\TestUser"}):
                path = default_profile_path()
                # On Linux running Windows path simulation, check components differently
                path_obj = Path(path)
                assert "TestUser" in str(path_obj)
                assert ".kloros" in str(path_obj)
                assert "calibration.json" in str(path_obj)

    def test_default_profile_path_unix(self):
        """Test default profile path generation on Unix."""
        with patch("platform.system", return_value="Linux"):
            with patch("pathlib.Path.home", return_value=Path("/home/testuser")):
                path = default_profile_path()
                expected = Path("/home/testuser/.kloros/calibration.json")
                assert Path(path) == expected

    def test_profile_path_override(self):
        """Test profile path environment variable override."""
        custom_path = "/custom/path/calibration.json"
        with patch.dict(os.environ, {"KLR_CALIB_PROFILE_PATH": custom_path}):
            path = default_profile_path()
            assert path == custom_path


class TestVoiceLoopIntegration:
    """Test integration with voice loop."""

    def test_voice_loop_loads_profile_when_present(self):
        """Test that voice loop loads calibration profile when available."""
        # Create a test profile
        test_profile = CalibrationProfile(
            version=1,
            device={"name": "test_device", "sample_rate": 16000},
            noise_floor_dbfs=-58.0,
            speech_rms_dbfs=-22.0,
            vad_threshold_dbfs=-48.0,
            agc_gain_db=3.5,
            spectral_tilt=0.4,
            recommended_wake_conf_min=0.67,
            created_utc="2025-09-21T13:37:00Z",
        )

        # Mock the load_profile function to return our test profile
        with patch("src.kloros_voice.load_profile") as mock_load:
            mock_load.return_value = test_profile

            # Mock other dependencies that might not be available in test
            with (
                patch("sys.modules", {"sounddevice": MagicMock()}),
                patch("src.kloros_voice.vosk"),
                patch("src.kloros_voice.log_event") as mock_log,
            ):
                # Import and create minimal KLoROS instance
                from src.kloros_voice import KLoROS

                # Create instance (this should call _load_calibration_profile)
                kloros = KLoROS()

                # Verify profile values were loaded
                assert kloros.vad_threshold_dbfs == -48.0
                assert kloros.agc_gain_db == 3.5

                # Verify log event was called
                mock_log.assert_any_call(
                    "calibration_profile_loaded",
                    vad_threshold_dbfs=-48.0,
                    agc_gain_db=3.5,
                    noise_floor_dbfs=-58.0,
                    speech_rms_dbfs=-22.0,
                    spectral_tilt=0.4,
                    recommended_wake_conf_min=0.67,
                )

    def test_voice_loop_handles_missing_profile(self):
        """Test that voice loop handles missing calibration profile gracefully."""
        # Mock load_profile to return None (no profile found)
        with patch("src.kloros_voice.load_profile") as mock_load:
            mock_load.return_value = None

            # Mock other dependencies
            with (
                patch("sys.modules", {"sounddevice": MagicMock()}),
                patch("src.kloros_voice.vosk"),
                patch("src.kloros_voice.log_event"),
            ):
                from src.kloros_voice import KLoROS

                # Create instance
                kloros = KLoROS()

                # Verify default values are used
                assert kloros.vad_threshold_dbfs is None
                assert kloros.agc_gain_db == 0.0

    def test_voice_loop_handles_calibration_import_error(self):
        """Test that voice loop handles calibration module import errors gracefully."""
        # Mock the load_profile import to be None (import failed)
        with patch("src.kloros_voice.load_profile", None):
            # Mock other dependencies
            with (
                patch("sys.modules", {"sounddevice": MagicMock()}),
                patch("src.kloros_voice.vosk"),
                patch("src.kloros_voice.log_event"),
            ):
                from src.kloros_voice import KLoROS

                # Create instance (should not crash)
                kloros = KLoROS()

                # Verify default values are used
                assert kloros.vad_threshold_dbfs is None
                assert kloros.agc_gain_db == 0.0
