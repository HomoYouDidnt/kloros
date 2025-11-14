"""Tests for ComparativeAnalyzerScanner."""

import pytest
import time
from unittest.mock import patch

from src.registry.capability_scanners.comparative_analyzer_scanner import (
    ComparativeAnalyzerScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


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
        """Test scanner detects when one brainmod consistently outperforms."""
        scanner = ComparativeAnalyzerScanner()

        mock_fitness = [
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': True, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'strategy_optimization'
            assert 'tot' in gap.reason.lower()

    def test_scan_requires_sufficient_samples(self):
        """Test scanner ignores comparisons with insufficient data."""
        scanner = ComparativeAnalyzerScanner()

        mock_fitness = [
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'tot', 'success': True, 'timestamp': time.time()},
            {'zooid': 'reasoning', 'brainmod': 'standard', 'success': False, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_detects_variant_outperformance(self):
        """Test scanner detects when zooid variant outperforms baseline."""
        scanner = ComparativeAnalyzerScanner()

        mock_fitness = [
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 120, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 130, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 125, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 128, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 122, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 135, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 118, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 132, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 127, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'batched', 'ttr_ms': 124, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 220, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 240, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 235, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 228, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 232, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 245, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 218, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 242, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 237, 'timestamp': time.time()},
            {'zooid': 'tool_caller', 'variant': 'standard', 'ttr_ms': 224, 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_fitness_data', return_value=mock_fitness):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('batched' in gap.reason.lower() for gap in gaps)

    def test_scan_with_no_data_returns_empty(self):
        """Test scan returns empty when no fitness data available."""
        scanner = ComparativeAnalyzerScanner()

        with patch.object(scanner, '_load_fitness_data', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []
