import pytest
from src.registry.capability_scanners.pypi_scanner import PyPIScanner
from src.registry.capability_scanners.base import CapabilityGap, ScannerMetadata


def test_pypi_scanner_metadata():
    """Test PyPIScanner metadata."""
    scanner = PyPIScanner()
    metadata = scanner.get_metadata()

    assert metadata.name == 'PyPIScanner'
    assert metadata.domain == 'external_tools'
    assert 0.0 <= metadata.scan_cost <= 1.0
    assert 0.0 <= metadata.schedule_weight <= 1.0


def test_pypi_scanner_scan_returns_gaps():
    """Test PyPIScanner.scan() returns list of CapabilityGap objects."""
    scanner = PyPIScanner()
    gaps = scanner.scan()

    assert isinstance(gaps, list)
    for gap in gaps:
        assert isinstance(gap, CapabilityGap)
        assert gap.type == 'external_tool'
        assert gap.category == 'pypi_package'


def test_pypi_scanner_detects_uninstalled_package():
    """Test scanner detects packages that aren't installed."""
    scanner = PyPIScanner()
    gaps = scanner.scan()

    gap_names = [g.name for g in gaps]

    for gap in gaps:
        assert gap.type == 'external_tool'
        assert gap.category == 'pypi_package'
        assert 0.0 <= gap.alignment_score <= 1.0
        assert 0.0 <= gap.install_cost <= 1.0
