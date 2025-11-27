"""Tests for systemd_helpers module.

Tests the systemd service state checking utilities used to prevent
generating investigation questions for intentionally disabled services.
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess
from src.orchestration.registry.systemd_helpers import (
    is_service_intentionally_disabled,
    get_service_state
)


class TestIsServiceIntentionallyDisabled:
    """Tests for is_service_intentionally_disabled() function."""

    def test_disabled_service_returns_true(self):
        """Test that disabled service returns True."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="disabled\n",
                returncode=1
            )

            result = is_service_intentionally_disabled("nginx.service")

            assert result is True
            mock_run.assert_called_once_with(
                ["systemctl", "is-enabled", "nginx.service"],
                capture_output=True,
                text=True,
                timeout=5
            )

    def test_masked_service_returns_true(self):
        """Test that masked service returns True."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="masked\n",
                returncode=1
            )

            result = is_service_intentionally_disabled("rabbitmq-server.service")

            assert result is True

    def test_enabled_service_returns_false(self):
        """Test that enabled service returns False."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="enabled\n",
                returncode=0
            )

            result = is_service_intentionally_disabled("ssh.service")

            assert result is False

    def test_static_service_returns_false(self):
        """Test that static service returns False."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="static\n",
                returncode=0
            )

            result = is_service_intentionally_disabled("systemd-journald.service")

            assert result is False

    def test_generated_service_returns_false(self):
        """Test that generated service returns False."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="generated\n",
                returncode=0
            )

            result = is_service_intentionally_disabled("some-generated.service")

            assert result is False

    def test_service_not_found_returns_false(self):
        """Test that non-existent service returns False (conservative)."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="",
                returncode=1
            )

            result = is_service_intentionally_disabled("nonexistent.service")

            assert result is False

    def test_timeout_returns_false(self):
        """Test that timeout returns False (conservative)."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["systemctl", "is-enabled", "hung.service"],
                timeout=5
            )

            result = is_service_intentionally_disabled("hung.service")

            assert result is False

    def test_systemctl_not_found_returns_false(self):
        """Test that missing systemctl returns False."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = is_service_intentionally_disabled("any.service")

            assert result is False

    def test_permission_denied_returns_false(self):
        """Test that permission error returns False (conservative)."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = PermissionError()

            result = is_service_intentionally_disabled("restricted.service")

            assert result is False

    def test_empty_service_name_returns_false(self):
        """Test that empty service name returns False."""
        result = is_service_intentionally_disabled("")
        assert result is False

    def test_none_service_name_returns_false(self):
        """Test that None service name returns False."""
        result = is_service_intentionally_disabled(None)
        assert result is False

    def test_service_name_without_suffix(self):
        """Test that service names work with or without .service suffix."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="disabled\n",
                returncode=1
            )

            result = is_service_intentionally_disabled("nginx")

            assert result is True
            mock_run.assert_called_once_with(
                ["systemctl", "is-enabled", "nginx"],
                capture_output=True,
                text=True,
                timeout=5
            )

    def test_whitespace_in_output_handled(self):
        """Test that whitespace in systemctl output is handled correctly."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="  disabled  \n",
                returncode=1
            )

            result = is_service_intentionally_disabled("test.service")

            assert result is True

    def test_unexpected_exception_returns_false(self):
        """Test that unexpected exceptions return False (fail safe)."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = RuntimeError("Unexpected error")

            result = is_service_intentionally_disabled("error.service")

            assert result is False


class TestGetServiceState:
    """Tests for get_service_state() function."""

    def test_active_service(self):
        """Test getting state of active service."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="active\n",
                returncode=0
            )

            result = get_service_state("nginx.service")

            assert result == "active"
            mock_run.assert_called_once_with(
                ["systemctl", "is-active", "nginx.service"],
                capture_output=True,
                text=True,
                timeout=5
            )

    def test_inactive_service(self):
        """Test getting state of inactive service."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="inactive\n",
                returncode=3
            )

            result = get_service_state("stopped.service")

            assert result == "inactive"

    def test_failed_service(self):
        """Test getting state of failed service."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="failed\n",
                returncode=3
            )

            result = get_service_state("crashed.service")

            assert result == "failed"

    def test_activating_service(self):
        """Test getting state of service that is activating."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="activating\n",
                returncode=0
            )

            result = get_service_state("starting.service")

            assert result == "activating"

    def test_timeout_returns_none(self):
        """Test that timeout returns None."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["systemctl", "is-active", "hung.service"],
                timeout=5
            )

            result = get_service_state("hung.service")

            assert result is None

    def test_systemctl_not_found_returns_none(self):
        """Test that missing systemctl returns None."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = get_service_state("any.service")

            assert result is None

    def test_empty_service_name_returns_none(self):
        """Test that empty service name returns None."""
        result = get_service_state("")
        assert result is None

    def test_none_service_name_returns_none(self):
        """Test that None service name returns None."""
        result = get_service_state(None)
        assert result is None

    def test_unexpected_exception_returns_none(self):
        """Test that unexpected exceptions return None."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = RuntimeError("Unexpected error")

            result = get_service_state("error.service")

            assert result is None

    def test_whitespace_in_output_handled(self):
        """Test that whitespace in systemctl output is handled correctly."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="  active  \n",
                returncode=0
            )

            result = get_service_state("test.service")

            assert result == "active"


class TestIntegration:
    """Integration tests using actual systemctl (if available)."""

    @pytest.mark.integration
    def test_real_systemctl_check(self):
        """Test with real systemctl command if available."""
        try:
            result = subprocess.run(
                ["systemctl", "--version"],
                capture_output=True,
                timeout=2
            )
            if result.returncode != 0:
                pytest.skip("systemctl not available")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("systemctl not available")

        result = is_service_intentionally_disabled("nonexistent-test-service-12345.service")

        assert isinstance(result, bool)

    @pytest.mark.integration
    def test_real_get_service_state(self):
        """Test get_service_state with real systemctl command if available."""
        try:
            result = subprocess.run(
                ["systemctl", "--version"],
                capture_output=True,
                timeout=2
            )
            if result.returncode != 0:
                pytest.skip("systemctl not available")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("systemctl not available")

        state = get_service_state("nonexistent-test-service-12345.service")

        assert state is None or isinstance(state, str)
