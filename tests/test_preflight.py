"""Unit tests for preflight checker."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("src.tools.preflight")

from src.tools.preflight import (
    check_audio_backend,
    check_calibration_profile,
    check_env_sanity,
    check_python_version,
    check_stt_backend,
    check_system_smoke,
    check_tts_backend,
    check_writable_directories,
    compute_overall_status,
    run_all_checks,
    write_json_summary,
)


class TestIndividualChecks:
    """Test individual check functions."""

    def test_python_version_pass(self):
        """Test Python version check passes for current version."""
        with patch("src.tools.preflight.sys.version_info", (3, 11, 6)):
            status, name, details, meta = check_python_version()
            assert status == "PASS"
            assert name == "python"
            assert "3.11.6" in details
            assert meta["major"] == 3
            assert meta["minor"] == 11

    def test_python_version_warn(self):
        """Test Python version check warns for old version."""
        with patch("src.tools.preflight.sys.version_info", (3, 9, 0)):
            status, name, details, meta = check_python_version()
            assert status == "WARN"
            assert name == "python"
            assert "3.9.0" in details
            assert "< 3.10" in details

    def test_writable_directories_pass(self, tmp_path):
        """Test writable directories check passes."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()

        with patch("pathlib.Path.home", return_value=fake_home):
            status, name, details, meta = check_writable_directories()
            assert status == "PASS"
            assert name == "directories"
            assert len(meta["created"]) == 3
            assert len(meta["failed"]) == 0

            # Verify directories were actually created
            assert (fake_home / ".kloros").exists()
            assert (fake_home / ".kloros" / "out").exists()
            assert (fake_home / ".kloros" / "in").exists()

    def test_writable_directories_fail(self):
        """Test writable directories check fails with permission error."""
        # Mock mkdir to raise PermissionError
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied")):
            status, name, details, meta = check_writable_directories()
            assert status == "FAIL"
            assert name == "directories"
            assert len(meta["failed"]) > 0

    def test_calibration_missing_warn(self):
        """Test calibration check warns when profile is missing."""
        with patch("src.audio.calibration.default_profile_path", return_value="/nonexistent/path"):
            status, name, details, meta = check_calibration_profile()
            assert status == "WARN"
            assert name == "calibration"
            assert "missing" in details.lower()

    def test_calibration_malformed_fail(self, tmp_path):
        """Test calibration check fails with malformed JSON."""
        calib_file = tmp_path / "calibration.json"
        calib_file.write_text("{ invalid json")

        mock_profile = MagicMock()
        mock_profile.vad_threshold_dbfs = -40.0

        with (
            patch("src.audio.calibration.default_profile_path", return_value=str(calib_file)),
            patch(
                "src.audio.calibration.load_profile",
                side_effect=json.JSONDecodeError("test", "test", 0),
            ),
        ):
            status, name, details, meta = check_calibration_profile()
            assert status == "FAIL"
            assert name == "calibration"
            assert "malformed" in details.lower()

    def test_calibration_valid_pass(self, tmp_path):
        """Test calibration check passes with valid profile."""
        calib_file = tmp_path / "calibration.json"
        calib_data = {
            "vad_threshold_dbfs": -40.0,
            "agc_gain_db": 5.0,
            "noise_floor_dbfs": -60.0,
            "speech_rms_dbfs": -20.0,
        }
        calib_file.write_text(json.dumps(calib_data))

        # Mock profile object with required attributes
        mock_profile = MagicMock()
        mock_profile.vad_threshold_dbfs = -40.0
        mock_profile.agc_gain_db = 5.0
        mock_profile.noise_floor_dbfs = -60.0
        mock_profile.speech_rms_dbfs = -20.0

        with (
            patch("src.audio.calibration.default_profile_path", return_value=str(calib_file)),
            patch("src.audio.calibration.load_profile", return_value=mock_profile),
        ):
            status, name, details, meta = check_calibration_profile()
            assert status == "PASS"
            assert name == "calibration"
            assert meta["vad_threshold"] == -40.0

    def test_calibration_stale_warn(self, tmp_path):
        """Test calibration check warns for stale profile."""
        calib_file = tmp_path / "calibration.json"
        calib_file.write_text("{}")

        # Set file modification time to 200 days ago
        old_time = (datetime.now() - timedelta(days=200)).timestamp()
        os.utime(calib_file, (old_time, old_time))

        mock_profile = MagicMock()
        mock_profile.vad_threshold_dbfs = -40.0
        mock_profile.agc_gain_db = 5.0
        mock_profile.noise_floor_dbfs = -60.0
        mock_profile.speech_rms_dbfs = -20.0

        with (
            patch("src.audio.calibration.default_profile_path", return_value=str(calib_file)),
            patch("src.audio.calibration.load_profile", return_value=mock_profile),
        ):
            status, name, details, meta = check_calibration_profile()
            assert status == "WARN"
            assert name == "calibration"
            assert "stale" in details.lower()
            assert meta["age_days"] > 180

    def test_env_sanity_pass(self):
        """Test env sanity check passes with valid environment."""
        test_env = {
            "KLR_ENABLE_STT": "1",
            "KLR_FUZZY_THRESHOLD": "0.8",
            "KLR_AUDIO_SAMPLE_RATE": "16000",
        }

        with patch.dict(os.environ, test_env, clear=False):
            status, name, details, meta = check_env_sanity()
            assert status == "PASS"
            assert name == "env"
            assert meta["KLR_ENABLE_STT"] == 1
            assert meta["KLR_FUZZY_THRESHOLD"] == 0.8

    def test_env_bad_values_fail(self):
        """Test env sanity check fails with invalid values."""
        test_env = {
            "KLR_AUDIO_SAMPLE_RATE": "-1",  # Invalid: negative
            "KLR_FUZZY_THRESHOLD": "1.5",  # Invalid: > 1.0
        }

        with patch.dict(os.environ, test_env, clear=False):
            status, name, details, meta = check_env_sanity()
            assert status == "FAIL"
            assert name == "env"
            assert len(meta["invalid"]) > 0

    def test_env_unparsable_warn(self):
        """Test env sanity check warns for unparsable values."""
        test_env = {"KLR_FUZZY_THRESHOLD": "not_a_number", "KLR_AUDIO_SAMPLE_RATE": "invalid"}

        with patch.dict(os.environ, test_env, clear=False):
            status, name, details, meta = check_env_sanity()
            assert status == "WARN"
            assert name == "env"
            assert len(meta["coerced"]) > 0

    def test_audio_backend_sounddevice_pass(self):
        """Test audio backend check passes when sounddevice is available."""
        mock_sd = MagicMock()
        mock_sd.default.device = [0, 1]  # [input, output]
        mock_sd.query_devices.return_value = [{"name": "Test Microphone", "max_input_channels": 1}]

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            status, name, details, meta = check_audio_backend()
            assert status == "PASS"
            assert name == "audio"
            assert meta["sounddevice_available"] is True
            assert meta["default_device_index"] == 0

    def test_audio_backend_unavailable_warn(self):
        """Test audio backend check warns when sounddevice unavailable."""
        with patch.dict("sys.modules", {"sounddevice": None}):
            status, name, details, meta = check_audio_backend()
            assert status == "WARN"
            assert name == "audio"
            assert meta["sounddevice_available"] is False

    def test_audio_backend_quick_mode(self):
        """Test audio backend check in quick mode."""
        status, name, details, meta = check_audio_backend(quick=True)
        assert status == "PASS"
        assert name == "audio"
        assert meta["quick"] is True

    def test_stt_backend_mock_pass(self):
        """Test STT backend check passes for mock."""
        with patch.dict(os.environ, {"KLR_STT_BACKEND": "mock"}):
            status, name, details, meta = check_stt_backend()
            assert status == "PASS"
            assert name == "stt"
            assert meta["backend"] == "mock"

    def test_stt_backend_vosk_missing_warn(self):
        """Test STT backend check warns when vosk unavailable."""
        with patch.dict(os.environ, {"KLR_STT_BACKEND": "vosk"}):
            with patch.dict("sys.modules", {"vosk": None}):
                status, name, details, meta = check_stt_backend()
                assert status == "WARN"
                assert name == "stt"
                assert meta["vosk_available"] is False

    def test_stt_backend_vosk_model_missing_warn(self, tmp_path):
        """Test STT backend check warns when vosk model missing."""
        mock_vosk = MagicMock()
        nonexistent_model = tmp_path / "nonexistent_model"

        with patch.dict(
            os.environ, {"KLR_STT_BACKEND": "vosk", "KLR_VOSK_MODEL_DIR": str(nonexistent_model)}
        ):
            with patch.dict("sys.modules", {"vosk": mock_vosk}):
                status, name, details, meta = check_stt_backend()
                assert status == "WARN"
                assert name == "stt"
                assert meta["model_missing"] is True

    def test_tts_backend_mock_pass(self):
        """Test TTS backend check passes for mock."""
        with patch.dict(os.environ, {"KLR_TTS_BACKEND": "mock"}):
            status, name, details, meta = check_tts_backend()
            assert status == "PASS"
            assert name == "tts"
            assert meta["backend"] == "mock"

    def test_tts_backend_piper_missing_warn(self):
        """Test TTS backend check warns when piper unavailable."""
        with patch.dict(os.environ, {"KLR_TTS_BACKEND": "piper"}):
            with patch.dict("sys.modules", {"piper": None}):
                with patch("shutil.which", return_value=None):
                    status, name, details, meta = check_tts_backend()
                    assert status == "WARN"
                    assert name == "tts"
                    assert meta["python_piper_available"] is False

    def test_tts_backend_piper_binary_pass(self):
        """Test TTS backend check passes when piper binary available."""
        with patch.dict(os.environ, {"KLR_TTS_BACKEND": "piper"}):
            with patch.dict("sys.modules", {"piper": None}):
                with patch("shutil.which", return_value="/usr/bin/piper"):
                    status, name, details, meta = check_tts_backend()
                    assert status == "PASS"
                    assert name == "tts"
                    assert meta["piper_binary_path"] == "/usr/bin/piper"

    def test_system_smoke_pass(self):
        """Test system smoke check passes with successful smoke test."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.transcript = "hello"
        mock_result.reply_text = "ok"
        mock_result.timings_ms = {"total_ms": 100}
        mock_result.tts_path = "/tmp/test.wav"

        with patch("src.tools.system_smoke.run_smoke", return_value=mock_result):
            status, name, details, meta = check_system_smoke()
            assert status == "PASS"
            assert name == "smoke"
            assert meta["transcript"] == "hello"
            assert meta["tts_generated"] is True

    def test_system_smoke_no_voice_warn(self):
        """Test system smoke check warns on no voice detection."""
        mock_result = MagicMock()
        mock_result.ok = False
        mock_result.reason = "no_voice"
        mock_result.transcript = ""
        mock_result.reply_text = ""
        mock_result.timings_ms = {}
        mock_result.tts_path = None

        with patch("src.tools.system_smoke.run_smoke", return_value=mock_result):
            status, name, details, meta = check_system_smoke()
            assert status == "WARN"
            assert name == "smoke"
            assert "no voice" in details.lower()

    def test_system_smoke_fail_on_exception(self):
        """Test system smoke check fails on exception."""
        with patch("src.tools.system_smoke.run_smoke", side_effect=Exception("Test error")):
            status, name, details, meta = check_system_smoke()
            assert status == "FAIL"
            assert name == "smoke"
            assert "Test error" in details


class TestOverallChecks:
    """Test overall check logic."""

    def test_overall_pass_with_mocks(self):
        """Test overall PASS with mocks and good environment."""
        test_env = {
            "KLR_STT_BACKEND": "mock",
            "KLR_TTS_BACKEND": "mock",
            "KLR_AUDIO_BACKEND": "mock",
            "KLR_FUZZY_THRESHOLD": "0.8",
        }

        # Mock all checks to return PASS
        mock_checks = [
            ("PASS", "python", "3.11.6", {}),
            ("PASS", "directories", "All OK", {}),
            ("WARN", "calibration", "Missing", {}),  # Missing calibration is OK
            ("PASS", "env", "4 vars OK", {}),
            ("WARN", "audio", "SoundDevice unavailable (will use mock)", {}),  # Mock is OK
            ("PASS", "stt", "Mock backend", {}),
            ("PASS", "tts", "Mock backend", {}),
            ("PASS", "smoke", "Pipeline OK", {}),
        ]

        with patch.dict(os.environ, test_env):
            with (
                patch("src.tools.preflight.check_python_version", return_value=mock_checks[0]),
                patch(
                    "src.tools.preflight.check_writable_directories", return_value=mock_checks[1]
                ),
                patch("src.tools.preflight.check_calibration_profile", return_value=mock_checks[2]),
                patch("src.tools.preflight.check_env_sanity", return_value=mock_checks[3]),
                patch("src.tools.preflight.check_audio_backend", return_value=mock_checks[4]),
                patch("src.tools.preflight.check_stt_backend", return_value=mock_checks[5]),
                patch("src.tools.preflight.check_tts_backend", return_value=mock_checks[6]),
                patch("src.tools.preflight.check_system_smoke", return_value=mock_checks[7]),
            ):
                results = run_all_checks()
                overall = compute_overall_status(results)

                # Should be WARN because of calibration and audio, but not FAIL
                assert overall == "WARN"

    def test_calibration_missing_warn(self):
        """Test overall WARN when calibration is missing."""
        mock_checks = [
            ("PASS", "python", "3.11.6", {}),
            ("WARN", "calibration", "Profile missing", {}),
            ("PASS", "other", "OK", {}),
        ]

        overall = compute_overall_status(mock_checks)
        assert overall == "WARN"

    def test_calibration_malformed_fail(self):
        """Test overall FAIL when calibration is malformed."""
        mock_checks = [
            ("PASS", "python", "3.11.6", {}),
            ("FAIL", "calibration", "Malformed JSON", {}),
            ("PASS", "other", "OK", {}),
        ]

        overall = compute_overall_status(mock_checks)
        assert overall == "FAIL"

    def test_env_bad_values_fail(self):
        """Test overall FAIL with invalid environment values."""
        mock_checks = [
            ("PASS", "python", "3.11.6", {}),
            ("FAIL", "env", "Invalid values", {}),
            ("PASS", "other", "OK", {}),
        ]

        overall = compute_overall_status(mock_checks)
        assert overall == "FAIL"

    def test_backend_soft_warnings(self):
        """Test that backend unavailability gives WARN, not FAIL."""
        mock_checks = [
            ("PASS", "python", "3.11.6", {}),
            ("WARN", "audio", "SoundDevice unavailable", {}),
            ("WARN", "stt", "Vosk unavailable", {}),
            ("WARN", "tts", "Piper unavailable", {}),
            ("PASS", "smoke", "Mock pipeline OK", {}),
        ]

        overall = compute_overall_status(mock_checks)
        assert overall == "WARN"  # Should be WARN, not FAIL

    def test_system_smoke_mock(self):
        """Test system smoke with mocked success and failure."""
        # Test success
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.transcript = "test"
        mock_result.reply_text = "response"
        mock_result.timings_ms = {}
        mock_result.tts_path = "/tmp/test.wav"

        with patch("src.tools.system_smoke.run_smoke", return_value=mock_result):
            status, name, details, meta = check_system_smoke()
            assert status == "PASS"

        # Test failure
        with patch("src.tools.system_smoke.run_smoke", side_effect=Exception("Test failure")):
            status, name, details, meta = check_system_smoke()
            assert status == "FAIL"


class TestJSONSummary:
    """Test JSON summary generation."""

    def test_json_summary_creation(self, tmp_path):
        """Test JSON summary is created correctly."""
        check_results = [
            ("PASS", "python", "3.11.6", {"major": 3, "minor": 11}),
            ("WARN", "calibration", "Missing", {"path": "/test/path"}),
        ]
        overall_status = "WARN"

        json_path = str(tmp_path / "test_preflight.json")
        written_path = write_json_summary(check_results, overall_status, json_path)

        assert written_path == json_path
        assert Path(json_path).exists()

        with open(json_path) as f:
            data = json.load(f)

        assert data["overall"] == "WARN"
        assert len(data["checks"]) == 2
        assert data["checks"][0]["name"] == "python"
        assert data["checks"][0]["status"] == "PASS"
        assert data["checks"][1]["name"] == "calibration"
        assert data["checks"][1]["status"] == "WARN"
        assert "timestamp_utc" in data


class TestCLIIntegration:
    """Test CLI exit codes and behavior."""

    def test_cli_exit_codes(self):
        """Test CLI exit codes for different overall statuses."""
        # This would be tested with subprocess in a real integration test
        # For unit testing, we verify the logic components

        # Test PASS overall -> should exit 0
        pass_results = [("PASS", "test", "OK", {})]
        overall = compute_overall_status(pass_results)
        assert overall == "PASS"

        # Test WARN overall -> should exit 2
        warn_results = [("WARN", "test", "Warning", {})]
        overall = compute_overall_status(warn_results)
        assert overall == "WARN"

        # Test FAIL overall -> should exit 1
        fail_results = [("FAIL", "test", "Failed", {})]
        overall = compute_overall_status(fail_results)
        assert overall == "FAIL"

    def test_skip_smoke_option(self):
        """Test that --no-smoke skips the smoke test."""
        with (
            patch(
                "src.tools.preflight.check_python_version",
                return_value=("PASS", "python", "OK", {}),
            ),
            patch(
                "src.tools.preflight.check_writable_directories",
                return_value=("PASS", "dirs", "OK", {}),
            ),
            patch(
                "src.tools.preflight.check_calibration_profile",
                return_value=("PASS", "calib", "OK", {}),
            ),
            patch("src.tools.preflight.check_env_sanity", return_value=("PASS", "env", "OK", {})),
            patch(
                "src.tools.preflight.check_audio_backend", return_value=("PASS", "audio", "OK", {})
            ),
            patch("src.tools.preflight.check_stt_backend", return_value=("PASS", "stt", "OK", {})),
            patch("src.tools.preflight.check_tts_backend", return_value=("PASS", "tts", "OK", {})),
        ):
            results = run_all_checks(skip_smoke=True)

            # Should have 7 checks (all except smoke)
            assert len(results) == 7
            check_names = [result[1] for result in results]
            assert "smoke" not in check_names

            # With smoke test
            with patch(
                "src.tools.preflight.check_system_smoke", return_value=("PASS", "smoke", "OK", {})
            ):
                results_with_smoke = run_all_checks(skip_smoke=False)
                assert len(results_with_smoke) == 8
                smoke_names = [result[1] for result in results_with_smoke]
                assert "smoke" in smoke_names
