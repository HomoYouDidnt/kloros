"""
System Resource Monitor - RAM, CPU, GPU, disk usage tracking.

Monitors system resource usage and detects anomalies.
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any

import psutil

from .base_types import (
    CuriosityQuestion,
    QuestionStatus,
    ActionClass,
    SystemResourceSnapshot,
)

logger = logging.getLogger(__name__)


class SystemResourceMonitor:
    """
    Monitors system resource usage and detects anomalies.

    Purpose:
        Detect resource exhaustion, memory leaks, stuck processes before
        they impact D-REAM experiments or system stability

    Outcomes:
        - Monitors RAM, swap, CPU, GPU, disk usage
        - Detects sudden spikes or sustained high usage
        - Generates resource-based curiosity questions
    """

    def __init__(
        self,
        memory_threshold: float = 0.85,
        swap_threshold: float = 0.50,
        cpu_threshold: float = 0.90,
        disk_threshold: float = 0.90,
        gpu_threshold: float = 0.95,
        consciousness: Optional[Any] = None
    ):
        """Initialize system resource monitor."""
        self.memory_threshold = memory_threshold
        self.swap_threshold = swap_threshold
        self.cpu_threshold = cpu_threshold
        self.disk_threshold = disk_threshold
        self.gpu_threshold = gpu_threshold
        self.consciousness = consciousness

    def capture_snapshot(self) -> SystemResourceSnapshot:
        """Capture current system resource usage."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        cpu_percent = psutil.cpu_percent(interval=0.1)
        load_avg = psutil.getloadavg()

        disk = psutil.disk_usage("/home/kloros")

        gpu_util = None
        gpu_mem = None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory",
                 "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                gpu_util = float(parts[0])
                gpu_mem = float(parts[1])
        except Exception:
            pass

        return SystemResourceSnapshot(
            timestamp=datetime.now(),
            memory_percent=mem.percent / 100.0,
            memory_used_gb=mem.used / (1024**3),
            memory_total_gb=mem.total / (1024**3),
            swap_percent=swap.percent / 100.0,
            swap_used_gb=swap.used / (1024**3),
            cpu_percent=cpu_percent / 100.0,
            load_avg_1min=load_avg[0],
            load_avg_5min=load_avg[1],
            disk_usage_percent=disk.percent / 100.0,
            gpu_utilization=gpu_util / 100.0 if gpu_util is not None else None,
            gpu_memory_percent=gpu_mem / 100.0 if gpu_mem is not None else None
        )

    def detect_resource_issues(self, snapshot: SystemResourceSnapshot) -> List[str]:
        """Detect resource issues from snapshot."""
        issues = []

        if snapshot.memory_percent > self.memory_threshold:
            issues.append(f"memory_high:{snapshot.memory_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="memory",
                        level=snapshot.memory_percent,
                        evidence=[f"Memory usage: {snapshot.memory_used_gb:.1f}GB/{snapshot.memory_total_gb:.1f}GB ({snapshot.memory_percent*100:.1f}%)"]
                    )
                except Exception:
                    pass

        if snapshot.swap_percent > self.swap_threshold:
            issues.append(f"swap_high:{snapshot.swap_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="memory",
                        level=min(1.0, snapshot.swap_percent * 2),
                        evidence=[f"Swap usage: {snapshot.swap_used_gb:.1f}GB ({snapshot.swap_percent*100:.1f}%) - indicates memory pressure"]
                    )
                except Exception:
                    pass

        if snapshot.cpu_percent > self.cpu_threshold:
            issues.append(f"cpu_saturated:{snapshot.cpu_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="cpu",
                        level=snapshot.cpu_percent,
                        evidence=[f"CPU usage: {snapshot.cpu_percent*100:.1f}%", f"Load average: {snapshot.load_avg_1min:.1f}"]
                    )
                except Exception:
                    pass

        cpu_count = psutil.cpu_count()
        if snapshot.load_avg_5min > cpu_count * 1.5:
            issues.append(f"load_avg_high:{snapshot.load_avg_5min:.1f}")

        if snapshot.disk_usage_percent > self.disk_threshold:
            issues.append(f"disk_low:{snapshot.disk_usage_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="context",
                        level=snapshot.disk_usage_percent,
                        evidence=[f"Disk usage: {snapshot.disk_usage_percent*100:.1f}%"]
                    )
                except Exception:
                    pass

        if snapshot.gpu_utilization and snapshot.gpu_utilization > self.gpu_threshold:
            issues.append(f"gpu_saturated:{snapshot.gpu_utilization*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="cpu",
                        level=snapshot.gpu_utilization,
                        evidence=[f"GPU utilization: {snapshot.gpu_utilization*100:.1f}%"]
                    )
                except Exception:
                    pass

        if snapshot.gpu_memory_percent and snapshot.gpu_memory_percent > self.gpu_threshold:
            issues.append(f"gpu_memory_high:{snapshot.gpu_memory_percent*100:.1f}%")
            if self.consciousness:
                try:
                    self.consciousness.process_resource_pressure(
                        pressure_type="memory",
                        level=snapshot.gpu_memory_percent,
                        evidence=[f"GPU memory: {snapshot.gpu_memory_percent*100:.1f}%"]
                    )
                except Exception:
                    pass

        return issues

    def generate_resource_questions(self) -> List[CuriosityQuestion]:
        """Generate curiosity questions from current resource state."""
        questions = []

        snapshot = self.capture_snapshot()
        issues = self.detect_resource_issues(snapshot)

        for issue in issues:
            issue_type, amount = issue.split(":", 1)
            q = self._question_for_resource_issue(issue_type, amount, snapshot)
            if q:
                questions.append(q)

        return questions

    def _question_for_resource_issue(
        self,
        issue_type: str,
        amount: str,
        snapshot: SystemResourceSnapshot
    ) -> Optional[CuriosityQuestion]:
        """Generate question for detected resource issue."""
        if issue_type == "memory_high":
            hypothesis = "SYSTEM_MEMORY_PRESSURE"
            question = (
                f"Why is memory usage at {amount}? "
                f"Used: {snapshot.memory_used_gb:.1f}GB/{snapshot.memory_total_gb:.1f}GB. "
                f"Should I enable aggressive garbage collection or restart memory-intensive services?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.8
            cost = 0.3

        elif issue_type == "swap_high":
            hypothesis = "SYSTEM_SWAP_PRESSURE"
            question = (
                f"Why is swap usage at {amount}? "
                f"Used: {snapshot.swap_used_gb:.1f}GB. "
                f"Is there a memory leak in a long-running process?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.9
            cost = 0.4

        elif issue_type == "cpu_saturated":
            hypothesis = "SYSTEM_CPU_SATURATION"
            question = (
                f"Why is CPU usage at {amount}? "
                f"Load avg: {snapshot.load_avg_1min:.1f}. "
                f"Are D-REAM experiments running with proper CPU affinity?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.7
            cost = 0.3

        elif issue_type == "load_avg_high":
            hypothesis = "SYSTEM_LOAD_EXCESSIVE"
            question = (
                f"Why is load average {amount} (CPU cores: {psutil.cpu_count()})? "
                f"Are there too many concurrent experiments?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.7
            cost = 0.3

        elif issue_type == "disk_low":
            hypothesis = "SYSTEM_DISK_PRESSURE"
            question = (
                f"Why is disk usage at {amount}? "
                f"Should I clean up old D-REAM artifacts or PHASE test outputs?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.6
            cost = 0.2

        elif issue_type == "gpu_saturated":
            hypothesis = "GPU_SATURATION"
            question = (
                f"Why is GPU utilization at {amount}? "
                f"Is a model training stuck or is OLLAMA overloaded?"
            )
            action_class = ActionClass.INVESTIGATE
            value = 0.7
            cost = 0.3

        elif issue_type == "gpu_memory_high":
            hypothesis = "GPU_MEMORY_PRESSURE"
            question = (
                f"Why is GPU memory at {amount}? "
                f"Should I restart OLLAMA services to free GPU memory?"
            )
            action_class = ActionClass.PROPOSE_FIX
            value = 0.7
            cost = 0.3

        else:
            return None

        evidence = [
            f"issue:{issue_type}",
            f"severity:{amount}",
            f"memory:{snapshot.memory_percent*100:.1f}%",
            f"cpu:{snapshot.cpu_percent*100:.1f}%",
            f"load_avg:{snapshot.load_avg_1min:.1f}",
            f"swap:{snapshot.swap_percent*100:.1f}%"
        ]

        if snapshot.gpu_utilization:
            evidence.append(f"gpu:{snapshot.gpu_utilization*100:.1f}%")

        return CuriosityQuestion(
            id=f"resource.{issue_type}",
            hypothesis=hypothesis,
            question=question,
            evidence=evidence,
            action_class=action_class,
            autonomy=3,
            value_estimate=value,
            cost=cost,
            status=QuestionStatus.READY,
            capability_key=f"system.{issue_type}"
        )
