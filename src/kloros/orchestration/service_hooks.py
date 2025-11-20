"""
Systemd service management hooks for zooid lifecycle.

Provides injectable callbacks for starting/stopping zooid services.
"""
import subprocess
import logging

logger = logging.getLogger(__name__)


def start_service(zooid_name: str) -> bool:
    """
    Start zooid systemd service.

    Args:
        zooid_name: Zooid name (e.g., "LatencyTracker_v1")

    Returns:
        True if service started successfully
    """
    unit = f"klr-zooid-{zooid_name}.service"

    try:
        logger.info(f"Starting systemd service: {unit}")
        result = subprocess.run(
            ["sudo", "systemctl", "start", unit],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info(f"✓ Service {unit} started")
            return True
        else:
            logger.error(f"Failed to start {unit}: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Exception starting {unit}: {e}")
        return False


def stop_service(zooid_name: str) -> bool:
    """
    Stop zooid systemd service.

    Args:
        zooid_name: Zooid name (e.g., "LatencyTracker_v1")

    Returns:
        True if service stopped successfully
    """
    unit = f"klr-zooid-{zooid_name}.service"

    try:
        logger.info(f"Stopping systemd service: {unit}")
        result = subprocess.run(
            ["sudo", "systemctl", "stop", unit],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info(f"✓ Service {unit} stopped")
            return True
        else:
            logger.error(f"Failed to stop {unit}: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Exception stopping {unit}: {e}")
        return False


def mock_start_service(zooid_name: str) -> bool:
    """Mock service start for testing."""
    logger.info(f"[MOCK] Would start systemd service for {zooid_name}")
    return True


def mock_stop_service(zooid_name: str) -> bool:
    """Mock service stop for testing."""
    logger.info(f"[MOCK] Would stop systemd service for {zooid_name}")
    return True
