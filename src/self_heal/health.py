"""Health probes for validation."""

from typing import Dict, Any, Optional
import psutil


class HealthProbes:
    """Health check probes for validating fixes."""

    def __init__(self, kloros_instance=None):
        """Initialize health probes.

        Args:
            kloros_instance: Reference to main KLoROS instance
        """
        self.kloros = kloros_instance
        self._metrics: Dict[str, Any] = {}

    def check_validator_health(self) -> Dict[str, Any]:
        """Check validator health and rejection rate.

        Returns:
            Dict with health status and metrics
        """
        try:
            # Check if validator is accepting more tools
            if self.kloros and hasattr(self.kloros, 'tool_synthesizer'):
                validator = getattr(
                    self.kloros.tool_synthesizer,
                    'validator',
                    None
                )
                if validator:
                    # Get recent rejection stats if available
                    rejection_rate = getattr(validator, '_recent_rejection_rate', 0.0)
                    return {
                        "healthy": rejection_rate < 0.5,
                        "rejection_rate": rejection_rate
                    }
        except Exception as e:
            print(f"[health] Validator check failed: {e}")

        return {"healthy": True, "rejection_rate": 0.0}

    def check_rag_health(self) -> Dict[str, Any]:
        """Check RAG backend health and timeout rate.

        Returns:
            Dict with health status and metrics
        """
        try:
            if self.kloros and hasattr(self.kloros, 'reason_backend'):
                # Check if synthesis is working
                timeout_count = self._metrics.get("rag_timeout_count", 0)
                success_count = self._metrics.get("rag_success_count", 0)
                total = timeout_count + success_count

                if total > 0:
                    timeout_rate = timeout_count / total
                    return {
                        "healthy": timeout_rate < 0.3,
                        "timeout_rate": timeout_rate
                    }
        except Exception as e:
            print(f"[health] RAG check failed: {e}")

        return {"healthy": True, "timeout_rate": 0.0}

    def check_audio_health(self) -> Dict[str, Any]:
        """Check audio system health and echo rate.

        Returns:
            Dict with health status and metrics
        """
        try:
            if self.kloros and hasattr(self.kloros, 'audio_backend'):
                # Check if audio muting is working
                echo_count = self._metrics.get("beep_echo_count", 0)
                return {
                    "healthy": echo_count < 5,
                    "echo_count": echo_count
                }
        except Exception as e:
            print(f"[health] Audio check failed: {e}")

        return {"healthy": True, "echo_count": 0}

    def record_metric(self, metric_name: str, value: Any):
        """Record a metric for tracking.

        Args:
            metric_name: Name of the metric
            value: Metric value
        """
        self._metrics[metric_name] = value

    def increment_metric(self, metric_name: str, amount: int = 1):
        """Increment a counter metric.

        Args:
            metric_name: Name of the metric
            amount: Amount to increment by
        """
        self._metrics[metric_name] = self._metrics.get(metric_name, 0) + amount

    def check_system_health(self) -> Dict[str, Any]:
        """Check system resource health.

        Returns:
            Dict with health status and metrics
        """
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            swap_critical = swap.percent >= 90
            swap_warning = swap.percent >= 70
            mem_critical = mem.available < 1_000_000_000

            stuck_processes = 0
            for proc in psutil.process_iter(['status']):
                try:
                    if proc.info['status'] == psutil.STATUS_DISK_SLEEP:
                        stuck_processes += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            healthy = not (swap_critical or mem_critical or stuck_processes > 5)

            return {
                "healthy": healthy,
                "swap_percent": swap.percent,
                "memory_available_gb": mem.available / (1024**3),
                "stuck_processes": stuck_processes,
                "swap_critical": swap_critical,
                "swap_warning": swap_warning,
                "memory_critical": mem_critical
            }
        except Exception as e:
            print(f"[health] System health check failed: {e}")
            return {"healthy": False, "error": str(e)}
