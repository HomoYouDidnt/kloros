"""Systemd service state helpers for capability discovery.

This module provides utility functions for checking systemd service states
to prevent generating investigation questions for intentionally disabled services.
"""

import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def is_service_intentionally_disabled(service_name: str) -> bool:
    """Check if a systemd service is intentionally disabled.

    This function runs `systemctl is-enabled <service>` to determine if a service
    is in a disabled or masked state, indicating it was intentionally turned off
    by the system administrator.

    Args:
        service_name: Name of the systemd service to check (with or without .service suffix)

    Returns:
        bool: True if service is disabled or masked, False otherwise

    Edge cases handled:
    - Service not found: Returns False (treat as potentially available)
    - Systemctl timeout: Returns False (assume service may be active)
    - Permission errors: Returns False (conservative approach)
    - Invalid service name: Returns False

    Examples:
        >>> is_service_intentionally_disabled("nginx.service")
        True  # If nginx is explicitly disabled

        >>> is_service_intentionally_disabled("ssh")
        False  # If ssh is enabled or running
    """
    if not service_name:
        logger.warning("Empty service name provided to is_service_intentionally_disabled")
        return False

    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", service_name],
            capture_output=True,
            text=True,
            timeout=5
        )

        status = result.stdout.strip()
        exit_code = result.returncode

        logger.debug(f"Service {service_name} is-enabled status: {status} (exit: {exit_code})")

        # Consider disabled, masked, or not-found (exit 4) as intentionally disabled
        return status in ["disabled", "masked", "not-found"] or exit_code == 4

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout checking if {service_name} is disabled (assuming not disabled)")
        return False

    except FileNotFoundError:
        logger.error("systemctl command not found (not a systemd system?)")
        return False

    except PermissionError:
        logger.warning(f"Permission denied checking {service_name} status (assuming not disabled)")
        return False

    except Exception as e:
        logger.error(f"Unexpected error checking if {service_name} is disabled: {e}")
        return False


def get_service_state(service_name: str) -> Optional[str]:
    """Get the current state of a systemd service.

    This function runs `systemctl is-active <service>` to get the service state.

    Args:
        service_name: Name of the systemd service to check

    Returns:
        str: Service state (e.g., "active", "inactive", "failed"), or None on error

    Examples:
        >>> get_service_state("nginx.service")
        'active'

        >>> get_service_state("stopped-service")
        'inactive'
    """
    if not service_name:
        logger.warning("Empty service name provided to get_service_state")
        return None

    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=5
        )

        state = result.stdout.strip()
        logger.debug(f"Service {service_name} is-active status: {state}")
        return state

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout checking {service_name} state")
        return None

    except FileNotFoundError:
        logger.error("systemctl command not found (not a systemd system?)")
        return None

    except Exception as e:
        logger.error(f"Unexpected error checking {service_name} state: {e}")
        return None
