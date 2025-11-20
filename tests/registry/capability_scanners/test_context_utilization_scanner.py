"""Tests for ContextUtilizationScanner."""

import pytest
import time
from unittest.mock import Mock, patch
from pathlib import Path

from src.registry.capability_scanners.context_utilization_scanner import (
    ContextUtilizationScanner
)
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


class TestContextUtilizationScanner:
    """Test context utilization monitoring."""

    def test_scanner_metadata(self):
        """Test scanner returns correct metadata."""
        scanner = ContextUtilizationScanner()
        metadata = scanner.get_metadata()

        assert isinstance(metadata, ScannerMetadata)
        assert metadata.name == 'ContextUtilizationScanner'
        assert metadata.domain == 'introspection'
        assert metadata.scan_cost == 0.25
        assert metadata.alignment_baseline == 0.7

    def test_scan_with_no_context_logs_returns_empty(self):
        """Test scan returns empty when no context logs exist."""
        scanner = ContextUtilizationScanner()

        with patch.object(scanner, '_load_context_logs', return_value=[]):
            gaps = scanner.scan()
            assert gaps == []

    def test_scan_detects_unused_context_tail(self):
        """Test scanner detects when last portion of context is never referenced."""
        scanner = ContextUtilizationScanner()

        mock_logs = [
            {
                'context_length': 1000,
                'references': [100, 200, 300, 400, 500, 600, 650],
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [50, 150, 250, 350, 450, 550, 680],
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [80, 180, 280, 380, 480, 580, 630],
                'timestamp': time.time()
            }
        ]

        with patch.object(scanner, '_load_context_logs', return_value=mock_logs):
            gaps = scanner.scan()

            assert len(gaps) > 0
            gap = gaps[0]
            assert gap.type == 'context_optimization'
            assert 'unused' in gap.reason.lower()

    def test_scan_detects_recency_bias(self):
        """Test scanner detects when only recent context is used."""
        scanner = ContextUtilizationScanner()

        mock_logs = [
            {
                'context_length': 1000,
                'references': [850, 900, 920, 950, 980],
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [820, 880, 910, 940, 990],
                'timestamp': time.time()
            },
            {
                'context_length': 1000,
                'references': [810, 870, 930, 960, 985],
                'timestamp': time.time()
            }
        ]

        with patch.object(scanner, '_load_context_logs', return_value=mock_logs):
            gaps = scanner.scan()

            assert len(gaps) > 0
            assert any('recency bias' in gap.reason.lower() for gap in gaps)

    def test_scan_handles_empty_references(self):
        """Test scanner handles logs with no references gracefully."""
        scanner = ContextUtilizationScanner()

        mock_logs = [
            {'context_length': 1000, 'references': [], 'timestamp': time.time()}
        ]

        with patch.object(scanner, '_load_context_logs', return_value=mock_logs):
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
                    "context_length": 10000,
                    "references": list(range(0, 5000, 100)),
                    "timestamp": now - i
                }
            }
            cache.append(obs)

        scanner = ContextUtilizationScanner(cache=cache)
        gaps = scanner.scan()

        assert len(gaps) >= 1
        assert gaps[0].category == 'context_utilization'
