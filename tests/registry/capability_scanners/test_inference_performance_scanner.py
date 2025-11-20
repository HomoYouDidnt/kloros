"""Tests for InferencePerformanceScanner."""

import pytest
import time
from unittest.mock import Mock, patch
from pathlib import Path
from collections import deque

from src.registry.capability_scanners.inference_performance_scanner import (
    InferencePerformanceScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestInferencePerformanceScanner:
    """Test inference performance monitoring."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = InferencePerformanceScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'InferencePerformanceScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.15
        assert 0.0 <= metadata.alignment_baseline <= 1.0
        assert 0.0 < metadata.schedule_weight <= 1.0

    def test_scan_with_no_metrics_returns_empty(self):
        """Test scan returns empty list when no metrics available."""
        scanner = InferencePerformanceScanner()

        with patch.object(scanner, '_load_inference_metrics', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_detects_slow_inference(self):
        """Test scanner detects slow inference patterns."""
        scanner = InferencePerformanceScanner()

        mock_metrics = [
            {'task_type': 'reasoning', 'tokens_per_sec': 5.2, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 5.8, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 5.5, 'timestamp': time.time()},
            {'task_type': 'factual', 'tokens_per_sec': 45.0, 'timestamp': time.time()},
        ]

        with patch.object(scanner, '_load_inference_metrics', return_value=mock_metrics):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert isinstance(gap, CapabilityGap)
            assert gap.type == 'performance_optimization'
            assert 'reasoning' in gap.reason.lower()
            assert 0.0 <= gap.alignment_score <= 1.0

    def test_scan_ignores_noise_below_threshold(self):
        """Test scanner ignores small performance variations."""
        scanner = InferencePerformanceScanner()

        mock_metrics = [
            {'task_type': 'reasoning', 'tokens_per_sec': 25.0, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 24.5, 'timestamp': time.time()},
            {'task_type': 'reasoning', 'tokens_per_sec': 25.5, 'timestamp': time.time()},
        ]

        with patch.object(scanner, '_load_inference_metrics', return_value=mock_metrics):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_handles_missing_metrics_file(self):
        """Test scanner handles missing metrics file gracefully."""
        scanner = InferencePerformanceScanner()

        with patch.object(Path, 'exists', return_value=False):
            gaps = scanner.scan()
            assert gaps == []

    def test_scanner_with_cache_injection(self):
        """Test scanner works with injected observation cache."""
        from kloros.introspection.observation_cache import ObservationCache

        cache = ObservationCache(window_seconds=60)

        now = time.time()
        for i in range(5):
            obs = {
                "ts": now - i,
                "zooid_name": f"zooid_{i}",
                "ok": True,
                "facts": {
                    "task_type": "code_generation",
                    "tokens_per_sec": 5.0,
                    "timestamp": now - i
                }
            }
            cache.append(obs)

        scanner = InferencePerformanceScanner(cache=cache)
        gaps = scanner.scan()

        assert len(gaps) >= 1
        assert gaps[0].category == 'inference_performance'
        assert 'slow_inference' in gaps[0].name
