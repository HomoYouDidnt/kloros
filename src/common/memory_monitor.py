"""
Memory monitoring module for ASTRAEA services.

Tracks RSS, heap usage, and triggers alerts when thresholds exceeded.
"""
import gc
import os
import json
import psutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_WARNING_THRESHOLD_MB = 1024
DEFAULT_CRITICAL_THRESHOLD_MB = 2048
METRICS_DIR = Path("/home/kloros/.kloros/metrics")


class MemoryMonitor:
    def __init__(
        self,
        service_name: str,
        warning_threshold_mb: int = DEFAULT_WARNING_THRESHOLD_MB,
        critical_threshold_mb: int = DEFAULT_CRITICAL_THRESHOLD_MB,
        auto_gc_on_warning: bool = True
    ):
        self.service_name = service_name
        self.warning_threshold_mb = warning_threshold_mb
        self.critical_threshold_mb = critical_threshold_mb
        self.auto_gc_on_warning = auto_gc_on_warning
        self.process = psutil.Process(os.getpid())
        self.baseline_rss_mb: Optional[float] = None
        self.last_warning_time: Optional[datetime] = None

        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        self.metrics_file = METRICS_DIR / f"{service_name}_memory.json"

    def get_current_usage(self) -> Dict[str, float]:
        mem_info = self.process.memory_info()
        rss_mb = mem_info.rss / (1024 * 1024)

        return {
            'rss_mb': round(rss_mb, 2),
            'vms_mb': round(mem_info.vms / (1024 * 1024), 2),
            'percent': round(self.process.memory_percent(), 2),
            'timestamp': datetime.now().isoformat()
        }

    def set_baseline(self):
        current = self.get_current_usage()
        self.baseline_rss_mb = current['rss_mb']
        logger.info(f"{self.service_name} memory baseline: {self.baseline_rss_mb}MB")

    def check_and_log(self) -> Dict[str, any]:
        current = self.get_current_usage()
        rss_mb = current['rss_mb']

        status = 'ok'
        action_taken = None

        if rss_mb >= self.critical_threshold_mb:
            status = 'critical'
            logger.error(
                f"{self.service_name} CRITICAL memory: {rss_mb}MB "
                f"(threshold: {self.critical_threshold_mb}MB)"
            )

        elif rss_mb >= self.warning_threshold_mb:
            status = 'warning'
            now = datetime.now()

            if self.last_warning_time is None or (now - self.last_warning_time).seconds > 300:
                logger.warning(
                    f"{self.service_name} high memory: {rss_mb}MB "
                    f"(threshold: {self.warning_threshold_mb}MB)"
                )
                self.last_warning_time = now

                if self.auto_gc_on_warning:
                    before_gc = rss_mb
                    gc.collect()
                    after = self.get_current_usage()
                    after_gc = after['rss_mb']
                    freed = before_gc - after_gc

                    if freed > 10:
                        logger.info(f"{self.service_name} GC freed {freed:.2f}MB")
                        action_taken = f"gc_freed_{freed:.2f}mb"
                        current = after
                        rss_mb = after_gc
                        status = 'ok' if rss_mb < self.warning_threshold_mb else 'warning'

        result = {
            **current,
            'status': status,
            'action_taken': action_taken,
            'baseline_mb': self.baseline_rss_mb,
            'growth_mb': round(rss_mb - self.baseline_rss_mb, 2) if self.baseline_rss_mb else None
        }

        with open(self.metrics_file, 'w') as f:
            json.dump(result, f, indent=2)

        return result

    def should_restart(self) -> bool:
        current = self.get_current_usage()
        return current['rss_mb'] >= self.critical_threshold_mb

    def get_recommendations(self) -> list:
        current = self.get_current_usage()
        rss_mb = current['rss_mb']
        recommendations = []

        if self.baseline_rss_mb and rss_mb > self.baseline_rss_mb * 2:
            recommendations.append(
                f"Memory doubled from baseline ({self.baseline_rss_mb}MB -> {rss_mb}MB). "
                "Possible memory leak."
            )

        if rss_mb > self.warning_threshold_mb:
            recommendations.append(
                f"High memory usage ({rss_mb}MB). Consider investigating object retention."
            )

        if rss_mb > self.critical_threshold_mb:
            recommendations.append(
                f"Critical memory usage ({rss_mb}MB). Service restart recommended."
            )

        return recommendations


def create_monitor(
    service_name: str,
    warning_mb: int = DEFAULT_WARNING_THRESHOLD_MB,
    critical_mb: int = DEFAULT_CRITICAL_THRESHOLD_MB
) -> MemoryMonitor:
    monitor = MemoryMonitor(service_name, warning_mb, critical_mb)
    monitor.set_baseline()
    return monitor
