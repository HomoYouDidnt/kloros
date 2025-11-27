"""Tests for BottleneckDetectorScanner."""

import pytest
import time
from unittest.mock import patch

from src.orchestration.registry.capability_scanners.bottleneck_detector_scanner import (
    BottleneckDetectorScanner
)
from src.orchestration.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestBottleneckDetectorScanner:
    """Test bottleneck detection scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = BottleneckDetectorScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'BottleneckDetectorScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.20

    def test_scan_detects_queue_buildup(self):
        """Test scanner detects growing queue depths."""
        scanner = BottleneckDetectorScanner()

        mock_metrics = [
            {'queue': 'umn', 'depth': 50, 'timestamp': time.time() - 600},
            {'queue': 'umn', 'depth': 120, 'timestamp': time.time() - 300},
            {'queue': 'umn', 'depth': 280, 'timestamp': time.time() - 60},
            {'queue': 'umn', 'depth': 350, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_queue_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'bottleneck'
            assert 'queue' in gap.reason.lower()

    def test_scan_detects_slow_operations(self):
        """Test scanner detects consistently slow operations."""
        scanner = BottleneckDetectorScanner()

        mock_metrics = [
            {'operation': 'json_parsing', 'duration_ms': 450, 'timestamp': time.time()},
            {'operation': 'json_parsing', 'duration_ms': 520, 'timestamp': time.time()},
            {'operation': 'json_parsing', 'duration_ms': 480, 'timestamp': time.time()},
            {'operation': 'json_parsing', 'duration_ms': 510, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_operation_timings', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('slow' in gap.reason.lower() for gap in gaps)

    def test_scan_ignores_transient_spikes(self):
        """Test scanner ignores one-off spikes (not sustained)."""
        scanner = BottleneckDetectorScanner()

        mock_metrics = [
            {'queue': 'umn', 'depth': 20, 'timestamp': time.time() - 600},
            {'queue': 'umn', 'depth': 180, 'timestamp': time.time() - 300},
            {'queue': 'umn', 'depth': 25, 'timestamp': time.time() - 60},
            {'queue': 'umn', 'depth': 22, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_queue_metrics', return_value=mock_metrics):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_with_no_metrics_returns_empty(self):
        """Test scan returns empty when no metrics available."""
        scanner = BottleneckDetectorScanner()

        with patch.object(scanner, '_load_queue_metrics', return_value=[]):
            with patch.object(scanner, '_load_operation_timings', return_value=[]):
                gaps = scanner.scan()
                assert gaps == []


def test_scanner_with_cache_injection():
    """Test scanner works with injected observation cache."""
    from src.observability.introspection.observation_cache import ObservationCache
    import time

    cache = ObservationCache(window_seconds=60)

    now = time.time()
    for i in range(10):
        obs = {
            "ts": now - i,
            "zooid_name": f"zooid_{i}",
            "ok": True,
            "facts": {
                "queue_name": "intent_queue",
                "depth": 150,
                "timestamp": now - i
            }
        }
        cache.append(obs)

    scanner = BottleneckDetectorScanner(cache=cache)
    gaps = scanner.scan()

    assert len(gaps) >= 1
    assert gaps[0].category == 'queue_bottleneck'
