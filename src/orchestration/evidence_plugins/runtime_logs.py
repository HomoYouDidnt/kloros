#!/usr/bin/env python3
"""
Runtime Logs Evidence Plugin - Gathers evidence from system logs and service status.
"""

import subprocess
import logging
import re
from typing import Dict, Any, List

from .base import EvidencePlugin, Evidence

logger = logging.getLogger(__name__)


class RuntimeLogsPlugin(EvidencePlugin):
    """
    Analyzes runtime state from system logs and service status.

    Evidence types:
    - Service status (systemctl)
    - Recent logs (journalctl)
    - Error patterns
    - Service restart history
    """

    @property
    def name(self) -> str:
        return "runtime_logs"

    def can_gather(self, investigation_type: str, question: str, context: Dict[str, Any]) -> bool:
        runtime_related = {
            "system_state",
            "performance",
            "error_analysis",
            "service_behavior"
        }

        keywords = ["error", "crash", "fail", "restart", "running", "status", "log"]

        return (
            investigation_type in runtime_related or
            any(kw in question.lower() for kw in keywords)
        )

    def gather(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        evidence = []

        service_names = self._extract_service_names(question, context)

        for service_name in service_names:
            status_evidence = self._get_service_status(service_name)
            if status_evidence:
                evidence.append(status_evidence)

            log_evidence = self._get_recent_logs(service_name, lines=50)
            if log_evidence:
                evidence.append(log_evidence)

            error_evidence = self._get_error_patterns(service_name)
            if error_evidence:
                evidence.append(error_evidence)

        return evidence

    def cost_estimate(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        service_count = len(self._extract_service_names(question, context))

        return {
            "time_estimate_seconds": service_count * 0.5,
            "token_cost": 0,
            "complexity": "low" if service_count < 5 else "medium"
        }

    def priority(self, investigation_type: str) -> int:
        if investigation_type in {"system_state", "error_analysis", "service_behavior"}:
            return 85
        return 50

    def _extract_service_names(self, question: str, context: Dict[str, Any]) -> List[str]:
        """
        Extract systemd service names from question and context.
        """
        services = set()

        service_pattern = r'kloros-[\w\-]+'
        found_services = re.findall(service_pattern, question.lower())
        services.update(found_services)

        common_services = [
            "kloros-orchestrator",
            "kloros-voice",
            "kloros-memory",
            "kloros-curiosity"
        ]

        for service in common_services:
            if service.split("-")[1] in question.lower():
                services.add(service)

        if not services:
            services.add("kloros-orchestrator")

        return list(services)

    def _get_service_status(self, service_name: str) -> Evidence:
        """
        Get systemctl status for a service.
        """
        try:
            result = subprocess.run(
                ["systemctl", "status", service_name],
                capture_output=True,
                text=True,
                timeout=5
            )

            status_info = {
                "service": service_name,
                "active": "active (running)" in result.stdout.lower(),
                "enabled": "enabled" in result.stdout.lower(),
                "output": result.stdout[:1000]
            }

            return Evidence(
                source=self.name,
                evidence_type="service_status",
                content=status_info,
                metadata={"service": service_name},
                timestamp="",
                confidence=1.0
            )

        except Exception as e:
            logger.warning(f"[runtime_logs] Failed to get status for {service_name}: {e}")
            return None

    def _get_recent_logs(self, service_name: str, lines: int = 50) -> Evidence:
        """
        Get recent logs from journalctl.
        """
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                return Evidence(
                    source=self.name,
                    evidence_type="recent_logs",
                    content=result.stdout,
                    metadata={
                        "service": service_name,
                        "lines": lines
                    },
                    timestamp="",
                    confidence=0.9
                )

        except Exception as e:
            logger.warning(f"[runtime_logs] Failed to get logs for {service_name}: {e}")

        return None

    def _get_error_patterns(self, service_name: str) -> Evidence:
        """
        Extract error patterns from recent logs.
        """
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", "200", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return None

            error_patterns = []
            error_keywords = ["error", "failed", "exception", "traceback", "critical", "warning"]

            for line in result.stdout.splitlines():
                if any(kw in line.lower() for kw in error_keywords):
                    error_patterns.append(line.strip())

            if error_patterns:
                unique_errors = list(set(error_patterns))[:20]

                return Evidence(
                    source=self.name,
                    evidence_type="error_patterns",
                    content=unique_errors,
                    metadata={
                        "service": service_name,
                        "error_count": len(error_patterns),
                        "unique_count": len(unique_errors)
                    },
                    timestamp="",
                    confidence=0.85
                )

        except Exception as e:
            logger.warning(f"[runtime_logs] Failed to extract errors for {service_name}: {e}")

        return None
