#!/usr/bin/env python3
"""
System Metrics Evidence Plugin - Gathers evidence from system resource usage.
"""

import subprocess
import logging
import re
from typing import Dict, Any, List

from .base import EvidencePlugin, Evidence

logger = logging.getLogger(__name__)


class SystemMetricsPlugin(EvidencePlugin):
    """
    Analyzes system resource usage and performance metrics.

    Evidence types:
    - Memory usage (total, used, available)
    - CPU usage
    - GPU usage (nvidia-ml)
    - Disk usage
    - Process resource consumption
    """

    @property
    def name(self) -> str:
        return "system_metrics"

    def can_gather(self, investigation_type: str, question: str, context: Dict[str, Any]) -> bool:
        performance_related = {
            "performance",
            "resource_usage",
            "system_state"
        }

        keywords = ["memory", "cpu", "gpu", "disk", "resource", "performance", "slow", "hang"]

        return (
            investigation_type in performance_related or
            any(kw in question.lower() for kw in keywords)
        )

    def gather(self, question: str, context: Dict[str, Any]) -> List[Evidence]:
        evidence = []

        if any(kw in question.lower() for kw in ["memory", "ram", "resource"]):
            mem_evidence = self._get_memory_usage()
            if mem_evidence:
                evidence.append(mem_evidence)

        if any(kw in question.lower() for kw in ["cpu", "processor", "performance"]):
            cpu_evidence = self._get_cpu_usage()
            if cpu_evidence:
                evidence.append(cpu_evidence)

        if any(kw in question.lower() for kw in ["gpu", "cuda", "nvidia"]):
            gpu_evidence = self._get_gpu_usage()
            if gpu_evidence:
                evidence.append(gpu_evidence)

        if any(kw in question.lower() for kw in ["disk", "storage", "space"]):
            disk_evidence = self._get_disk_usage()
            if disk_evidence:
                evidence.append(disk_evidence)

        return evidence

    def cost_estimate(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "time_estimate_seconds": 1.0,
            "token_cost": 0,
            "complexity": "low"
        }

    def priority(self, investigation_type: str) -> int:
        if investigation_type == "performance":
            return 80
        return 40

    def _get_memory_usage(self) -> Evidence:
        """
        Get system memory usage.
        """
        try:
            result = subprocess.run(
                ["free", "-h"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    mem_line = lines[1].split()

                    return Evidence(
                        source=self.name,
                        evidence_type="memory_usage",
                        content={
                            "total": mem_line[1] if len(mem_line) > 1 else "unknown",
                            "used": mem_line[2] if len(mem_line) > 2 else "unknown",
                            "free": mem_line[3] if len(mem_line) > 3 else "unknown",
                            "available": mem_line[6] if len(mem_line) > 6 else "unknown",
                            "raw_output": result.stdout
                        },
                        metadata={},
                        timestamp="",
                        confidence=1.0
                    )

        except Exception as e:
            logger.warning(f"[system_metrics] Failed to get memory usage: {e}")

        return None

    def _get_cpu_usage(self) -> Evidence:
        """
        Get CPU usage using top.
        """
        try:
            result = subprocess.run(
                ["top", "-bn1"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                cpu_line = [l for l in result.stdout.splitlines() if "Cpu(s)" in l]
                if cpu_line:
                    return Evidence(
                        source=self.name,
                        evidence_type="cpu_usage",
                        content={
                            "cpu_line": cpu_line[0].strip(),
                            "raw_output": result.stdout[:500]
                        },
                        metadata={},
                        timestamp="",
                        confidence=0.9
                    )

        except Exception as e:
            logger.warning(f"[system_metrics] Failed to get CPU usage: {e}")

        return None

    def _get_gpu_usage(self) -> Evidence:
        """
        Get GPU usage using nvidia-ml.
        """
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu", "--format=csv"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().splitlines()

                gpu_info = []
                for line in lines[1:]:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 5:
                        gpu_info.append({
                            "index": parts[0],
                            "name": parts[1],
                            "memory_used": parts[2],
                            "memory_total": parts[3],
                            "utilization": parts[4]
                        })

                return Evidence(
                    source=self.name,
                    evidence_type="gpu_usage",
                    content=gpu_info,
                    metadata={"gpu_count": len(gpu_info)},
                    timestamp="",
                    confidence=1.0
                )

        except FileNotFoundError:
            logger.debug("[system_metrics] nvidia-smi not found (no GPU or drivers not installed)")
        except Exception as e:
            logger.warning(f"[system_metrics] Failed to get GPU usage: {e}")

        return None

    def _get_disk_usage(self) -> Evidence:
        """
        Get disk usage.
        """
        try:
            result = subprocess.run(
                ["df", "-h", "/home"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    disk_line = lines[1].split()

                    return Evidence(
                        source=self.name,
                        evidence_type="disk_usage",
                        content={
                            "filesystem": disk_line[0] if len(disk_line) > 0 else "unknown",
                            "size": disk_line[1] if len(disk_line) > 1 else "unknown",
                            "used": disk_line[2] if len(disk_line) > 2 else "unknown",
                            "available": disk_line[3] if len(disk_line) > 3 else "unknown",
                            "use_percent": disk_line[4] if len(disk_line) > 4 else "unknown",
                            "mount": disk_line[5] if len(disk_line) > 5 else "unknown"
                        },
                        metadata={},
                        timestamp="",
                        confidence=1.0
                    )

        except Exception as e:
            logger.warning(f"[system_metrics] Failed to get disk usage: {e}")

        return None
