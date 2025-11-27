"""Tests for ComparativeAnalyzerScanner."""

import pytest
import time
from unittest.mock import patch

from src.orchestration.registry.capability_scanners.comparative_analyzer_scanner import (
    ComparativeAnalyzerScanner
)
from src.orchestration.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestComparativeAnalyzerScanner:
    """Test comparative strategy analysis scanner."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = ComparativeAnalyzerScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'ComparativeAnalyzerScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.15

    def test_scan_detects_superior_brainmod_strategy(self):
        """Test scanner handles brainmod comparison (currently disabled)."""
        scanner = ComparativeAnalyzerScanner()

        mock_fitness = [
            {'zooid_name': 'reasoning', 'ok': True, 'ts': time.time(), 'ttr_ms': 100},
            {'zooid_name': 'reasoning', 'ok': True, 'ts': time.time(), 'ttr_ms': 110},
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_requires_sufficient_samples(self):
        """Test scanner handles insufficient data (comparison disabled)."""
        scanner = ComparativeAnalyzerScanner()

        mock_fitness = [
            {'zooid_name': 'reasoning', 'ok': True, 'ts': time.time(), 'ttr_ms': 100},
            {'zooid_name': 'reasoning', 'ok': True, 'ts': time.time(), 'ttr_ms': 110},
            {'zooid_name': 'reasoning', 'ok': False, 'ts': time.time(), 'ttr_ms': 120}
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_detects_variant_outperformance(self):
        """Test scanner handles variant comparison (currently disabled)."""
        scanner = ComparativeAnalyzerScanner()

        mock_fitness = [
            {'zooid_name': 'tool_caller', 'ok': True, 'ttr_ms': 120, 'ts': time.time()},
            {'zooid_name': 'tool_caller', 'ok': True, 'ttr_ms': 130, 'ts': time.time()},
            {'zooid_name': 'tool_caller', 'ok': True, 'ttr_ms': 125, 'ts': time.time()},
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_with_no_data_returns_empty(self):
        """Test scan returns empty when no fitness data available."""
        scanner = ComparativeAnalyzerScanner()

        with patch.object(scanner, '_load_fitness_data', return_value=[]):
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
            "ok": i % 2 == 0,
            "ttr_ms": 100.0,
            "incident_id": f"inc-{i}",
            "niche": "test"
        }
        cache.append(obs)

    scanner = ComparativeAnalyzerScanner(cache=cache)
    gaps = scanner.scan()

    assert len(gaps) == 0
