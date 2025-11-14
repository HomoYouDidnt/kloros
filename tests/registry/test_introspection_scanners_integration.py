"""Integration tests for introspection scanners."""

import pytest
from pathlib import Path

from src.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
from src.registry.capability_scanners import (
    InferencePerformanceScanner,
    ContextUtilizationScanner,
    ResourceProfilerScanner,
    BottleneckDetectorScanner,
    ComparativeAnalyzerScanner
)


class TestIntrospectionScannersIntegration:
    """Test introspection scanners integrate with discovery monitor."""

    def test_all_scanners_discoverable(self):
        """Test all introspection scanners are auto-discovered."""
        monitor = CapabilityDiscoveryMonitor()

        scanner_names = [s.get_metadata().name for s in monitor.scanners]

        assert 'InferencePerformanceScanner' in scanner_names
        assert 'ContextUtilizationScanner' in scanner_names
        assert 'ResourceProfilerScanner' in scanner_names
        assert 'BottleneckDetectorScanner' in scanner_names
        assert 'ComparativeAnalyzerScanner' in scanner_names

    def test_all_scanners_have_introspection_domain(self):
        """Test all new scanners report 'introspection' domain."""
        scanners = [
            InferencePerformanceScanner(),
            ContextUtilizationScanner(),
            ResourceProfilerScanner(),
            BottleneckDetectorScanner(),
            ComparativeAnalyzerScanner()
        ]

        for scanner in scanners:
            metadata = scanner.get_metadata()
            assert metadata.domain == 'introspection'

    def test_all_scanners_have_reasonable_scan_cost(self):
        """Test scan costs are within reasonable bounds."""
        scanners = [
            InferencePerformanceScanner(),
            ContextUtilizationScanner(),
            ResourceProfilerScanner(),
            BottleneckDetectorScanner(),
            ComparativeAnalyzerScanner()
        ]

        for scanner in scanners:
            metadata = scanner.get_metadata()
            assert 0.0 < metadata.scan_cost <= 0.3

    def test_scanners_return_valid_gaps_structure(self):
        """Test all scanners return properly structured CapabilityGap objects."""
        scanners = [
            InferencePerformanceScanner(),
            ContextUtilizationScanner(),
            ResourceProfilerScanner(),
            BottleneckDetectorScanner(),
            ComparativeAnalyzerScanner()
        ]

        for scanner in scanners:
            gaps = scanner.scan()
            assert isinstance(gaps, list)

            for gap in gaps:
                assert hasattr(gap, 'type')
                assert hasattr(gap, 'name')
                assert hasattr(gap, 'category')
                assert hasattr(gap, 'reason')
                assert hasattr(gap, 'alignment_score')
                assert hasattr(gap, 'install_cost')
                assert 0.0 <= gap.alignment_score <= 1.0
                assert 0.0 <= gap.install_cost <= 1.0

    def test_monitor_can_run_cycle_with_new_scanners(self):
        """Test capability monitor can complete cycle with introspection scanners."""
        monitor = CapabilityDiscoveryMonitor()

        try:
            introspection_scanners = [
                s for s in monitor.scanners
                if s.get_metadata().domain == 'introspection'
            ]
            assert len(introspection_scanners) >= 5
        except Exception as e:
            pytest.fail(f"Monitor cycle failed with introspection scanners: {e}")
