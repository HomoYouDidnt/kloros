"""
Service Health Monitor for KLoROS Critical Processes

Monitors critical systemd services and can restart them autonomously.
Integrates with existing self-healing framework.
"""

import subprocess
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class ServiceStatus:
    """Status of a monitored service."""
    name: str
    active: bool
    enabled: bool
    failed: bool
    since: Optional[str]
    last_check: datetime


class CriticalService:
    """Definition of a critical service for KLoROS."""

    def __init__(
        self,
        name: str,
        description: str,
        auto_restart: bool = True,
        restart_cooldown_minutes: int = 5,
        max_restarts_per_hour: int = 3,
        dependencies: Optional[List[str]] = None
    ):
        """Initialize critical service definition.

        Args:
            name: Systemd service name (e.g., 'kloros-orchestrator.timer')
            description: Human-readable description
            auto_restart: Whether to automatically restart on failure
            restart_cooldown_minutes: Minimum time between restart attempts
            max_restarts_per_hour: Maximum restart attempts per hour
            dependencies: List of service names this depends on
        """
        self.name = name
        self.description = description
        self.auto_restart = auto_restart
        self.restart_cooldown = timedelta(minutes=restart_cooldown_minutes)
        self.max_restarts_per_hour = max_restarts_per_hour
        self.dependencies = dependencies or []

        # Tracking
        self.restart_history: List[datetime] = []
        self.last_restart_attempt: Optional[datetime] = None
        self.consecutive_failures: int = 0


class ServiceHealthMonitor:
    """
    Monitor and heal critical KLoROS services.

    Monitors systemd services and can autonomously restart them.
    Integrates with KLoROS self-healing framework.
    """

    # Define critical services for KLoROS
    CRITICAL_SERVICES = [
        CriticalService(
            name="kloros-orchestrator.timer",
            description="Orchestrator timer (runs winner deployment & autonomous loop)",
            auto_restart=True,
            restart_cooldown_minutes=5,
            max_restarts_per_hour=2
        ),
        CriticalService(
            name="ollama-live.service",
            description="Ollama Live LLM service (fast chat, required for reasoning & code repair)",
            auto_restart=True,
            restart_cooldown_minutes=10,
            max_restarts_per_hour=1
        ),
        CriticalService(
            name="spica-phase-test.timer",
            description="PHASE testing timer (nightly test runs)",
            auto_restart=True,
            restart_cooldown_minutes=15,
            max_restarts_per_hour=1
        ),
        CriticalService(
            name="kloros.service",
            description="Main KLoROS voice agent (critical for user communication)",
            auto_restart=True,  # Critical for user interaction
            restart_cooldown_minutes=10,
            max_restarts_per_hour=1,
            dependencies=["ollama-live.service"]
        ),
    ]

    def __init__(self, log_file: Optional[Path] = None):
        """Initialize service health monitor.

        Args:
            log_file: Optional path to log file for health check history
        """
        self.services = {svc.name: svc for svc in self.CRITICAL_SERVICES}
        self.log_file = log_file or Path("/home/kloros/.kloros/service_health.jsonl")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def check_service_status(self, service_name: str) -> ServiceStatus:
        """Check status of a systemd service.

        Args:
            service_name: Name of service to check

        Returns:
            ServiceStatus object with current state
        """
        try:
            # Check if service is active
            active_result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            active = active_result.returncode == 0

            # Check if service is enabled
            enabled_result = subprocess.run(
                ["systemctl", "is-enabled", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            enabled = enabled_result.returncode == 0

            # Check if service has failed
            failed_result = subprocess.run(
                ["systemctl", "is-failed", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            failed = failed_result.returncode == 0

            # Get service start time
            since_result = subprocess.run(
                ["systemctl", "show", service_name, "--property=ActiveEnterTimestamp", "--value"],
                capture_output=True,
                text=True,
                timeout=5
            )
            since = since_result.stdout.strip() if since_result.returncode == 0 else None

            return ServiceStatus(
                name=service_name,
                active=active,
                enabled=enabled,
                failed=failed,
                since=since,
                last_check=datetime.now()
            )

        except Exception as e:
            logger.error(f"Failed to check service {service_name}: {e}")
            return ServiceStatus(
                name=service_name,
                active=False,
                enabled=False,
                failed=True,
                since=None,
                last_check=datetime.now()
            )

    def check_all_services(self) -> Dict[str, ServiceStatus]:
        """Check status of all critical services.

        Returns:
            Dict mapping service name to ServiceStatus
        """
        statuses = {}
        for service_name in self.services.keys():
            statuses[service_name] = self.check_service_status(service_name)
        return statuses

    def should_restart_service(self, service: CriticalService) -> bool:
        """Determine if a service should be restarted.

        Args:
            service: CriticalService to check

        Returns:
            True if service should be restarted
        """
        if not service.auto_restart:
            return False

        # Check cooldown period
        if service.last_restart_attempt:
            time_since_last = datetime.now() - service.last_restart_attempt
            if time_since_last < service.restart_cooldown:
                logger.info(f"[service_health] {service.name} in cooldown period")
                return False

        # Check rate limiting (restarts in last hour)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_restarts = [t for t in service.restart_history if t > one_hour_ago]

        if len(recent_restarts) >= service.max_restarts_per_hour:
            logger.warning(
                f"[service_health] {service.name} exceeded max restarts "
                f"({len(recent_restarts)}/{service.max_restarts_per_hour} in last hour)"
            )
            return False

        return True

    def restart_service(self, service_name: str, enable_if_disabled: bool = True) -> bool:
        """Restart a systemd service.

        Args:
            service_name: Name of service to restart
            enable_if_disabled: Whether to enable the service if it's disabled

        Returns:
            True if restart successful
        """
        service = self.services.get(service_name)
        if not service:
            logger.error(f"[service_health] Unknown service: {service_name}")
            return False

        # Check if restart is allowed
        if not self.should_restart_service(service):
            return False

        try:
            # Check current status
            status = self.check_service_status(service_name)

            # Check dependencies first
            for dep in service.dependencies:
                dep_status = self.check_service_status(dep)
                if not dep_status.active:
                    logger.info(f"[service_health] Starting dependency: {dep}")
                    self.restart_service(dep, enable_if_disabled=True)

            # Enable if disabled and requested
            if enable_if_disabled and not status.enabled:
                logger.info(f"[service_health] Enabling {service_name}")
                enable_result = subprocess.run(
                    ["sudo", "systemctl", "enable", service_name],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if enable_result.returncode != 0:
                    logger.error(f"[service_health] Failed to enable {service_name}: {enable_result.stderr}")
                    return False

            # Start or restart the service
            if status.active:
                logger.info(f"[service_health] Restarting {service_name}")
                cmd = ["sudo", "systemctl", "restart", service_name]
            else:
                logger.info(f"[service_health] Starting {service_name}")
                cmd = ["sudo", "systemctl", "start", service_name]

            restart_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if restart_result.returncode != 0:
                logger.error(f"[service_health] Failed to restart {service_name}: {restart_result.stderr}")
                service.consecutive_failures += 1
                return False

            # Record restart
            service.last_restart_attempt = datetime.now()
            service.restart_history.append(datetime.now())
            service.consecutive_failures = 0

            # Verify service started
            new_status = self.check_service_status(service_name)

            if new_status.active:
                logger.info(f"[service_health] ✓ {service_name} successfully restarted")
                self._log_restart(service_name, success=True)
                return True
            else:
                logger.error(f"[service_health] ✗ {service_name} failed to start")
                service.consecutive_failures += 1
                self._log_restart(service_name, success=False, reason="service did not start")
                return False

        except Exception as e:
            logger.error(f"[service_health] Error restarting {service_name}: {e}")
            service.consecutive_failures += 1
            self._log_restart(service_name, success=False, reason=str(e))
            return False

    def heal_unhealthy_services(self) -> Dict[str, bool]:
        """Check all services and restart any that are down.

        Returns:
            Dict mapping service name to restart success (only includes services that needed restart)
        """
        results = {}
        statuses = self.check_all_services()

        for service_name, status in statuses.items():
            service = self.services[service_name]

            # Check if service needs healing
            needs_healing = False
            reason = ""

            if not status.enabled and service.auto_restart:
                needs_healing = True
                reason = "disabled"
            elif not status.active and service.auto_restart:
                needs_healing = True
                reason = "inactive"
            elif status.failed and service.auto_restart:
                needs_healing = True
                reason = "failed"

            if needs_healing:
                logger.warning(
                    f"[service_health] {service.description} is {reason}, "
                    f"attempting restart..."
                )
                success = self.restart_service(service_name, enable_if_disabled=True)
                results[service_name] = success

        return results

    def get_health_report(self) -> Dict[str, Any]:
        """Generate a health report for all critical services.

        Returns:
            Dict with health report data
        """
        statuses = self.check_all_services()

        report = {
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "summary": {
                "total": len(statuses),
                "active": 0,
                "inactive": 0,
                "failed": 0,
                "disabled": 0
            }
        }

        for service_name, status in statuses.items():
            service = self.services[service_name]

            report["services"][service_name] = {
                "description": service.description,
                "active": status.active,
                "enabled": status.enabled,
                "failed": status.failed,
                "since": status.since,
                "auto_restart": service.auto_restart,
                "restart_history_count": len(service.restart_history),
                "consecutive_failures": service.consecutive_failures
            }

            # Update summary
            if status.active:
                report["summary"]["active"] += 1
            else:
                report["summary"]["inactive"] += 1

            if status.failed:
                report["summary"]["failed"] += 1

            if not status.enabled:
                report["summary"]["disabled"] += 1

        return report

    def _log_restart(self, service_name: str, success: bool, reason: str = ""):
        """Log a service restart attempt.

        Args:
            service_name: Name of service
            success: Whether restart succeeded
            reason: Optional reason for failure
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "service": service_name,
            "action": "restart",
            "success": success,
            "reason": reason
        }

        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write restart log: {e}")


def check_and_heal_services() -> Dict[str, Any]:
    """Convenience function to check and heal all critical services.

    Returns:
        Health report after healing
    """
    monitor = ServiceHealthMonitor()

    # Heal any unhealthy services
    healed = monitor.heal_unhealthy_services()

    # Generate report
    report = monitor.get_health_report()
    report["healed_services"] = healed

    return report


# Integration with existing self-healing framework

class RestartServiceAction:
    """Action to restart a systemd service (integrates with existing HealAction)."""

    def __init__(self, name: str, params: Dict[str, Any]):
        """Initialize restart service action.

        Args:
            name: Action name
            params: Must include 'service' key with service name
        """
        self.name = name
        self.params = params
        self._monitor = ServiceHealthMonitor()
        self._rollback_data = None

    def apply(self, kloros_instance) -> bool:
        """Apply the restart action.

        Args:
            kloros_instance: KLoROS instance (not used for service restarts)

        Returns:
            True if successful
        """
        service_name = self.params.get("service")
        if not service_name:
            logger.error("[action] No service specified for restart")
            return False

        # Record original state for rollback (though we can't truly rollback a restart)
        status = self._monitor.check_service_status(service_name)
        self._rollback_data = {
            "was_active": status.active,
            "was_enabled": status.enabled
        }

        # Restart the service
        return self._monitor.restart_service(service_name, enable_if_disabled=True)

    def rollback(self, kloros_instance) -> bool:
        """Rollback restart (best effort - stop if it wasn't running).

        Args:
            kloros_instance: KLoROS instance

        Returns:
            True if rollback successful
        """
        if not self._rollback_data:
            return False

        service_name = self.params.get("service")

        # If service wasn't active before, stop it
        if not self._rollback_data.get("was_active"):
            try:
                subprocess.run(
                    ["sudo", "systemctl", "stop", service_name],
                    capture_output=True,
                    timeout=30
                )
                logger.info(f"[action] Rolled back restart of {service_name} (stopped)")
                return True
            except Exception as e:
                logger.error(f"[action] Rollback failed: {e}")
                return False

        # Can't truly rollback a restart if it was already running
        logger.info(f"[action] Cannot rollback restart of {service_name} (was already running)")
        return True


if __name__ == "__main__":
    # Test the service health monitor
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    monitor = ServiceHealthMonitor()

    if len(sys.argv) > 1 and sys.argv[1] == "--heal":
        # Heal mode
        print("=== Healing Unhealthy Services ===\n")
        results = monitor.heal_unhealthy_services()

        if results:
            print("\nServices healed:")
            for service, success in results.items():
                status = "✓ SUCCESS" if success else "✗ FAILED"
                print(f"  {service}: {status}")
        else:
            print("All services healthy, no healing needed")

    else:
        # Report mode
        print("=== KLoROS Service Health Report ===\n")
        report = monitor.get_health_report()

        print(f"Timestamp: {report['timestamp']}\n")
        print("Summary:")
        print(f"  Total services: {report['summary']['total']}")
        print(f"  Active: {report['summary']['active']}")
        print(f"  Inactive: {report['summary']['inactive']}")
        print(f"  Failed: {report['summary']['failed']}")
        print(f"  Disabled: {report['summary']['disabled']}")
        print()

        for service_name, info in report['services'].items():
            status_icon = "✓" if info['active'] else "✗"
            enabled_text = "enabled" if info['enabled'] else "disabled"

            print(f"{status_icon} {service_name} ({enabled_text})")
            print(f"   {info['description']}")

            if info['active'] and info['since']:
                print(f"   Running since: {info['since']}")
            elif info['failed']:
                print(f"   Status: FAILED")
            else:
                print(f"   Status: Inactive")

            if info['restart_history_count'] > 0:
                print(f"   Restart history: {info['restart_history_count']} attempts")

            if info['consecutive_failures'] > 0:
                print(f"   ⚠ Consecutive failures: {info['consecutive_failures']}")

            print()
