"""Tests for ResourceProfilerScanner."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.orchestration.registry.capability_scanners.resource_profiler_scanner import (
    ResourceProfilerScanner
)
from src.orchestration.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestResourceProfilerScanner:
    """Test resource profiling scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = ResourceProfilerScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'ResourceProfilerScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.25

    def test_scan_detects_low_gpu_utilization(self):
        """Test scanner detects underutilized GPU."""
        scanner = ResourceProfilerScanner()

        mock_metrics = [
            {'gpu_util': 35.0, 'gpu_memory_util': 60.0, 'operation': 'tool_calling'},
            {'gpu_util': 42.0, 'gpu_memory_util': 65.0, 'operation': 'tool_calling'},
            {'gpu_util': 38.0, 'gpu_memory_util': 62.0, 'operation': 'tool_calling'}
        ]

        with patch.object(scanner, '_load_resource_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'resource_optimization'
            assert 'gpu' in gap.reason.lower()

    def test_scan_handles_no_gpu(self):
        """Test scanner handles systems without GPU gracefully."""
        scanner = ResourceProfilerScanner()

        mock_metrics = [
            {'cpu_util': 65.0, 'memory_util': 70.0, 'operation': 'reasoning'},
            {'cpu_util': 68.0, 'memory_util': 72.0, 'operation': 'reasoning'}
        ]

        with patch.object(scanner, '_load_resource_metrics', return_value=mock_metrics):
            gaps = scanner.scan()
            assert isinstance(gaps, list)

    def test_scan_detects_cpu_bottleneck(self):
        """Test scanner detects CPU bottlenecks."""
        scanner = ResourceProfilerScanner()

        mock_metrics = [
            {'cpu_util': 95.0, 'memory_util': 50.0, 'operation': 'preprocessing'},
            {'cpu_util': 97.0, 'memory_util': 52.0, 'operation': 'preprocessing'},
            {'cpu_util': 96.0, 'memory_util': 51.0, 'operation': 'preprocessing'}
        ]

        with patch.object(scanner, '_load_resource_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('cpu' in gap.reason.lower() for gap in gaps)

    def test_scan_with_empty_metrics_returns_empty(self):
        """Test scan returns empty when no metrics available."""
        scanner = ResourceProfilerScanner()

        with patch.object(scanner, '_load_resource_metrics', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []


def test_scanner_with_cache_injection():
    """Test scanner works with injected observation cache."""
    from src.observability.introspection.observation_cache import ObservationCache
    import time

    cache = ObservationCache(window_seconds=60)

    now = time.time()
    for i in range(5):
        obs = {
            "ts": now - i,
            "zooid_name": f"zooid_{i}",
            "ok": True,
            "facts": {
                "gpu_utilization": 30.0,
                "gpu_memory_used_mb": 1000,
                "gpu_memory_total_mb": 8000,
                "timestamp": now - i
            }
        }
        cache.append(obs)

    scanner = ResourceProfilerScanner(cache=cache)
    gaps = scanner.scan()

    assert len(gaps) >= 1
    assert gaps[0].category == 'resource_utilization'
